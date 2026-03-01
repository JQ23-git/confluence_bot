import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, time
import pytz
import os
import numpy as np
import time as py_time
import logging
import sqlite3

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("confluence_bot")

# --- 1. CONFIG & DARK STYLE ---
st.set_page_config(layout="wide", page_title="confluence.bot")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .stApp { background-color: #0e1117; color: #ffffff; }
    button[data-baseweb="tab"] div p { font-size: 18px !important; font-weight: 700 !important; color: #ffffff !important; }
    div.stButton > button { border: 1px solid #333; background-color: #0e1117; color: #ffffff; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# --- 2. CONSTANTS ---
AE_FAST      = 16
AE_MID       = 26
AE_SLOW      = 34

# Gambit: span=17 with a 3.5x multiplier on alpha (intentional design choice)
GAMBIT_SPAN  = 17
GAMBIT_ALPHA = 3.5 / GAMBIT_SPAN  # ≈ 0.206 — faster reaction than standard span EWM

CACHE_TTL    = 3600   # seconds
COIN_WORKERS = 12     # higher parallelism for 100+ coin scans
DB_PATH      = "signals.db"

# TradingView symbol overrides for tickers that need exchange prefixes
TV_SYMBOL_MAP = {
    "GC=F": "COMEX:GC1!",
    "SI=F": "COMEX:SI1!",
    "CL=F": "NYMEX:CL1!",
    "NG=F": "NYMEX:NG1!",
}

CONFLUENCE_ORDER = [
    "🚀 STRONG BUY", "🔥 REVERSAL", "📈 Trending Up",
    "⚪ Neutral", "📉 Trending Down", "⬇️ STRONG SELL"
]

# --- 3. DATA MAPPING ---
STOCK_GROUPS = {
    "Tech & AI":        ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM"],
    "Cyber & Cloud":    ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space":  ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy":           ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA",
                         "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}
STOCK_MAP = {t: t for cat in STOCK_GROUPS.values() for t in cat}

def get_crypto_map():
    csv_file = 'top200_non_stable_non_wrapped.csv'
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            df.columns = df.columns.str.strip()
            if 'Ticker' in df.columns and 'Name' in df.columns:
                return {str(row['Ticker']).strip(): str(row['Name']).strip() for _, row in df.iterrows()}
            logger.warning("CSV missing expected 'Ticker'/'Name' columns; falling back to defaults")
        except Exception as e:
            logger.warning("Failed to load crypto CSV: %s", e)
    return {"BTC-USD": "Bitcoin", "ETH-USD": "Ethereum"}

CRYPTO_MAP    = get_crypto_map()
COMMODITY_MAP = {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil", "NG=F": "Natural Gas"}

# --- 4. SIGNAL HISTORY (SQLite) ---
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS signal_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            ticker     TEXT NOT NULL,
            name       TEXT NOT NULL,
            confluence TEXT NOT NULL,
            score      INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()

_init_db()

def log_signals(df: pd.DataFrame, asset_type: str):
    """Persist current scan snapshot to SQLite (once per session per asset type)."""
    if df is None or df.empty:
        return
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (ts, asset_type, str(row.get("Ticker", "")),
         str(row.get("Company", "")), str(row.get("Confluence", "")),
         int(row.get("_score", 0)))
        for _, row in df.iterrows()
    ]
    con = sqlite3.connect(DB_PATH)
    con.executemany(
        "INSERT INTO signal_history (ts, asset_type, ticker, name, confluence, score) VALUES (?,?,?,?,?,?)",
        rows
    )
    con.commit()
    con.close()

@st.cache_data(ttl=300)
def get_signal_history(limit: int = 2000) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT ts, asset_type, ticker, name, confluence, score "
        "FROM signal_history ORDER BY ts DESC LIMIT ?",
        con, params=(limit,)
    )
    con.close()
    return df

# --- 5. INDICATORS ---
def calculate_smma(series, length):
    return series.ewm(alpha=1 / length, adjust=False).mean()

def get_ae_signal(df):
    src = (df['High'] + df['Low']) / 2
    f = calculate_smma(src, AE_FAST)
    m = calculate_smma(src, AE_MID)
    s = calculate_smma(src, AE_SLOW)
    bull = (f > m) & (m > s) & (src > f)
    bear = (f < m) & (m < s) & (src < f)
    return bull, bear

def get_ae_signal_ratio(ratio_series):
    """AE signal applied to a plain price ratio series (no High/Low columns)."""
    f = calculate_smma(ratio_series, AE_FAST)
    m = calculate_smma(ratio_series, AE_MID)
    s = calculate_smma(ratio_series, AE_SLOW)
    bull = (f > m) & (m > s) & (ratio_series > f)
    bear = (f < m) & (m < s) & (ratio_series < f)
    return bull, bear

def get_gambit_signal(df):
    l_s = df['Low'].ewm(alpha=GAMBIT_ALPHA, adjust=False).mean()
    h_s = df['High'].ewm(alpha=GAMBIT_ALPHA, adjust=False).mean()
    rev_up   = (df['Close'].shift(1) < l_s.shift(1)) & (df['Close'] > l_s) & (df['Close'] > df['Open'])
    rev_down = (df['Close'].shift(1) > h_s.shift(1)) & (df['Close'] < h_s) & (df['Close'] < df['Open'])
    return rev_up, rev_down

# --- 6. ENGINE ---
def _tv_url(ticker):
    symbol = TV_SYMBOL_MAP.get(ticker, ticker)
    return f"https://www.tradingview.com/chart/?symbol={symbol}"

from concurrent.futures import ThreadPoolExecutor, as_completed

APP_VERSION = "v5.3"

def _fetch_one(sym, period="1y", interval="1d", retries=3):
    """Fetch OHLCV for a single ticker via Ticker.history(); retry on failure."""
    delay = 1
    for attempt in range(retries):
        try:
            df = yf.Ticker(sym).history(period=period, interval=interval)
            if df is not None and not df.empty:
                return sym, df
        except Exception as e:
            logger.debug("Attempt %d for %s failed: %s", attempt + 1, sym, e)
        if attempt < retries - 1:
            py_time.sleep(delay)
            delay *= 2
    return sym, pd.DataFrame()

def _fetch_all(symbols, period="1y", interval="1d", max_workers=4):
    """Fetch all symbols with a thread pool to avoid rate-limiting."""
    result = {}
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {exe.submit(_fetch_one, sym, period, interval): sym for sym in symbols}
        for fut in as_completed(futures):
            sym, df = fut.result()
            if not df.empty:
                result[sym] = df
    logger.info("_fetch_all: got %d / %d symbols", len(result), len(symbols))
    return result

def _flip_date(signal_bool, index):
    """Return the date when the current True streak began."""
    vals = signal_bool.values
    i = len(vals) - 1
    while i > 0 and vals[i - 1]:
        i -= 1
    return pd.Timestamp(index[i]).strftime('%b %d')

@st.cache_data(ttl=CACHE_TTL)
def scan(t_map, bench, max_workers=4, interval="1d", is_crypto=False):
    tz_cst  = pytz.timezone('US/Central')
    now_cst = datetime.now(tz_cst)
    period  = "2y" if interval == "1wk" else "1y"

    all_syms = list(dict.fromkeys([bench] + list(t_map.keys())))
    dfs = _fetch_all(all_syms, period=period, interval=interval, max_workers=max_workers)

    bench_df = dfs.get(bench, pd.DataFrame())
    if bench_df.empty or len(bench_df) < AE_SLOW:
        logger.error("Benchmark %s unavailable or insufficient (%d rows)", bench, len(bench_df))
        return pd.DataFrame(), "unavailable"

    def _strip(df):
        """Remove the last candle if it hasn't closed yet."""
        if is_crypto:
            # Crypto daily candle closes at UTC midnight — strip if last bar is today (UTC)
            last_date = df.index[-1]
            if hasattr(last_date, 'date'):
                last_date = last_date.date()
            if last_date >= datetime.utcnow().date():
                return df.iloc[:-1]
            return df
        elif interval == "1wk":
            # Weekly bar is incomplete Mon–Fri; confirmed on weekends
            if now_cst.weekday() < 5:
                return df.iloc[:-1]
            return df
        else:
            # Daily stocks: confirmed after 5 pm CST on weekdays
            if now_cst.weekday() < 5 and now_cst.time() < time(17, 0):
                return df.iloc[:-1]
            return df

    spy_sub = _strip(bench_df)
    if spy_sub.empty:
        return pd.DataFrame(), "unavailable"

    if interval == "1wk":
        confirmed_date = "Week of " + spy_sub.index[-1].strftime('%b %d, %Y')
    else:
        confirmed_date = spy_sub.index[-1].strftime('%b %d, %Y')

    results = []
    for ticker, name in t_map.items():
        df = dfs.get(ticker, pd.DataFrame())
        if df.empty or len(df) < AE_SLOW:
            logger.debug("Skipping %s: only %d rows", ticker, len(df))
            continue

        df = _strip(df)
        if df.empty or len(df) < AE_SLOW:
            continue

        try:
            bull, bear = get_ae_signal(df)
            buy,  sell = get_gambit_signal(df)
        except Exception as e:
            logger.warning("Signal calc failed for %s: %s", ticker, e)
            continue

        t_stat = "⚪ Neutral"
        g_stat = "—"
        c_stat = "⚪ Neutral"

        if bull.iloc[-1]:   t_stat = "🟢 Bullish"
        elif bear.iloc[-1]: t_stat = "🔴 Bearish"

        if buy.iloc[-1]:    g_stat = "🟢 BUY (Reversal)"
        elif sell.iloc[-1]: g_stat = "🔴 SELL (Pivot)"

        if bull.iloc[-1]:
            c_stat = "🚀 STRONG BUY" if buy.iloc[-1] else "📈 Trending Up"
        elif bear.iloc[-1]:
            c_stat = "⬇️ STRONG SELL" if sell.iloc[-1] else "📉 Trending Down"
        elif buy.iloc[-1]:
            c_stat = "🔥 REVERSAL"

        ae_score = 1 if bull.iloc[-1] else (-1 if bear.iloc[-1] else 0)
        g_score  = 1 if buy.iloc[-1]  else (-1 if sell.iloc[-1]  else 0)

        if bull.iloc[-1]:
            since = _flip_date(bull, df.index)
        elif bear.iloc[-1]:
            since = _flip_date(bear, df.index)
        else:
            since = "—"

        rs_stat   = "—"
        rs_score  = 0
        bench_since = "—"
        common = df.index.intersection(spy_sub.index)
        if len(common) > AE_SLOW:
            ratio = df.loc[common, 'Close'] / spy_sub.loc[common, 'Close']
            r_bull, r_bear = get_ae_signal_ratio(ratio)
            if r_bull.iloc[-1]:
                rs_stat, rs_score = "🟢 Bullish", 1
                bench_since = _flip_date(r_bull, r_bull.index)
            elif r_bear.iloc[-1]:
                rs_stat, rs_score = "🔴 Bearish", -1
                bench_since = _flip_date(r_bear, r_bear.index)
            else:
                rs_stat = "⚪ Neutral"

        score = ae_score + g_score + rs_score
        score_fmt = f"+{score}" if score > 0 else str(score)

        results.append({
            "Company":          name,
            "Ticker":           ticker.replace("-USD", ""),
            "Price":            f"${df['Close'].iloc[-1]:.2f}",
            "Score":            score_fmt,
            "_score":           score,
            "Trend (vs USD)":   t_stat,
            "Since":            since,
            "BenchTrend":       rs_stat,
            "BenchSince":       bench_since,
            "Gambit Reversals": g_stat,
            "Confluence":       c_stat,
            "Action":           _tv_url(ticker),
        })

    if not results:
        return pd.DataFrame(), confirmed_date

    out = pd.DataFrame(results)
    out['Confluence'] = pd.Categorical(out['Confluence'], categories=CONFLUENCE_ORDER, ordered=True)
    out = out.sort_values('Confluence')
    return out, confirmed_date

# --- 7. UI HELPERS ---
def draw(df, b_name, filter_val="All"):
    if df is None or df.empty:
        st.warning("Market data unavailable.")
        return

    disp = df.copy()
    if filter_val != "All":
        disp = disp[disp['Confluence'].astype(str) == filter_val]

    if disp.empty:
        st.info(f"No assets currently showing '{filter_val}'.")
        return

    buy_c, sell_c, rev_c = "#06402B", "#4a0f0f", "#5c4d00"

    def highlight(row):
        val = str(row.get('Confluence', ''))
        if "STRONG BUY"  in val: return [f'background-color: {buy_c}']  * len(row)
        if "REVERSAL"    in val: return [f'background-color: {rev_c}']  * len(row)
        if "STRONG SELL" in val: return [f'background-color: {sell_c}'] * len(row)
        return [''] * len(row)

    bench_since_label = b_name.replace("Trend (", "Since (")
    display_df = disp.drop(columns=['_score'], errors='ignore').rename(columns={
        "BenchTrend":  b_name,
        "BenchSince":  bench_since_label,
    })
    st.dataframe(
        display_df.style.apply(highlight, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True, use_container_width=True, height=1200
    )

# --- 8. HEADER ---
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=350)
    else:
        st.title("confluence.bot")
with col2:
    st.caption(APP_VERSION)
    if st.button("Refresh"):
        st.cache_data.clear()
        st.rerun()

t_stocks, t_coins, t_comm, t_hist = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️", "HISTORY 📋"])

# --- 9. STOCKS TAB ---
with t_stocks:
    try:
        df_s, d_s = scan(STOCK_MAP, "SPY", interval="1wk")
        st.caption(f"📅 Weekly Close: {d_s}")
        if not df_s.empty and "stocks_logged" not in st.session_state:
            log_signals(df_s, "stocks")
            st.session_state["stocks_logged"] = True

        f_col, _ = st.columns([2, 8])
        with f_col:
            sf = st.selectbox("Filter", ["All"] + CONFLUENCE_ORDER, key="s_filter")

        sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
        with sub[0]:
            draw(df_s, "Trend (vs SPY)", sf)
        for i, cat in enumerate(STOCK_GROUPS.keys()):
            with sub[i + 1]:
                if df_s is not None and not df_s.empty and 'Ticker' in df_s.columns:
                    draw(df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])], "Trend (vs SPY)", sf)
                else:
                    st.info("Loading market data...")
    except Exception as e:
        logger.error("Stocks scan failed: %s", e)
        st.error("Could not load stock data. Try refreshing.")

