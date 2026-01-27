import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from datetime import datetime
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
    /* Tab 2 (Coins): Bitcoin Orange */
    button[data-baseweb="tab"]:nth-of-type(2) div p {
        color: #F7931A !important;
    }
    /* Tab 4 (New Flips - moved to end): Bright Yellow/Gold */
    button[data-baseweb="tab"]:nth-of-type(4) div p {
        color: #FFD700 !important;
    }
    
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

# --- 2. DATA MAPPING ---
STOCK_MAP = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "META": "Meta Platforms", "BRK.B": "Berkshire Hathaway",
    "TSLA": "Tesla", "AVGO": "Broadcom", "TSM": "TSMC", "LLY": "Eli Lilly",
    "WMT": "Walmart", "JPM": "JPMorgan Chase", "V": "Visa", "UNH": "UnitedHealth",
    "JNJ": "Johnson & Johnson", "MA": "Mastercard", "PG": "Procter & Gamble",
    "HD": "Home Depot", "NFLX": "Netflix", "BABA": "Alibaba", "XOM": "Exxon Mobil",
    "CVX": "Chevron", "TM": "Toyota", "BAC": "Bank of America", "MRK": "Merck & Co",
    "PEP": "PepsiCo", "KO": "Coca-Cola", "ABBV": "AbbVie", "ORCL": "Oracle",
    "ADBE": "Adobe", "CRM": "Salesforce", "CSCO": "Cisco", "AMD": "AMD",
    "QCOM": "Qualcomm", "INTC": "Intel", "AMGN": "Amgen", "PFE": "Pfizer",
    "ASML": "ASML", "NVO": "Novo Nordisk", "MCD": "McDonalds", "TMO": "Thermo Fisher"
}

CRYPTO_MAP = {
    "BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "BNBUSDT": "Binance Coin",
    "XRPUSDT": "XRP", "SOLUSDT": "Solana", "TRXUSDT": "TRON", "DOGEUSDT": "Dogecoin",
    "ADAUSDT": "Cardano", "BCHUSDT": "Bitcoin Cash", "XMRUSDT": "Monero",
    "LINKUSDT": "Chainlink", "LEOUSDT": "LEO", "HYPEUSDT": "Hyperliquid",
    "XLMUSDT": "Stellar", "ZECUSDT": "Zcash", "CCUSDT": "Canton", "SUIUSDT": "Sui",
    "LTCUSDT": "Litecoin", "AVAXUSDT": "Avalanche", "TONUSDT": "Toncoin",
    "CROUSDT": "Cronos", "DOTUSDT": "Polkadot", "UNIUSDT": "Uniswap",
    "MNTUSDT": "Mantle", "BGBUSDT": "Bitget", "TAOUSDT": "Bittensor",
    "AAVEUSDT": "Aave", "OKBUSDT": "OKB", "PEPEUSDT": "Pepe", "NEARUSDT": "NEAR",
    "ICPUSDT": "Internet Comp", "ETCUSDT": "Ethereum Classic", "FILUSDT": "Filecoin",
    "QNTUSDT": "Quant", "VETUSDT": "VeChain", "CHZUSDT": "Chiliz", "XTZUSDT": "Tezos",
    "CAKEUSDT": "PancakeSwap", "NEXOUSDT": "Nexo", "ZROUSDT": "LayerZero",
    "OPUSDT": "Optimism", "STXUSDT": "Stacks", "DASHUSDT": "Dash",
    "XDCUSDT": "XDC Network", "AMPUSDT": "Amp", "APEUSDT": "ApeCoin",
    "DYDXUSDT": "dYdX", "SNXUSDT": "Synthetix", "1INCHUSDT": "1inch", "ARUSDT": "Arweave"
}

COMMODITY_MAP = {
    "GLD": "Gold", "SLV": "Silver", "PPLT": "Platinum", "PALL": "Palladium",
    "CPER": "Copper", "JJU": "Aluminum", "JJN": "Nickel", "USO": "Crude Oil WTI", 
    "BNO": "Crude Oil Brent", "UNG": "Natural Gas", "UGA": "Gasoline RBOB", 
    "UHN": "Heating Oil", "URA": "Uranium ETF", "ZC1!": "Corn", "ZW1!": "Wheat", 
    "ZS1!": "Soybeans", "JO": "Coffee", "CANE": "Sugar"
}

# --- 3. INDICATOR LOGIC ---

def calculate_smma(series, length):
    return series.ewm(alpha=1/length, adjust=False).mean()

# --- TREND STRATEGY (AE) ---
def get_ae_signal(df, target_col='hl2'):
    if target_col == 'hl2':
        src = (df['high'] + df['low']) / 2
    else:
        src = df[target_col]

    fast = calculate_smma(src, 16)
    mid = calculate_smma(src, 26)
    slow = calculate_smma(src, 34)

    f, m, s, p = fast, mid, slow, src

    is_bull = (f > m) & (m > s) & (p > f)
    is_bear = (f < m) & (m < s) & (p < f)
    
    return is_bull, is_bear

