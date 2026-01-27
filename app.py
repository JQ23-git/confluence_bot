import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# --- 1. CONFIG & THEME TOGGLE ---
st.set_page_config(layout="wide", page_title="confluence.bot", page_icon="favicon.ico")

# Use a checkbox at the top for the toggle
use_light_mode = st.checkbox("☀️ Light Mode")

# Theme Variables
if use_light_mode:
    bg_color = "#ffffff"
    text_color = "#000000"
    card_bg = "#f0f2f6"
    border_color = "#ddd"
    accent = "#22d3ee"
    # Lighter highlights for light mode
    buy_color = "rgba(6, 64, 43, 0.2)"
    sell_color = "rgba(74, 15, 15, 0.2)"
    rev_color = "rgba(92, 77, 0, 0.2)"
    trend_up = "rgba(27, 77, 62, 0.15)"
    trend_down = "rgba(77, 27, 27, 0.15)"
else:
    bg_color = "#0e1117"
    text_color = "#ffffff"
    card_bg = "#1a1c24"
    border_color = "#333"
    accent = "#22d3ee"
    # Deep jewel tones for dark mode
    buy_color = "#06402B"
    sell_color = "#4a0f0f"
    rev_color = "#5c4d00"
    trend_up = "#1b4d3e"
    trend_down = "#4d1b1b"

st.markdown(f"""
<style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    
    .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
    
    .stApp {{
        background-color: {bg_color};
        color: {text_color};
    }}
    
    button[data-baseweb="tab"] div p {{ 
        font-size: 18px !important; 
        font-weight: 700 !important;
        color: {text_color} !important;
    }}

    .status-text {{ 
        color: {accent}; 
        font-size: 0.85rem; 
        font-weight: 600; 
        text-transform: uppercase; 
    }}
    
    div.stButton > button {{ 
        border: 1px solid {border_color}; 
        background-color: {bg_color}; 
        color: {text_color}; 
        border-radius: 6px; 
    }}
</style>
""", unsafe_allow_html=True)

# --- 2. DATA MAPPING ---
STOCK_GROUPS = {
    "Tech & AI": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM"],
    "Cyber & Cloud": ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space": ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy": ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA", "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}

STOCK_MAP = {t: t for cat in STOCK_GROUPS.values() for t in cat}

CRYPTO_MAP = {
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "BNB", "XRP-USD": "XRP", "SOL-USD": "Solana",
    "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin", "TRX-USD": "TRON", "LINK-USD": "Chainlink", "AVAX-USD": "Avalanche",
    "PEPE-USD": "Pepe", "SHIB-USD": "Shiba Inu", "WIF-USD": "dogwifhat", "FET-USD": "Artificial Superintelligence",
    "RENDER-USD": "Render", "HYPE-USD": "Hyperliquid", "SUI-USD": "Sui", "NEAR-USD": "NEAR", "APT-USD": "Aptos"
}

COMMODITY_MAP = {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil", "NG=F": "Natural Gas", "ZC=F": "Corn"}

# --- 3. INDICATORS ---
def calculate_smma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()

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
    ticker, name, asset_type, spy_sub, is_closed = args
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df is None or len(df) < 50: return None
        if asset_type == "Crypto" or not is_closed: df = df.iloc[:-1]

        bull, bear = get_ae_signal(df)
        buy, sell = get_gambit_signal(df)
        
        t_stat = "Neutral ⚪"
        if bull.iloc[-1]: t_stat = "Bullish 🟢"
        elif bear.iloc[-1]: t_stat = "Bearish 🔴"

        g_stat = "—"
        if buy.iloc[-1]: g_stat = "🟢 BUY (Reversal)"
        elif sell.iloc[-1]: g_stat = "🔴 SELL (Pivot)"
        
        c_stat = "⚪ Neutral"
        if bull.iloc[-1]:
            c_stat = "🚀 STRONG BUY" if buy.iloc[-1] else "📈 Trending Up"
        elif bear.iloc[-1]:
            c_stat = "⬇️ STRONG SELL" if sell.iloc[-1] else "📉 Trending Down"
        elif buy.iloc[-1]:
            c_stat = "🔥 REVERSAL"

        common = df.index.intersection(spy_sub.index)
        rs_stat = "—"
        if len(common) > 20:
            ratio = df.loc[common, 'Close'] / spy_sub.loc[common, 'Close']
            r_bull, r_bear = get_ae_signal(pd.DataFrame({'ratio': ratio}), 'ratio')
            rs_stat = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"

        return {"Company": name, "Ticker": ticker.replace("-USD", ""), "Price": f"${df['Close'].iloc[-1]:.2f}",
                "Trend (vs USD)": t_stat, "Trend (vs SPY/BTC)": rs_stat, "Gambit Reversals": g_stat, "Confluence": c_stat,
                "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"}
    except: return None

@st.cache_data(ttl=3600)
def scan(t_map, bench, a_type):
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)
    is_closed = now.hour >= 16
    spy = yf.Ticker(bench).history(period="1y")
    spy_sub = spy.iloc[:-1] if not is_closed or a_type == "Crypto" else spy
    
    tasks = [(t, n, a_type, spy_sub, is_closed) for t, n in t_map.items()]
    with ThreadPoolExecutor(max_workers=20) as exe:
        results = [r for r in list(exe.map(fetch_ticker, tasks)) if r]
    
    df = pd.DataFrame(results)
    if not df.empty:
        cats = ["🚀 STRONG BUY", "🔥 REVERSAL", "📈 Trending Up", "⚪ Neutral", "📈 Pullback", "📉 Trending Down", "⬇️ STRONG SELL"]
        df['Confluence'] = pd.Categorical(df['Confluence'], categories=cats, ordered=True)
        df = df.sort_values('Confluence')
    return df, spy_sub.index[-1].strftime('%b %d, %Y')

# --- 5. UI ---
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot v4.0")
with col2: 
    st.markdown('<div class="status-container"><div class="status-text">● Turbo Online</div></div>', unsafe_allow_html=True)
    if st.button("Refresh"): st.cache_data.clear(); st.rerun()

t_stocks, t_coins, t_comm = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️"])

def highlight_rows(row):
    val = str(row.get('Confluence', ''))
    if "STRONG BUY" in val: return [f'background-color: {buy_color}'] * len(row)
    if "STRONG SELL" in val: return [f'background-color: {sell_color}'] * len(row)
    if "REVERSAL" in val: return [f'background-color: {rev_color}'] * len(row)
    if "Trending Up" in val: return [f'background-color: {trend_up}'] * len(row)
    if "Trending Down" in val: return [f'background-color: {trend_down}'] * len(row)
    return [''] * len(row)

def draw(df):
    st.dataframe(df.style.apply(highlight_rows, axis=1), 
                 column_config={"Action": st.column_config.LinkColumn("Chart")}, 
                 hide_index=True, use_container_width=True, height=1200)

with t_stocks:
    df_s, d_s = scan(STOCK_MAP, "SPY", "Stock")
    st.caption(f"Data Date: {d_s}")
    sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
    with sub[0]: draw(df_s)
    for i, cat in enumerate(STOCK_GROUPS.keys()):
        with sub[i+1]: draw(df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])])

with t_coins:
    df_c, d_c = scan(CRYPTO_MAP, "BTC-USD", "Crypto")
    st.caption(f"Data Date: {d_c}")
    draw(df_c)

with t_comm:
    df_m, d_m = scan(COMMODITY_MAP, "SPY", "Comm")
    st.caption(f"Data Date: {d_m}")
    draw(df_m)