# --- 10. COINS TAB ---
with t_coins:
    try:
        df_c, d_c = scan(CRYPTO_MAP, "BTC-USD", max_workers=COIN_WORKERS, is_crypto=True)
        st.caption(f"📅 Daily Close: {d_c} | Coins Found: {len(df_c)}")
        if not df_c.empty and "coins_logged" not in st.session_state:
            log_signals(df_c, "coins")
            st.session_state["coins_logged"] = True

        f_col, _ = st.columns([2, 8])
        with f_col:
            cf = st.selectbox("Filter", ["All"] + CONFLUENCE_ORDER, key="c_filter")
        draw(df_c, "Trend (vs BTC)", cf)
    except Exception as e:
        logger.error("Crypto scan failed: %s", e)
        st.error("Could not load crypto data. Try refreshing.")

# --- 11. COMMODITIES TAB ---
with t_comm:
    try:
        df_m, d_m = scan(COMMODITY_MAP, "SPY", interval="1wk")
        st.caption(f"📅 Weekly Close: {d_m} | Commodities Found: {len(df_m)}")
        if not df_m.empty and "comm_logged" not in st.session_state:
            log_signals(df_m, "commodities")
            st.session_state["comm_logged"] = True

        f_col, _ = st.columns([2, 8])
        with f_col:
            mf = st.selectbox("Filter", ["All"] + CONFLUENCE_ORDER, key="m_filter")
        draw(df_m, "Trend (vs SPY)", mf)
    except Exception as e:
        logger.error("Commodities scan failed: %s", e)
        st.error("Could not load commodities data. Try refreshing.")