# --- GAMBIT STRATEGY (Reversal) ---
def get_gambit_signal(df):
    len_val = 16
    alpha_fast = 3.5 / (len_val + 1)
    alpha_slow = 2.0 / (len_val + 1)
    
    # Low Line
    tl1 = df['low'].ewm(alpha=alpha_fast, adjust=False).mean()
    tl = df['low'].ewm(alpha=alpha_slow, adjust=False).mean()
    tl3 = tl - tl1
    tl4 = tl3.rolling(8).rank(pct=True)
    tl5 = (tl3 < 0) & (tl4 > 0.75)
    l = np.where(tl5, tl, tl1)
    l_series = pd.Series(l, index=df.index)

    # High Line
    th1 = df['high'].ewm(alpha=alpha_fast, adjust=False).mean()
    th = df['high'].ewm(alpha=alpha_slow, adjust=False).mean()
    th3 = th1 - th
    th4 = th3.rolling(8).rank(pct=True)
    th5 = (th3 > 0) & (th4 < 0.25)
    h = np.where(th5, th, th1)
    h_series = pd.Series(h, index=df.index)

    # Unconfirmed Reversal
    prev_close = df['close'].shift(1)
    prev_l = l_series.shift(1)
    is_ucru = (prev_close < prev_l) & (df['close'] > l_series) & (df['close'] < h_series) & (df['close'] > df['open'])
    
    # Confirmed Reversal (Buy)
    rev_up = is_ucru.shift(1) & (df['close'] > df['high'].shift(1))
    
    # Bearish Pivot (Sell)
    # Simplify for stability: Rejection from High line
    is_ur = (df['close'] < h_series) & (df['close'] < prev_close) & (df['close'].shift(2) > h_series.shift(2))
    
    return rev_up, is_ur

@st.cache_resource
def get_tv_instance():
    return TvDatafeed()

# --- 4. THE PARALLEL SCANNER ---
def fetch_single_ticker(args):
    ticker, name, asset_type, spy_subset, is_market_closed_today, use_last_row, tv = args
    try:
        exchange = 'NASDAQ' 
        if "USDT" in ticker: exchange = 'BINANCE'
        if ticker in ["ZC1!", "ZW1!", "ZS1!"]: exchange = "CBOT"
        
        df = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_daily, n_bars=100)
        if df is None: df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
        if df is None: df = tv.get_hist(symbol=ticker, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
        
        if df is None or df.empty: return None

        target_df = df.copy()
        if not use_last_row:
            target_df = target_df.iloc[:-1]

        if len(target_df) < 50: return None

        # --- SIGNALS ---
        bull_series, bear_series = get_ae_signal(target_df, 'hl2')
        rev_up_series, rev_down_series = get_gambit_signal(target_df)
        
        # Last Candle Values
        today_bull = bull_series.iloc[-1]
        today_bear = bear_series.iloc[-1]
        gambit_buy = rev_up_series.iloc[-1]
        gambit_sell = rev_down_series.iloc[-1]
        
        # --- COL 1: TREND STATUS ---
        trend_status = "2. Neutral ⚪"
        if today_bull: trend_status = "1. Bullish 🟢"
        elif today_bear: trend_status = "3. Bearish 🔴"
        
        # --- COL 2: GAMBIT STATUS ---
        gambit_status = "⚪"
        if gambit_buy: gambit_status = "🟢 BUY (Reversal)"
        elif gambit_sell: gambit_status = "🔴 SELL (Pivot)"
        
        # --- CONFLUENCE CHECK (For row coloring) ---
        confluence_score = 0
        if today_bull and gambit_buy: confluence_score = 2
        elif today_bear and gambit_sell: confluence_score = -2
        elif not today_bull and gambit_buy: confluence_score = 1 # Reversal against trend
        
        # --- FLIP DETECTION ---
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

        # Benchmark
        aligned_df = target_df['close'].to_frame(name='stock').join(spy_subset['close'].to_frame(name='spy')).dropna()
        aligned_df['ratio'] = aligned_df['stock'] / aligned_df['spy']
        rs_bull, rs_bear = get_ae_signal(aligned_df, 'ratio')
        
        bench_col = "Trend (vs BTC)" if asset_type == "Crypto" else "Trend (vs SPY)"
        rs_status = "1. Bullish 🟢" if rs_bull.iloc[-1] else "3. Bearish 🔴" if rs_bear.iloc[-1] else "2. Neutral ⚪"

        return {
            "Company": name, 
            "Ticker": ticker.replace("1!", ""),
            "Price": f"${target_df['close'].iloc[-1]:.2f}",
            "Trend (Dir)": trend_status,
            "Gambit (Rev)": gambit_status,
            bench_col: rs_status,
            "Action": f"https://www.tradingview.com/chart/?symbol={ticker}",
            "is_flip": is_flip,
            "flip_type": flip_text,
            "score": confluence_score
        }
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner="Analyzing Market Data...") 
def scan_market(tickers_map, benchmark_symbol, asset_type="Stock"):
    tv = get_tv_instance()
    tz_ny = pytz.timezone('US/Eastern')
    now_ny = datetime.now(tz_ny)
    
    market_cutoff_hour = 16
    if asset_type == "Crypto": market_cutoff_hour = 19
    is_market_closed_today = now_ny.hour >= market_cutoff_hour

    bench_exchange = 'AMEX' if "SPY" in benchmark_symbol else 'BINANCE'
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange=bench_exchange, interval=Interval.in_daily, n_bars=100)
    
    last_candle_date = spy_data.index[-1].date()
    today_date_ny = now_ny.date()
    
    # Logic to drop live candle
    spy_subset = spy_data
    use_last_row = True
    display_date = spy_data.index[-1].strftime('%b %d, %Y')
    
    if asset_type == "Crypto":
        if not is_market_closed_today:
             spy_subset = spy_data.iloc[:-1]
             display_date = spy_data.index[-2].strftime('%b %d, %Y')
             use_last_row = False
    else:
        if last_candle_date == today_date_ny and not is_market_closed_today:
             spy_subset = spy_data.iloc[:-1]
             display_date = spy_data.index[-2].strftime('%b %d, %Y')
             use_last_row = False

    tasks = []
    for ticker, name in tickers_map.items():
        tasks.append((ticker, name, asset_type, spy_subset, is_market_closed_today, use_last_row, tv))
    
    results = []
    # --- STABLE MODE: 4 WORKERS (The Proven Setting) ---
    with ThreadPoolExecutor(max_workers=4) as executor:
        processed = list(executor.map(fetch_single_ticker, tasks))
    results = [p for p in processed if p is not None]

    return pd.DataFrame(results), display_date

