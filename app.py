import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz
import os
import time
import numpy as np

# --- 1. CONFIG ---
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

# --- 2. DATA MAPPING (STABLE LISTS) ---
STOCK_GROUPS = {
    "Tech & AI": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM"],
    "Cyber & Cloud": ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space": ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy": ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA", "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}
STOCK_MAP = {t: t for cat in STOCK_GROUPS.values() for t in cat}

def get_crypto_map():
    c_map = {}
    if os.path.exists('top200_non_stable_non_wrapped.csv'):
        try:
            df_csv = pd.read_csv('top200_non_stable_non_wrapped.csv')
            for _, row in df_csv.iterrows():
                t = str(row['Ticker']).strip()
                yf_t = t if "-USD" in t else f"{t}-USD"
                c_map[yf_t] = str(row['Name']).strip()
        except: pass
    if not c_map: c_map = {"BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana"}
    return c_map

CRYPTO_MAP = get_crypto_map()
COMMODITY_MAP = {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil", "NG=F": "Natural Gas"}

# --- 3. INDICATORS ---
def calculate_smma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df):
    src = (df['High'] + df['Low']) / 2
    f, m, s = calculate_smma(src, 16), calculate_smma(src, 26), calculate_smma(src, 34)
    return (f > m) & (m > s) & (src > f), (f < m) & (m < s) & (src < f)

def get_gambit_signal(df):
    l_s = df['Low'].ewm(alpha=3.5/17, adjust=False).mean()
    h_s = df['High'].ewm(alpha=3.5/17, adjust=False).mean()
    rev_up = (df['Close'].shift(1) < l_s.shift(1)) & (df['Close'] > l_s) & (df['Close'] > df['Open'])
    rev_down = (df['Close'].shift(1) > h_s.shift(1)) & (df['Close'] < h_s) & (df['Close'] < df['Open'])
    return rev_up, rev_down

# --- 4. ENGINE ---
def fetch_ticker(ticker, name, spy_sub):
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df is None or len(df) < 10: return None
        df = df.iloc[:-1] # Confirmed Jan 26 Day
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
        if len(common) > 5:
            ratio = df.loc[common, 'Close'] / spy_sub.loc[common, 'Close']
            r_bull, r_bear = get_ae_signal(pd.DataFrame({'ratio': ratio}))
            rs_stat = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"
        return {"Company": name, "Ticker": ticker.replace("-USD", ""), "Price": f"${df['Close'].iloc[-1]:.2f}",
                "Trend (vs USD)": t_stat, "BenchTrend": rs_stat, "Gambit Reversals": g_stat, "Confluence": c_stat,
                "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"}
    except: return None

@st.cache_data(ttl=3600)
def scan(t_map, bench):
    spy = yf.Ticker(bench).history(period="1y").iloc[:-1]
    results = []
    # Sequential load to prevent Rate Limiting
    for t, n in t_map.items():
        res = fetch_ticker(t, n, spy)
        if res: results.append(res)
        time.sleep(0.05) # Tiny breath between requests
    df = pd.DataFrame(results)
    if not df.empty:
        cats = ["🚀 STRONG BUY", "🔥 REVERSAL", "📈 Trending Up", "⚪ Neutral", "📉 Trending Down", "⬇️ STRONG SELL"]
        df['Confluence'] = pd.Categorical(df['Confluence'], categories=cats, ordered=True)
        df = df.sort_values('Confluence')
    return df

# --- 5. UI ---
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot")
with col2:
    if st.button("Refresh"): st.cache_data.clear(); st.rerun()

t_stocks, t_coins, t_comm = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️"])

def draw(df, b_name):
    if df is None or df.empty: st.warning("Fetching data..."); return
    buy_c, sell_c, rev_c, t_up, t_down = "#06402B", "#4a0f0f", "#5c4d00", "#1b4d3e", "#4d1b1b"
    def highlight(row):
        val = str(row.get('Confluence', ''))
        if "STRONG BUY" in val: return [f'background-color: {buy_c}'] * len(row)
        if "STRONG SELL" in val: return [f'background-color: {sell_c}'] * len(row)
        if "REVERSAL" in val: return [f'background-color: {rev_c}'] * len(row)
        if "Trending Up" in val: return [f'background-color: {t_up}'] * len(row)
        if "Trending Down" in val: return [f'background-color: {t_down}'] * len(row)
        return [''] * len(row)
    st.dataframe(df.rename(columns={"BenchTrend": b_name}).style.apply(highlight, axis=1), 
                 column_config={"Action": st.column_config.LinkColumn("Chart")}, 
                 hide_index=True, use_container_width=True, height=1200)

with t_stocks:
    df_s = scan(STOCK_MAP, "SPY")
    st.caption("📅 Confirmed Close: Jan 26, 2025")
    sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
    with sub[0]: draw(df_s, "Trend (vs SPY)")
    for i, cat in enumerate(STOCK_GROUPS.keys()):
        with sub[i+1]: draw(df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])], "Trend (vs SPY)")

with t_coins:
    df_c = scan(CRYPTO_MAP, "BTC-USD")
    st.caption(f"📅 Confirmed Close: Jan 26, 2025 | Coins: {len(df_c)}")
    draw(df_c, "Trend (vs BTC)")

with t_comm:
    df_m = scan(COMMODITY_MAP, "SPY")
    st.caption("📅 Confirmed Close: Jan 26, 2025")
    draw(df_m, "Trend (vs SPY)")