# --- 12. HISTORY TAB ---
with t_hist:
    st.subheader("Signal History")
    st.caption("Most recent signal snapshot per ticker, logged once per session.")

    hist_df = get_signal_history()
    if hist_df.empty:
        st.info("No history yet — open each tab to trigger a scan.")
    else:
        # Latest signal per ticker (most recent timestamp first)
        latest = (
            hist_df
            .drop_duplicates(subset=["ticker"], keep="first")
            .copy()
            .rename(columns={
                "ts": "Last Seen (UTC)", "asset_type": "Type",
                "ticker": "Ticker", "name": "Company",
                "confluence": "Confluence", "score": "Score"
            })
        )
        latest["Score"] = latest["Score"].apply(lambda x: f"+{x}" if int(x) > 0 else str(x))

        h_col, _ = st.columns([2, 8])
        with h_col:
            hf = st.selectbox("Filter by signal", ["All"] + CONFLUENCE_ORDER, key="h_filter")
        if hf != "All":
            latest = latest[latest["Confluence"] == hf]

        buy_c, sell_c, rev_c = "#06402B", "#4a0f0f", "#5c4d00"

        def highlight_hist(row):
            val = str(row.get("Confluence", ""))
            if "STRONG BUY"  in val: return [f"background-color: {buy_c}"] * len(row)
            if "REVERSAL"    in val: return [f"background-color: {rev_c}"] * len(row)
            if "STRONG SELL" in val: return [f"background-color: {sell_c}"] * len(row)
            return [""] * len(row)

        st.dataframe(
            latest.style.apply(highlight_hist, axis=1),
            hide_index=True, use_container_width=True, height=600
        )

        st.divider()
        st.caption("📈 Recent High-Signal Events (STRONG BUY / REVERSAL / STRONG SELL)")
        alerts = hist_df[
            hist_df["confluence"].str.contains("STRONG BUY|REVERSAL|STRONG SELL", na=False)
        ].head(100).rename(columns={
            "ts": "Time (UTC)", "asset_type": "Type",
            "ticker": "Ticker", "name": "Company",
            "confluence": "Signal", "score": "Score"
        })
        if not alerts.empty:
            alerts["Score"] = alerts["Score"].apply(lambda x: f"+{x}" if int(x) > 0 else str(x))
            st.dataframe(alerts, hide_index=True, use_container_width=True, height=400)
        else:
            st.info("No high-signal events logged yet.")
