import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, time
import pytz
import os
import numpy as np
import time as py_time
import logging

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
# AE signal periods
AE_FAST   = 16
AE_MID    = 26
AE_SLOW   = 34

# Gambit: span=17 with a 3.5x multiplier on alpha (intentional design choice)
GAMBIT_SPAN  = 17
GAMBIT_ALPHA = 3.5 / GAMBIT_SPAN  # ≈ 0.206 — faster reaction than standard span EWM

CACHE_TTL = 3600  # seconds

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

# --- 4. INDICATORS ---
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

# --- 5. ENGINE ---
def _tv_url(ticker):
    symbol = TV_SYMBOL_MAP.get(ticker, ticker)
    return f"https://www.tradingview.com/chart/?symbol={symbol}"

def _batch_download(symbols, period="1y"):
    """Download all symbols in ONE request; returns dict ticker -> OHLCV DataFrame."""
    unique = list(dict.fromkeys(symbols))
    try:
        raw = yf.download(
            unique, period=period,
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True,
        )
    except Exception as e:
        logger.error("Batch download failed: %s", e)
        return {}

    if raw is None or raw.empty:
        logger.error("Batch download returned empty result for %s tickers", len(unique))
        return {}

    result = {}
    for sym in unique:
        try:
            if len(unique) == 1:
                # single-ticker download: flat DataFrame, no MultiIndex
                df = raw
            else:
                df = raw[sym]
            # drop rows where all OHLCV values are NaN
            df = df.dropna(how="all")
            if not df.empty:
                result[sym] = df
        except (KeyError, TypeError) as e:
            logger.debug("No data for %s: %s", sym, e)
    return result

@st.cache_data(ttl=CACHE_TTL)
def scan(t_map, bench):
    tz_cst  = pytz.timezone('US/Central')
    now_cst = datetime.now(tz_cst)

    all_syms = list(dict.fromkeys([bench] + list(t_map.keys())))
    dfs = _batch_download(all_syms)

    bench_df = dfs.get(bench, pd.DataFrame())
    if bench_df.empty or len(bench_df) < AE_SLOW:
        logger.error("Benchmark %s unavailable or insufficient (%d rows)", bench, len(bench_df))
        return pd.DataFrame(), "unavailable"

    spy_sub = bench_df.iloc[:-1] if now_cst.time() < time(17, 0) else bench_df
    confirmed_date = spy_sub.index[-1].strftime('%b %d, %Y')

    results = []
    for ticker, name in t_map.items():
        df = dfs.get(ticker, pd.DataFrame())
        if df.empty or len(df) < AE_SLOW:
            logger.debug("Skipping %s: only %d rows", ticker, len(df))
            continue

        if now_cst.time() < time(17, 0):
            df = df.iloc[:-1]

        try:
            bull, bear = get_ae_signal(df)
            buy,  sell = get_gambit_signal(df)
        except Exception as e:
            logger.warning("Signal calc failed for %s: %s", ticker, e)
            continue

        t_stat = "Neutral ⚪"
        g_stat = "—"
        c_stat = "⚪ Neutral"

        if bull.iloc[-1]:   t_stat = "Bullish 🟢"
        elif bear.iloc[-1]: t_stat = "Bearish 🔴"

        if buy.iloc[-1]:    g_stat = "🟢 BUY (Reversal)"
        elif sell.iloc[-1]: g_stat = "🔴 SELL (Pivot)"

        if bull.iloc[-1]:
            c_stat = "🚀 STRONG BUY" if buy.iloc[-1] else "📈 Trending Up"
        elif bear.iloc[-1]:
            c_stat = "⬇️ STRONG SELL" if sell.iloc[-1] else "📉 Trending Down"
        elif buy.iloc[-1]:
            c_stat = "🔥 REVERSAL"

        rs_stat = "—"
        common = df.index.intersection(spy_sub.index)
        if len(common) > AE_SLOW:
            ratio = df.loc[common, 'Close'] / spy_sub.loc[common, 'Close']
            r_bull, r_bear = get_ae_signal_ratio(ratio)
            rs_stat = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"

        results.append({
            "Company":          name,
            "Ticker":           ticker.replace("-USD", ""),
            "Price":            f"${df['Close'].iloc[-1]:.2f}",
            "Trend (vs USD)":   t_stat,
            "BenchTrend":       rs_stat,
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

# --- 6. UI ---
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=350)
    else:
        st.title("confluence.bot")
with col2:
    if st.button("Refresh"):
        st.cache_data.clear()
        st.rerun()

t_stocks, t_coins, t_comm = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️"])

def draw(df, b_name):
    if df is None or df.empty:
        st.warning("Market data unavailable.")
        return
    buy_c, sell_c, rev_c = "#06402B", "#4a0f0f", "#5c4d00"

    def highlight(row):
        val = str(row.get('Confluence', ''))
        if "STRONG BUY" in val:  return [f'background-color: {buy_c}'] * len(row)
        if "REVERSAL"   in val:  return [f'background-color: {rev_c}'] * len(row)
        if "STRONG SELL" in val: return [f'background-color: {sell_c}'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df.rename(columns={"BenchTrend": b_name}).style.apply(highlight, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True, use_container_width=True, height=1200
    )

with t_stocks:
    try:
        df_s, d_s = scan(STOCK_MAP, "SPY")
        st.caption(f"📅 Confirmed Close: {d_s}")
        sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
        with sub[0]:
            draw(df_s, "Trend (vs SPY)")
        for i, cat in enumerate(STOCK_GROUPS.keys()):
            with sub[i + 1]:
                if df_s is not None and not df_s.empty and 'Ticker' in df_s.columns:
                    draw(df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])], "Trend (vs SPY)")
                else:
                    st.info("Loading market data...")
    except Exception as e:
        logger.error("Stocks scan failed: %s", e)
        st.error("Could not load stock data. Try refreshing.")

with t_coins:
    try:
        df_c, d_c = scan(CRYPTO_MAP, "BTC-USD")
        st.caption(f"📅 Daily Close: {d_c} | Coins Found: {len(df_c)}")
        draw(df_c, "Trend (vs BTC)")
    except Exception as e:
        logger.error("Crypto scan failed: %s", e)
        st.error("Could not load crypto data. Try refreshing.")

with t_comm:
    try:
        df_m, d_m = scan(COMMODITY_MAP, "SPY")
        st.caption(f"📅 Daily Close: {d_m} | Commodities Found: {len(df_m)}")
        draw(df_m, "Trend (vs SPY)")
    except Exception as e:
        logger.error("Commodities scan failed: %s", e)
        st.error("Could not load commodities data. Try refreshing.")
