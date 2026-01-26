import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from datetime import datetime
import pytz
from PIL import Image
import os

# --- 1. CONFIG & STYLE ---
st.set_page_config(layout="wide", page_title="confluence.bot", page_icon="🎯")

# PRO CSS: Hides default header, tightens layout, styles the dataframe
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Remove huge whitespace at top */
    .block-container {
        padding-top: 0rem;
        padding-bottom: 1rem;
    }
    
    /* Make the sidebar look like a pro nav bar */
    [data-testid="stSidebar"] {
        border-right: 1px solid #333;
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

# --- 3. THE ENGINE ---
def calculate_smma(series, length):
    return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    if target_col == 'hl2':
        src = (df['high'] + df['low']) / 2
    else:
        src = df[target_col]

    fast = calculate_smma(src, 16)
    mid = calculate_smma(src, 26)
    slow = calculate_smma(src, 34)

    f, m, s, p = fast.iloc[-1], mid.iloc[-1], slow.iloc[-1], src.iloc[-1]

    is_bull = (f > m) and (m > s) and (p > f)
    is_bear = (f < m) and (m < s) and (p < f)

    if is_bull:
        return "Bullish 🟢"
    elif is_bear:
        return "Bearish 🔴"
    else:
        return "Neutral ⚪"

@st.cache_resource
def get_tv_instance():
    return TvDatafeed()

# --- 4. THE SCANNER ---
@st.cache_data(ttl=3600, show_spinner="Analyzing Market Data...") 
def scan_market(tickers_map, benchmark_symbol, asset_type="Stock"):
    tv = get_tv_instance()
    results = []
    
    tz_ny = pytz.timezone('US/Eastern')
    now_ny = datetime.now(tz_ny)
    
    market_cutoff_hour = 16
    if asset_type == "Crypto":
        market_cutoff_hour = 19
        
    is_market_closed_today = now_ny.hour >= market_cutoff_hour

    bench_exchange = 'AMEX' if "SPY" in benchmark_symbol else 'BINANCE'
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange=bench_exchange, interval=Interval.in_daily, n_bars=100)
    
    last_candle_date = spy_data.index[-1].date()
    today_date = now_ny.date()
    
    if last_candle_date == today_date:
        if not is_market_closed_today:
            spy_subset = spy_data.iloc[:-1] 
            display_date = spy_data.index[-2].strftime('%b %d, %Y')
            use_last_row = False
        else:
            spy_subset = spy_data 
            display_date = spy_data.index[-1].strftime('%b %d, %Y')
            use_last_row = True
    else:
        spy_subset = spy_data
        display_date = spy_data.index[-1].strftime('%b %d, %Y')
        use_last_row = True

    progress_bar = st.progress(0, text=f"Scanning {asset_type} ({display_date})...")
    total = len(tickers_map)

    for i, (ticker, name) in enumerate(tickers_map.items()):
        try:
            exchange = 'NASDAQ' 
            if "USDT" in ticker: exchange = 'BINANCE'
            if ticker in ["ZC1!", "ZW1!", "ZS1!"]: exchange = "CBOT"
            
            df = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_daily, n_bars=100)
            if df is None: 
                df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
            if df is None:
                df = tv.get_hist(symbol=ticker, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
            
            if df is not None and not df.empty:
                if not use_last_row:
                    df = df.iloc[:-1]

                trend_signal = get_ae_signal(df, 'hl2')
                
                aligned_df = df['close'].to_frame(name='stock').join(spy_subset['close'].to_frame(name='spy')).dropna()
                aligned_df['ratio'] = aligned_df['stock'] / aligned_df['spy']
                rs_signal = get_ae_signal(aligned_df, 'ratio')
                
                if asset_type == "Crypto":
                    bench_col = "Trend (vs BTC)"
                else:
                    bench_col = "Trend (vs SPY)"

                row = {
                    "Company": name, 
                    "Ticker": ticker.replace("1!", ""),
                    "Price": f"${df['close'].iloc[-1]:.2f}",
                    "Trend (vs USD)": trend_signal,
                    bench_col: rs_signal,
                    "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"
                }
                results.append(row)
        except Exception:
            pass
            
        progress_bar.progress((i + 1) / total)
        
    progress_bar.empty()
    return pd.DataFrame(results), display_date

# --- 5. THE PRO UI LAYOUT ---

# A. SIDEBAR (The Navigation & Logo Area)
with st.sidebar:
    # 1. Logo at Top Left (Standard SaaS placement)
    if os.path.exists("logo.png"):
        # Width=220 keeps it crisp on Retina displays
        st.image("logo.png", width=220)
    else:
        st.write("## confluence.bot")
        
    st.write("---")
    
    # 2. Controls
    st.caption("SYSTEM CONTROLS")
    if st.button("🔄 Force Refresh Data"):
        st.cache_data.clear()
        st.rerun()
        
    st.write("")
    st.info("🟢 **System Online**\n\nData optimized for NY Market Close.")

# B. MAIN AREA (Clean & Data-First)
st.markdown("""<style>.stDataFrame { width: 100%; }</style>""", unsafe_allow_html=True)

def highlight_rows(row):
    trend_cols = [c for c in row.index if "Trend" in c]
    if len(trend_cols) < 2: return [''] * len(row)
    t1 = row[trend_cols[0]]
    t2 = row[trend_cols[1]]
    
    if "Bullish" in t1 and "Bullish" in t2:
        return ['background-color: #1b4d3e'] * len(row)
    elif "Bearish" in t1 and "Bearish" in t2:
        return ['background-color: #4d1b1b'] * len(row)
    else:
        return [''] * len(row)

# TABS (Top of Main Area)
tab_stocks, tab_coins, tab_commodities = st.tabs(["Stocks 📈", "Coins 🪙", "Commodities 🛢️"])

with tab_stocks:
    df_stocks, stock_date = scan_market(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Confirmed Daily Close: **{stock_date}**")
    st.dataframe(
        df_stocks.style.apply(highlight_rows, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_coins:
    df_crypto, crypto_date = scan_market(CRYPTO_MAP, "BTCUSDT", "Crypto")
    st.caption(f"📅 Confirmed Daily Close: **{crypto_date}**")
    st.dataframe(
        df_crypto.style.apply(highlight_rows, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_commodities:
    df_comm, comm_date = scan_market(COMMODITY_MAP, "SPY", "Commodity")
    st.caption(f"📅 Confirmed Daily Close: **{comm_date}**")
    st.dataframe(
        df_comm.style.apply(highlight_rows, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )
# Force Logo Upload
