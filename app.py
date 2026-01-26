import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import datetime

st.set_page_config(layout="wide", page_title="Confluence Pro")

# --- 1. THE ENGINE (Logic) ---
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

# --- 2. THE SCANNER (24-Hour Vault) ---
# TTL = 86400 seconds (24 Hours). It locks the data for a full day.
@st.cache_data(ttl=86400, show_spinner="Fetching Daily Close Data...")
def scan_market(tickers, benchmark_symbol, asset_type="Stock"):
    tv = get_tv_instance()
    results = []
    
    # 1. Get Benchmark & Date
    # We grab the benchmark first to establish the "As Of" date
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
    if spy_data is None:
        spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='BINANCE', interval=Interval.in_daily, n_bars=100)
    
    # Extract the date of the last candle
    last_date = spy_data.index[-1].strftime('%b %d, %Y')

    # UI Feedback
    progress_bar = st.progress(0, text=f"Analyzing {asset_type} Close Data...")
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        try:
            exchange = 'NASDAQ'
            if ticker.endswith("USDT"): exchange = 'BINANCE'
            
            df = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_daily, n_bars=100)
            if df is None and exchange == 'NASDAQ': 
                df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
            
            if df is not None and not df.empty:
                trend_signal = get_ae_signal(df, 'hl2')
                
                # Rel Strength
                aligned_df = df['close'].to_frame(name='stock').join(spy_data['close'].to_frame(name='spy')).dropna()
                aligned_df['ratio'] = aligned_df['stock'] / aligned_df['spy']
                rs_signal = get_ae_signal(aligned_df, 'ratio')
                
                results.append({
                    "Ticker": ticker,
                    "Price": f"${df['close'].iloc[-1]:.2f}",
                    "Trend (vs USD)": trend_signal,
                    "Rel Strength (vs Bench)": rs_signal,
                    "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"
                })
        except Exception:
            pass
            
        progress_bar.progress((i + 1) / total)
        
    progress_bar.empty()
    # Returns TWO things now: The Dataframe AND the Date string
    return pd.DataFrame(results), last_date

# --- 3. DATA LISTS ---
STOCK_LIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK.B", "TSLA", 
    "AVGO", "TSM", "LLY", "WMT", "JPM", "V", "UNH", "JNJ", "MA", 
    "PG", "HD", "NFLX", "BABA", "XOM", "CVX", "TM", "BAC", "MRK", 
    "PEP", "KO", "ABBV", "ORCL", "ADBE", "CRM", "CSCO", "AMD", 
    "QCOM", "INTC", "AMGN", "PFE", "ASML", "NVO", "MCD", "TMO"
]

CRYPTO_LIST = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT", "DOGEUSDT", 
    "ADAUSDT", "BCHUSDT", "XMRUSDT", "LINKUSDT", "LEOUSDT", "HYPEUSDT", "XLMUSDT", 
    "ZECUSDT", "CCUSDT", "SUIUSDT", "LTCUSDT", "AVAXUSDT", "TONUSDT", "CROUSDT", 
    "DOTUSDT", "UNIUSDT", "MNTUSDT", "BGBUSDT", "TAOUSDT", "AAVEUSDT", "OKBUSDT", 
    "PEPEUSDT", "NEARUSDT", "ICPUSDT", "ETCUSDT", "FILUSDT", "QNTUSDT", "VETUSDT", 
    "CHZUSDT", "XTZUSDT", "CAKEUSDT", "NEXOUSDT", "ZROUSDT", "OPUSDT", "STXUSDT", 
    "DASHUSDT", "XDCUSDT", "AMPUSDT", "APEUSDT", "DYDXUSDT", "SNXUSDT", "1INCHUSDT", 
    "ARUSDT"
]

# --- 4. THE UI ---
st.title("🎯 Confluence.bot Pro")

# Sidebar
with st.sidebar:
    st.write("### ⚙️ System Status")
    if st.button("🔄 Force New Daily Scan"):
        st.cache_data.clear()
        st.rerun()
    st.info("System scans the daily close once every 24 hours. Data is stored in RAM.")

st.markdown("""<style>.stDataFrame { width: 100%; }</style>""", unsafe_allow_html=True)

def highlight_rows(row):
    trend = row["Trend (vs USD)"]
    rs = row["Rel Strength (vs Bench)"]
    if "Bullish" in trend and "Bullish" in rs:
        return ['background-color: #1b4d3e'] * len(row)
    elif "Bearish" in trend and "Bearish" in rs:
        return ['background-color: #4d1b1b'] * len(row)
    else:
        return [''] * len(row)

tab_stocks, tab_coins, tab_commodities = st.tabs(["Stocks 📈", "Coins 🪙", "Commodities 🛢️"])

with tab_stocks:
    # 1. Fetch Data (Hits Cache if available)
    df_stocks, stock_date = scan_market(STOCK_LIST, "SPY", "Stocks")
    
    # 2. Show Date Header
    st.caption(f"📅 Data Snapshot: Market Close of **{stock_date}**")
    
    # 3. Show Table
    st.dataframe(
        df_stocks.style.apply(highlight_rows, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_coins:
    df_crypto, crypto_date = scan_market(CRYPTO_LIST, "BTCUSDT", "Crypto")
    st.caption(f"📅 Data Snapshot: Daily Close of **{crypto_date}**")
    
    st.dataframe(
        df_crypto.style.apply(highlight_rows, axis=1),
        column_config={"Action": st.column_config.LinkColumn("Chart")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_commodities:
    st.info("🚧 Commodities data coming in v2.1")