# --- 5. THE HEADER LAYOUT ---
col_left, col_right = st.columns([3, 1])
with col_left:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot")
with col_right:
    st.markdown("""<div class="status-container"><div class="status-text">● System Online</div></div>""", unsafe_allow_html=True)
    if st.button("Refresh Data", key="refresh_top"):
        st.cache_data.clear()
        st.rerun()

st.write("") 

# --- 6. DISPLAY LOGIC ---
st.markdown("""<style>.stDataFrame { width: 100%; }</style>""", unsafe_allow_html=True)

def highlight_rows(row):
    # Highlight logic based on our split columns
    s = row.get('score', 0)
    if s == 2: return ['background-color: #06402B'] * len(row) # Strong Buy (Trend+Rev)
    elif s == -2: return ['background-color: #4a0f0f'] * len(row) # Strong Sell
    elif s == 1: return ['background-color: #5c4d00'] * len(row) # Reversal Warning
    
    # Default Trend Colors if no confluence
    trend = row.get('Trend (Dir)', '')
    if "Bullish" in trend: return ['background-color: #1b4d3e'] * len(row)
    elif "Bearish" in trend: return ['background-color: #4d1b1b'] * len(row)
    
    return [''] * len(row)

# TABS: FLIPS IS NOW LAST
tab_stocks, tab_coins, tab_commodities, tab_flips = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️", "⚡ NEW FLIPS"])

# Define hidden columns for main views
hidden_cols = {
    "is_flip": None, 
    "flip_type": None, 
    "score": None,
    "Action": st.column_config.LinkColumn("Chart")
}

with tab_stocks:
    df_stocks, stock_date = scan_market(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Data Date: **{stock_date}**")
    st.dataframe(
        df_stocks.style.apply(highlight_rows, axis=1),
        column_config=hidden_cols,
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_coins:
    df_crypto, crypto_date = scan_market(CRYPTO_MAP, "BTCUSDT", "Crypto")
    st.caption(f"📅 Data Date: **{crypto_date}**")
    st.dataframe(
        df_crypto.style.apply(highlight_rows, axis=1),
        column_config=hidden_cols,
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_commodities:
    df_comm, comm_date = scan_market(COMMODITY_MAP, "SPY", "Commodity")
    st.caption(f"📅 Data Date: **{comm_date}**")
    st.dataframe(
        df_comm.style.apply(highlight_rows, axis=1),
        column_config=hidden_cols,
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_flips:
    st.caption("⚡ Assets that triggered a Signal or Flip TODAY")
    
    all_flips = []
    if 'df_stocks' in locals() and not df_stocks.empty:
        all_flips.append(df_stocks[df_stocks['is_flip'] == True].copy())
    if 'df_crypto' in locals() and not df_crypto.empty:
        all_flips.append(df_crypto[df_crypto['is_flip'] == True].copy())
    if 'df_comm' in locals() and not df_comm.empty:
        all_flips.append(df_comm[df_comm['is_flip'] == True].copy())
    
    if all_flips:
        df_flips = pd.concat(all_flips, ignore_index=True)
        # For Flips tab, we show the "flip_type" but still hide the boolean "is_flip"
        cols = ['Company', 'Ticker', 'flip_type', 'Trend (Dir)', 'Gambit (Rev)', 'Price', 'Action', 'score']
        # Filter columns if they exist
        cols = [c for c in cols if c in df_flips.columns]
        
        st.dataframe(
            df_flips[cols].style.apply(highlight_rows, axis=1),
            column_config={
                "Action": st.column_config.LinkColumn("Chart"),
                "flip_type": st.column_config.TextColumn("Trigger Event"),
                "score": None # Hide score
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No trend flips or gambit signals detected today.")
