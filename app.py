import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, time
import pytz
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# --- 1. CONFIG & DARK STYLE ---
st.set_page_config(layout="wide", page_title="confluence.bot", page_icon="favicon.ico")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .stApp { background-color: #0e1117; color: #ffffff; }
    button[data-baseweb="tab"] div p { font-size: 18px !important; font-weight: 700 !important; color: #ffffff !important; }
    .status-text { color: #22d3ee; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
    div.stButton > button { border: 1px solid #333; background-color: #0e1117; color: #ffffff; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# --- 2. DATA MAPPING ---

# STOCK GROUPS
STOCK_GROUPS = {
    "Tech & AI": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM"],
    "Cyber & Cloud": ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space": ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy": ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA", "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}
STOCK_MAP = {t: t for cat in STOCK_GROUPS.values() for t in cat}

# DYNAMIC CRYPTO LOAD (From your CSV)
def get_crypto_map():
    if os.path.exists('top200_non_stable_non_wrapped.csv'):
        df_csv = pd.read_csv('top200_non_stable_non_wrapped.csv')
        # Ensure Ticker column exists
        if 'Ticker' in df_csv.columns:
            return {f"{row['Ticker']}-USD": row['Name'] for _, row in df_csv.iterrows()}
    # Fallback to base list if file missing
    return {"BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana"}

CRYPTO_MAP = get_crypto_map()

COMMODITY_MAP = {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil", "NG=F": "Natural Gas", "ZC=F": "Corn"}

# --- 3. INDICATORS ---
def calculate_smma(series, length): 
    return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    src = (df['High'] + df['Low']) / 2 if target_col == 'hl2' else df[target_col]
    f, m, s = calculate_smma(src, 16), calculate_smma(src, 26), calculate_smma(src, 34)
    return (f > m) & (m > s) & (src > f), (f < m) & (m < s) & (src < f)

def get_gambit_signal(df):
    l_s = df['Low'].ewm(alpha=3.5/17, adjust=False).mean()
    h_s = df['High'].ewm(alpha=3.5/17, adjust=False).mean()
    rev_up = (df['Close'].shift(1) < l_s.shift(1)) & (df['Close'] > l_s) & (df['Close'] > df['Open'])
    rev_down = (df['Close'].shift(1) > h_s.shift(1)) & (df['Close'] < h_s) & (df['Close'] < df['Open'])
    return rev_up, rev_down

# --- 4. ENGINE ---
def fetch_ticker(args):
    ticker, name, asset_type, spy_sub, now_et = args
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df is None or len(df) < 50: return None
        
        # SMART DROP LOGIC: Only drop if the last candle is currently trading
        last_date = df.index[-1].date()
        if asset_type == "Crypto":
            if last_date == datetime.now(pytz.utc).date(): df = df.iloc[:-1]
        else:
            if last_date == now_et.date() and now_et.hour < 16: df = df.iloc[:-1]

        bull, bear = get_ae_signal(df)
        buy, sell = get_gambit_signal(df)
        t_stat = "Neutral ⚪"; g_stat = "—"; c_stat = "⚪ Neutral"
        
        if bull.iloc[-1]: t_stat = "Bullish 🟢"
        elif bear.iloc[-1]: t_stat = "Bearish 🔴"
        
        if buy.iloc[-1]: g_stat = "🟢 BUY (Reversal)"
        elif sell.iloc[-1]: g_stat = "🔴 SELL (Pivot)"
        
        if bull.iloc[-1]: c_stat = "🚀 STRONG BUY" if buy.iloc[-1] else "📈 Trending Up"
        elif bear.iloc[-1]: c_stat = "⬇️ STRONG SELL" if sell.iloc[-1] else "📉 Trending Down"
        elif buy.iloc[-1]: c_stat = "🔥 REVERSAL"

        common = df.index.intersection(spy_sub.index)
        rs_stat = "—"
        if len(common) > 20:
            ratio = df.loc[common, 'Close'] / spy_sub.loc[common, 'Close']
            r_bull, r_bear = get_ae_signal(pd.DataFrame({'ratio': ratio}), 'ratio')
            rs_stat = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"
            
        return {"Company": name, "Ticker": ticker.replace("-USD", ""), "Price": f"${df['Close'].iloc[-1]:.2f}",
                "Trend (vs USD)": t_stat, "BenchTrend": rs_stat, "Gambit Reversals": g_stat, "Confluence": c_stat,
                "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"}
    except: return None

@st.cache_data(ttl=3600)
def scan(t_map, bench, a_type):
    tz = pytz.timezone('US/Eastern'); now_et = datetime.now(tz)
    spy = yf.Ticker(bench).history(period="1y")
    
    # Correct benchmark timing
    last_spy_date = spy.index[-1].date()
    if a_type == "Crypto":
        if last_spy_date == datetime.now(pytz.utc).date(): spy_sub = spy.iloc[:-1]
        else: spy_sub = spy
    else:
        if last_spy_date == now_et.date() and now_et.hour < 16: spy_sub = spy.iloc[:-1]
        else: spy_sub = spy

    tasks = [(t, n, a_type, spy_sub, now_et) for t, n in t_map.items()]
    with ThreadPoolExecutor(max_workers=25) as exe:
        results = [r for r in list(exe.map(fetch_ticker, tasks)) if r]
    
    df = pd.DataFrame(results)
    if not df.empty:
        cats = ["🚀 STRONG BUY", "🔥 REVERSAL", "📈 Trending Up", "⚪ Neutral", "📉 Trending Down", "⬇️ STRONG SELL"]
        df['Confluence'] = pd.Categorical(df['Confluence'], categories=cats, ordered=True)
        df = df.sort_values('Confluence')
    return df, spy_sub.index[-1].strftime('%b %d, %Y')

# --- 5. UI ---
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot v4.3")
with col2:
    st.markdown('<div class="status-container"><div class="status-text">● Turbo Online</div></div>', unsafe_allow_html=True)
    if st.button("Refresh"): st.cache_data.clear(); st.rerun()

t_stocks, t_coins, t_comm = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️"])

def draw(df, bench_name="Trend (vs SPY)"):
    buy_c, sell_c, rev_c, t_up, t_down = "#06402B", "#4a0f0f", "#5c4d00", "#1b4d3e", "#4d1b1b"
    def highlight(row):
        val = str(row.get('Confluence', ''))
        if "STRONG BUY" in val: return [f'background-color: {buy_c}'] * len(row)
        if "STRONG SELL" in val: return [f'background-color: {sell_c}'] * len(row)
        if "REVERSAL" in val: return [f'background-color: {rev_c}'] * len(row)
        if "Trending Up" in val: return [f'background-color: {t_up}'] * len(row)
        if "Trending Down" in val: return [f'background-color: {t_down}'] * len(row)
        return [''] * len(row)
    
    df_display = df.rename(columns={"BenchTrend": bench_name})
    st.dataframe(df_display.style.apply(highlight, axis=1), 
                 column_config={"Action": st.column_config.LinkColumn("Chart")}, 
                 hide_index=True, use_container_width=True, height=1500)

with t_stocks:
    df_s, d_s = scan(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Confirmed Data Date: {d_s}")
    sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
    with sub[0]: draw(df_s, "Trend (vs SPY)")
    for i, cat in enumerate(STOCK_GROUPS.keys()):
        with sub[i+1]: draw(df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])], "Trend (vs SPY)")

with t_coins:
    df_c, d_c = scan(CRYPTO_MAP, "BTC-USD", "Crypto")
    st.caption(f"📅 Confirmed Data Date: {d_c}")
    draw(df_c, "Trend (vs BTC)")

with t_comm:
    df_m, d_m = scan(COMMODITY_MAP, "SPY", "Comm")
    st.caption(f"📅 Confirmed Data Date: {d_m}")
    draw(df_m, "Trend (vs SPY)")
