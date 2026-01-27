import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# --- 1. CONFIG & STYLE ---
st.set_page_config(layout="wide", page_title="confluence.bot", page_icon="favicon.ico")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .stApp { background-color: #0e1117; }
    button[data-baseweb="tab"] div p { font-size: 18px !important; font-weight: 700 !important; letter-spacing: 0.5px !important; }
    .status-container { display: flex; flex-direction: column; align-items: flex-end; justify-content: center; height: 100%; padding-top: 15px; }
    .status-text { color: #22d3ee; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
    div.stButton > button { border: 1px solid #333; background-color: #000; color: #aaa; border-radius: 6px; }
    div.stButton > button:hover { border-color: #22d3ee; color: #22d3ee; }
</style>
""", unsafe_allow_html=True)

# --- 2. DATA MAPPING ---
STOCK_GROUPS = {
    "Tech & AI": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM", "SNDK"],
    "Cyber & Cloud": ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space": ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy": ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA", "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}
STOCK_MAP = {t: t for cat in STOCK_GROUPS.values() for t in cat}

def get_crypto_map():
    c_map = {}
    if os.path.exists('top200_non_stable_non_wrapped.csv'):
        df_csv = pd.read_csv('top200_non_stable_non_wrapped.csv')
        for _, row in df_csv.iterrows():
            t = str(row['Ticker']).strip()
            yf_ticker = t if "-USD" in t else f"{t}-USD"
            c_map[yf_ticker] = str(row['Name']).strip()
    return c_map if c_map else {"BTC-USD": "Bitcoin", "ETH-USD": "Ethereum"}

CRYPTO_MAP = get_crypto_map()
COMMODITY_MAP = {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil", "NG=F": "Natural Gas", "ZC=F": "Corn"}

# --- 3. INDICATOR LOGIC ---
def calculate_smma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    src = (df['High'] + df['Low']) / 2 if target_col == 'hl2' else df[target_col]
    f, m, s = calculate_smma(src, 16), calculate_smma(src, 26), calculate_smma(src, 34)
    return (f > m) & (m > s) & (src > f), (f < m) & (m < s) & (src < f)

def get_gambit_signal(df):
    l_series = df['Low'].ewm(alpha=3.5/17, adjust=False).mean()
    h_series = df['High'].ewm(alpha=3.5/17, adjust=False).mean()
    prev_close = df['Close'].shift(1)
    rev_up = (prev_close < l_series.shift(1)) & (df['Close'] > l_series) & (df['Close'] > df['Open'])
    rev_down = (prev_close > h_series.shift(1)) & (df['Close'] < h_series) & (df['Close'] < df['Open'])
    return rev_up, rev_down

# --- 4. THE YAHOO TURBO SCANNER ---
def fetch_single_ticker(args):
    ticker, name, asset_type, spy_subset = args
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df is None or len(df) < 30: return None
        df = df.iloc[:-1] # Stay on Jan 26 Confirmed Close

        bull, bear = get_ae_signal(df)
        rev_up, rev_down = get_gambit_signal(df)
        
        t_stat = "Neutral ⚪"
        if bull.iloc[-1]: t_stat = "Bullish 🟢"
        elif bear.iloc[-1]: t_stat = "Bearish 🔴"
        
        g_stat = "—"
        if rev_up.iloc[-1]: g_stat = "🟢 BUY (Reversal)"
        elif rev_down.iloc[-1]: g_stat = "🔴 SELL (Pivot)"
        
        c_stat = "⚪ Neutral"
        trigger_text = ""
        if bull.iloc[-1]:
            if rev_up.iloc[-1]: 
                c_stat = "🚀 STRONG BUY"
                trigger_text = "Gambit Buy 🔥"
            else: 
                c_stat = "📈 Trending Up"
        elif bear.iloc[-1]:
            if rev_down.iloc[-1]: 
                c_stat = "⬇️ STRONG SELL"
            else: 
                c_stat = "📉 Trending Down"
        elif rev_up.iloc[-1]:
            c_stat = "🔥 REVERSAL"
            trigger_text = "Trend Flip 🟢"

        common = df.index.intersection(spy_subset.index)
        rs_stat = "—"
        if len(common) > 10:
            ratio = df.loc[common]['Close'] / spy_subset.loc[common]['Close']
            r_bull, r_bear = get_ae_signal(pd.DataFrame({'ratio': ratio}), 'ratio')
            rs_stat = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"
            
        return {
            "Company": name, "Ticker": ticker.replace("-USD", ""), "Trigger": trigger_text,
            "Price": f"${df['Close'].iloc[-1]:.2f}", "Trend (vs USD)": t_stat, 
            "BenchTrend": rs_stat, "Gambit Reversals": g_stat, "Confluence": c_stat,
            "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"
        }
    except: return None

@st.cache_data(ttl=3600) 
def scan_market(tickers_map, benchmark_symbol, asset_type="Stock"):
    spy = yf.Ticker(benchmark_symbol).history(period="1y").iloc[:-1]
    tasks = [(t, n, asset_type, spy) for t, n in tickers_map.items()]
    with ThreadPoolExecutor(max_workers=30) as exe:
        results = [p for p in list(exe.map(fetch_single_ticker, tasks)) if p]
    df = pd.DataFrame(results)
    if not df.empty:
        cats = ["🚀 STRONG BUY", "🔥 REVERSAL", "📈 Trending Up", "⚪ Neutral", "📉 Trending Down", "⬇️ STRONG SELL"]
        df['Confluence'] = pd.Categorical(df['Confluence'], categories=cats, ordered=True)
        df = df.sort_values('Confluence')
    return df, spy.index[-1].strftime('%b %d, %Y')

# --- 5. UI LAYOUT ---
col_left, col_right = st.columns([3, 1])
with col_left:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot") 
with col_right:
    st.markdown("""<div class="status-container"><div class="status-text">● Turbo Online</div></div>""", unsafe_allow_html=True)
    if st.button("Refresh Data"): st.cache_data.clear(); st.rerun()

def highlight_rows(row):
    val = str(row.get('Confluence', ''))
    if "STRONG BUY" in val: return ['background-color: #06402B'] * len(row) 
    if "REVERSAL" in val: return ['background-color: #5c4d00'] * len(row)
    if "STRONG SELL" in val: return ['background-color: #4a0f0f'] * len(row)
    if "Trending Up" in val: return ['background-color: #1b4d3e'] * len(row)
    if "Trending Down" in val: return ['background-color: #4d1b1b'] * len(row)
    return [''] * len(row)

def draw(df, b_name):
    df_d = df.rename(columns={"BenchTrend": b_name})
    st.dataframe(df_d.style.apply(highlight_rows, axis=1), hide_index=True, use_container_width=True, height=1200, 
                 column_config={"Action": st.column_config.LinkColumn("Chart")})

tab_stocks, tab_coins, tab_comm = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️"])

with tab_stocks:
    df_s, d_s = scan_market(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Confirmed Close: {d_s}")
    sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
    with sub[0]: draw(df_s, "Trend (vs SPY)")
    for i, cat in enumerate(STOCK_GROUPS.keys()):
        with sub[i+1]: draw(df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])], "Trend (vs SPY)")

with tab_coins:
    df_c, d_c = scan_market(CRYPTO_MAP, "BTC-USD", "Crypto")
    st.caption(f"📅 Confirmed Close: {d_c} | Total Coins: {len(df_c)}")
    draw(df_c, "Trend (vs BTC)")

with tab_comm:
    df_m, d_m = scan_market(COMMODITY_MAP, "SPY", "Comm")
    st.caption(f"📅 Confirmed Close: {d_m}")
    draw(df_m, "Trend (vs SPY)")
