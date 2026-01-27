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
    
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    
    .stApp {
        background-color: #0e1117;
    }
    
    [data-testid="stImage"] {
        pointer-events: none;
    }
    
    /* --- TABS STYLING --- */
    button[data-baseweb="tab"] div p {
        font-size: 20px !important;    
        font-weight: 800 !important;   
        text-transform: uppercase !important; 
        letter-spacing: 1px !important;
    }
    
    button[data-baseweb="tab"] {
        padding-top: 10px !important;
        padding-bottom: 10px !important;
        margin-right: 20px !important;
    }

    /* SPECIFIC COLORS FOR TABS */
    button[data-baseweb="tab"]:nth-of-type(2) div p { color: #F7931A !important; }
    button[data-baseweb="tab"]:nth-of-type(4) div p { color: #FFD700 !important; }
    
    /* STATUS & REFRESH */
    .status-container {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        justify-content: center;
        height: 100%;
        padding-top: 15px; 
    }
    .status-text {
        color: #22d3ee; 
        font-size: 0.85rem; 
        font-weight: 600;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
        text-transform: uppercase;
    }
    
    div.stButton > button {
        border: 1px solid #333;
        background-color: #000;
        color: #aaa;
        font-size: 0.9rem;
        padding: 0.4rem 1rem;
        border-radius: 6px;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        border-color: #22d3ee;
        color: #22d3ee;
        background-color: rgba(34, 211, 238, 0.05);
    }
</style>
""", unsafe_allow_html=True)

# --- 2. DATA MAPPING (YAHOO FORMAT) ---
STOCK_MAP = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "META": "Meta Platforms", "BRK-B": "Berkshire Hathaway",
    "TSLA": "Tesla", "AVGO": "Broadcom", "TSM": "TSMC", "LLY": "Eli Lilly",
    "WMT": "Walmart", "JPM": "JPMorgan Chase", "V": "Visa", "UNH": "UnitedHealth",
    "JNJ": "Johnson & Johnson", "MA": "Mastercard", "PG": "Procter & Gamble",
    "HD": "Home Depot", "NFLX": "Netflix", "BABA": "Alibaba", "XOM": "Exxon Mobil",
    "CVX": "Chevron", "TM": "Toyota", "BAC": "Bank of America", "MRK": "Merck & Co",
    "PEP": "PepsiCo", "KO": "Coca-Cola", "ABBV": "AbbVie", "ORCL": "Oracle",
    "ADBE": "Adobe", "CRM": "Salesforce", "CSCO": "Cisco", "AMD": "AMD",
    "QCOM": "Qualcomm", "INTC": "Intel", "AMGN": "Amgen", "PFE": "Pfizer",
    "ASML": "ASML", "NVO": "Novo Nordisk", "MCD": "McDonalds", "TMO": "Thermo Fisher",
    "MU": "Micron Tech", "SNDK": "SanDisk", "DNA": "Ginkgo Bioworks", 
    "SANA": "Sana Biotech", "NIO": "NIO Inc"
}

CRYPTO_MAP = {
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "Binance Coin",
    "XRP-USD": "XRP", "SOL-USD": "Solana", "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin",
    "TRX-USD": "TRON", "LINK-USD": "Chainlink", "DOT-USD": "Polkadot",
    "MATIC-USD": "Polygon", "LTC-USD": "Litecoin", "SHIB-USD": "Shiba Inu",
    "AVAX-USD": "Avalanche", "DAI-USD": "Dai", "UNI-USD": "Uniswap",
    "ATOM-USD": "Cosmos", "XMR-USD": "Monero", "ETC-USD": "Ethereum Classic",
    "XLM-USD": "Stellar", "BCH-USD": "Bitcoin Cash", "FIL-USD": "Filecoin",
    "NEAR-USD": "NEAR Protocol", "QNT-USD": "Quant", "APE-USD": "ApeCoin",
    "HBAR-USD": "Hedera", "ICP-USD": "Internet Computer", "AAVE-USD": "Aave",
    "EOS-USD": "EOS", "EGLD-USD": "MultiversX", "SAND-USD": "The Sandbox",
    "THETA-USD": "Theta Network", "AXS-USD": "Axie Infinity", "MANA-USD": "Decentraland",
    "XTZ-USD": "Tezos", "CHZ-USD": "Chiliz", "ZEC-USD": "Zcash", "BSV-USD": "Bitcoin SV"
}

COMMODITY_MAP = {
    "GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum", "PA=F": "Palladium",
    "HG=F": "Copper", "CL=F": "Crude Oil", "BZ=F": "Brent Crude",
    "NG=F": "Natural Gas", "RB=F": "Gasoline", "HO=F": "Heating Oil",
    "ZC=F": "Corn", "ZW=F": "Wheat", "ZS=F": "Soybeans",
    "KC=F": "Coffee", "SB=F": "Sugar", "CC=F": "Cocoa", "CT=F": "Cotton"
}

# --- 3. INDICATOR LOGIC ---

def calculate_smma(series, length):
    return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    if target_col == 'hl2':
        src = (df['High'] + df['Low']) / 2
    else:
        src = df[target_col]

    fast = calculate_smma(src, 16)
    mid = calculate_smma(src, 26)
    slow = calculate_smma(src, 34)

    f, m, s, p = fast, mid, slow, src
    is_bull = (f > m) & (m > s) & (p > f)
    is_bear = (f < m) & (m < s) & (p < f)
    return is_bull, is_bear

def get_gambit_signal(df):
    len_val = 16
    alpha_fast = 3.5 / (len_val + 1)
    alpha_slow = 2.0 / (len_val + 1)
    
    tl1 = df['Low'].ewm(alpha=alpha_fast, adjust=False).mean()
    tl = df['Low'].ewm(alpha=alpha_slow, adjust=False).mean()
    tl3 = tl - tl1
    tl4 = tl3.rolling(8).rank(pct=True)
    tl5 = (tl3 < 0) & (tl4 > 0.75)
    l = np.where(tl5, tl, tl1)
    l_series = pd.Series(l, index=df.index)

    th1 = df['High'].ewm(alpha=alpha_fast, adjust=False).mean()
    th = df['High'].ewm(alpha=alpha_slow, adjust=False).mean()
    th3 = th1 - th
    th4 = th3.rolling(8).rank(pct=True)
    th5 = (th3 > 0) & (th4 < 0.25)
    h = np.where(th5, th, th1)
    h_series = pd.Series(h, index=df.index)

    prev_close = df['Close'].shift(1)
    prev_l = l_series.shift(1)
    is_ucru = (prev_close < prev_l) & (df['Close'] > l_series) & (df['Close'] < h_series) & (df['Close'] > df['Open'])
    rev_up = is_ucru.shift(1) & (df['Close'] > df['High'].shift(1))
    is_ur = (df['Close'] < h_series) & (df['Close'] < prev_close) & (df['Close'].shift(2) > h_series.shift(2))
    return rev_up, is_ur

# --- 4. THE YAHOO TURBO SCANNER ---
def fetch_single_ticker(args):
    ticker, name, asset_type, spy_subset, is_market_closed_today = args
    try:
        # Fetch Data (1y is plenty)
        df = yf.Ticker(ticker).history(period="1y")
        
        if df is None or df.empty: return None
        if len(df) < 50: return None
        
        # Yahoo data logic
        target_df = df.copy()
        
        # If market is Open, last row is live. Drop it for confirmed daily close.
        # Crypto is 24/7 so we keep it.
        if asset_type != "Crypto" and not is_market_closed_today:
             target_df = target_df.iloc[:-1]

        # --- SIGNALS ---
        bull_series, bear_series = get_ae_signal(target_df, 'hl2')
        rev_up_series, rev_down_series = get_gambit_signal(target_df)
        
        today_bull = bull_series.iloc[-1]
        today_bear = bear_series.iloc[-1]
        gambit_buy = rev_up_series.iloc[-1]
        gambit_sell = rev_down_series.iloc[-1]
        
        trend_status = "Neutral ⚪"
        if today_bull: trend_status = "Bullish 🟢"
        elif today_bear: trend_status = "Bearish 🔴"
        
        gambit_status = "—"
        if gambit_buy: gambit_status = "🟢 BUY (Reversal)"
        elif gambit_sell: gambit_status = "🔴 SELL (Pivot)"
        
        confluence_text = "⚪ Neutral"
        
        if today_bull:
            if gambit_buy:
                confluence_text = "🚀 STRONG BUY"
            elif gambit_sell:
                confluence_text = "⚠️ PULLBACK"
            else:
                confluence_text = "📈 Trending Up"
        elif today_bear:
            if gambit_sell:
                confluence_text = "⬇️ STRONG SELL"
            elif gambit_buy:
                confluence_text = "🔥 REVERSAL"
            else:
                confluence_text = "📉 Trending Down"
        
        yest_bull = bull_series.iloc[-2]
        yest_bear = bear_series.iloc[-2]
        is_flip = False
        flip_text = ""
        
        if today_bull and not yest_bull:
            is_flip = True
            flip_text = "Bull Flip 🟢"
        elif today_bear and not yest_bear:
            is_flip = True
            flip_text = "Bear Flip 🔴"
        elif gambit_buy:
            is_flip = True
            flip_text = "Gambit Buy 🔥"

        # Benchmark Logic (Simplified for speed in Yahoo mode)
        common_idx = target_df.index.intersection(spy_subset.index)
        if len(common_idx) > 20:
            aligned_stock = target_df.loc[common_idx]['Close']
            aligned_bench = spy_subset.loc[common_idx]['Close']
            ratio = aligned_stock / aligned_bench
            
            ratio_df = pd.DataFrame({'ratio': ratio})
            r_bull, r_bear = get_ae_signal(ratio_df, 'ratio')
            rs_status = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"
        else:
            rs_status = "—"

        # Link logic
        clean_ticker = ticker.replace("=F", "")
        tv_link_ticker = ticker
        if asset_type == "Crypto": 
            tv_link_ticker = "BINANCE:" + ticker.replace("-USD", "USDT")
        else:
            tv_link_ticker = clean_ticker
            
        return {
            "Company": name, 
            "Ticker": clean_ticker,
            "Price": f"${target_df['Close'].iloc[-1]:.2f}",
            "Trend (vs USD)": trend_status,
            "Trend (vs SPY)" if asset_type != "Crypto" else "Trend (vs BTC)": rs_status,
            "Gambit Reversals": gambit_status,
            "Confluence": confluence_text,
            "Action": f"https://www.tradingview.com/chart/?symbol={tv_link_ticker}",
            "is_flip": is_flip,
            "flip_type": flip_text
        }
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner="Turbo Scanning Markets...") 
def scan_market(tickers_map, benchmark_symbol, asset_type="Stock"):
    tz_ny = pytz.timezone('US/Eastern')
    now_ny = datetime.now(tz_ny)
    
    market_cutoff_hour = 16
    is_market_closed_today = now_ny.hour >= market_cutoff_hour

    # Fetch Benchmark once
    bench_ticker = yf.Ticker(benchmark_symbol)
    bench_hist = bench_ticker.history(period="1y")
    
    display_date = bench_hist.index[-1].strftime('%b %d, %Y')
    
    spy_subset = bench_hist.copy()
    if asset_type != "Crypto" and not is_market_closed_today:
        spy_subset = spy_subset.iloc[:-1]

    tasks = []
    for ticker, name in tickers_map.items():
        tasks.append((ticker, name, asset_type, spy_subset, is_market_closed_today))
    
    results = []
    # --- TURBO MODE: 20 WORKERS ---
    with ThreadPoolExecutor(max_workers=20) as executor:
        processed = list(executor.map(fetch_single_ticker, tasks))
    results = [p for p in processed if p is not None]

    return pd.DataFrame(results), display_date

col_left, col_right = st.columns([3, 1])
with col_left:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot v2.0 (Turbo)") # <--- VERSION STAMP
with col_right:
    st.markdown("""<div class="status-container"><div class="status-text">● Turbo Online</div></div>""", unsafe_allow_html=True)
    if st.button("Refresh Data", key="refresh_top"):
        st.cache_data.clear()
        st.rerun()

st.write("") 
st.markdown("""<style>.stDataFrame { width: 100%; }</style>""", unsafe_allow_html=True)

def highlight_rows(row):
    val = row.get('Confluence', '')
    if "STRONG BUY" in val: return ['background-color: #06402B'] * len(row) 
    if "STRONG SELL" in val: return ['background-color: #4a0f0f'] * len(row) 
    if "REVERSAL" in val: return ['background-color: #5c4d00'] * len(row) 
    if "PULLBACK" in val: return ['background-color: #5c2b00'] * len(row)
    if "Trending Up" in val: return ['background-color: #1b4d3e'] * len(row)
    if "Trending Down" in val: return ['background-color: #4d1b1b'] * len(row)
    return [''] * len(row)

tab_stocks, tab_coins, tab_commodities, tab_flips = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️", "⚡ NEW FLIPS"])

def get_col_config(asset_type):
    bench_name = "Trend (vs BTC)" if asset_type == "Crypto" else "Trend (vs SPY)"
    return {
        "is_flip": None, 
        "flip_type": None, 
        "Action": st.column_config.LinkColumn("Chart"),
        "Trend (vs USD)": st.column_config.TextColumn("Trend (vs USD)", help="The asset's absolute price trend. \n🟢 Bullish: Price > Moving Averages\n🔴 Bearish: Price < Moving Averages"),
        bench_name: st.column_config.TextColumn(bench_name, help=f"Relative Strength vs {bench_name.split()[-1]}.\n🟢 Bullish: Outperforming the market.\n🔴 Bearish: Underperforming the market."),
        "Gambit Reversals": st.column_config.TextColumn("Gambit Reversals", help="✨ REVERSAL SIGNALS:\n🟢 BUY: Price dipped below support & recovered (Buy the Dip).\n🔴 SELL: Price hit resistance ceiling & rejected.\n—: No signal today."),
        "Confluence": st.column_config.TextColumn("Confluence", help="The Final Verdict:\n🚀 STRONG BUY: Bull Trend + Gambit Buy\n⬇️ STRONG SELL: Bear Trend + Gambit Sell\n⚠️ PULLBACK: Bull Trend + Gambit Sell\n🔥 REVERSAL: Bear Trend + Gambit Buy")
    }

with tab_stocks:
    df_stocks, stock_date = scan_market(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Data Date: **{stock_date}**")
    st.dataframe(df_stocks.style.apply(highlight_rows, axis=1), column_config=get_col_config("Stock"), hide_index=True, use_container_width=False, height=1200)

with tab_coins:
    df_crypto, crypto_date = scan_market(CRYPTO_MAP, "BTC-USD", "Crypto")
    st.caption(f"📅 Data Date: **{crypto_date}**")
    st.dataframe(df_crypto.style.apply(highlight_rows, axis=1), column_config=get_col_config("Crypto"), hide_index=True, use_container_width=False, height=1200)

with tab_commodities:
    df_comm, comm_date = scan_market(COMMODITY_MAP, "SPY", "Commodity")
    st.caption(f"📅 Data Date: **{comm_date}**")
    st.dataframe(df_comm.style.apply(highlight_rows, axis=1), column_config=get_col_config("Commodity"), hide_index=True, use_container_width=False, height=1200)

with tab_flips:
    st.caption("⚡ Assets that triggered a Signal or Flip TODAY")
    all_flips = []
    if 'df_stocks' in locals() and not df_stocks.empty: all_flips.append(df_stocks[df_stocks['is_flip'] == True].copy())
    if 'df_crypto' in locals() and not df_crypto.empty: all_flips.append(df_crypto[df_crypto['is_flip'] == True].copy())
    if 'df_comm' in locals() and not df_comm.empty: all_flips.append(df_comm[df_comm['is_flip'] == True].copy())
    
    if all_flips:
        df_flips = pd.concat(all_flips, ignore_index=True)
        cols = ['Company', 'Ticker', 'flip_type', 'Trend (vs USD)', 'Gambit Reversals', 'Confluence', 'Price', 'Action']
        cols = [c for c in cols if c in df_flips.columns]
        
        flips_config = get_col_config("Stock") 
        flips_config["flip_type"] = st.column_config.TextColumn("Trigger Event", help="What caused this asset to appear here (e.g., Trend Flip or Gambit Signal).")
        
        st.dataframe(
            df_flips[cols].style.apply(highlight_rows, axis=1),
            column_config=flips_config,
            hide_index=True, use_container_width=False
        )
    else:
        st.info("No trend flips or gambit signals detected today.")
