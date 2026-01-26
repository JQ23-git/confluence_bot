import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

st.set_page_config(layout="wide", page_title="Confluence Pro")

# --- 1. SESSION STATE SETUP (The Memory Fix) ---
if 'stock_data' not in st.session_state:
    st.session_state.stock_data = None
if 'crypto_data' not in st.session_state:
    st.session_state.crypto_data = None

# --- 2. THE ENGINE (Logic) ---
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

    # Get latest values
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

def scan_market(tickers, benchmark_symbol="SPY"):
    tv = get_tv_instance()
    results = []
    
    # Progress Bar UI
    progress_text = "Operation in progress. Please wait."
    my_bar = st.progress(0, text=progress_text)
    
    # Get Benchmark Data
    # Try AMEX first (for SPY), fallback to BINANCE (for BTCUSDT)
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
    if spy_data is None:
        spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='BINANCE', interval=Interval.in_daily, n_bars=100)

    total = len(tickers)
    for i, ticker in enumerate(tickers):
        try:
            # Smart Exchange Selection
            exchange = 'NASDAQ'
            # If it ends in USDT, it's crypto -> use Binance
            if ticker.endswith("USDT"): 
                exchange = 'BINANCE'
            
            df = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_daily, n_bars=100)
            
            # Fallback for stocks
            if df is None and exchange == 'NASDAQ': 
                df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
            
            if df is not None and not df.empty:
                trend_signal = get_ae_signal(df, 'hl2')
                
                # Relative Strength Calculation
                # Join with benchmark to align dates
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
        except Exception as e:
            # Silent fail for individual tickers to keep scan running
            pass
            
        my_bar.progress((i + 1) / total, text=f"Scanning {ticker}...")
        
    my_bar.empty()
    return pd.DataFrame(results)

# --- 3. THE UI ---
st.title("🎯 Confluence.bot Pro")

# CSS for full width/height tables
st.markdown("""
<style>
    .stDataFrame { width: 100%; }
</style>
""", unsafe_allow_html=True)

tab_stocks, tab_coins, tab_commodities = st.tabs(["Stocks 📈", "Coins 🪙", "Commodities 🛢️"])

# Helper for coloring rows
def highlight_rows(row):
    trend = row["Trend (vs USD)"]
    rs = row["Rel Strength (vs Bench)"]
    if "Bullish" in trend and "Bullish" in rs:
        return ['background-color: #1b4d3e'] * len(row) # Dark Green
    elif "Bearish" in trend and "Bearish" in rs:
        return ['background-color: #4d1b1b'] * len(row) # Dark Red
    else:
        return [''] * len(row)

# --- TAB: STOCKS ---
with tab_stocks:
    st.header("US Equities Radar (vs SPY)")
    
    if st.button("Run Stock Scan 🚀", key="btn_stocks"):
        stock_list = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK.B", "TSLA", 
            "AVGO", "TSM", "LLY", "WMT", "JPM", "V", "UNH", "JNJ", "MA", 
            "PG", "HD", "NFLX", "BABA", "XOM", "CVX", "TM", "BAC", "MRK", 
            "PEP", "KO", "ABBV", "ORCL", "ADBE", "CRM", "CSCO", "AMD", 
            "QCOM", "INTC", "AMGN", "PFE", "ASML", "NVO", "MCD", "TMO"
        ]
        st.session_state.stock_data = scan_market(stock_list, "SPY")

    if st.session_state.stock_data is not None:
        st.dataframe(
            st.session_state.stock_data.style.apply(highlight_rows, axis=1),
            column_config={"Action": st.column_config.LinkColumn("Chart")},
            hide_index=True,
            use_container_width=True,
            height=1200
        )

# --- TAB: COINS ---
with tab_coins:
    st.header("Crypto Radar (vs BTC)")
    
    if st.button("Run Crypto Scan 🪙", key="btn_crypto"):
        # The Top 50 List (Converted to USDT pairs for data feed)
        crypto_list = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT", "DOGEUSDT", 
            "ADAUSDT", "BCHUSDT", "XMRUSDT", "LINKUSDT", "LEOUSDT", "HYPEUSDT", "XLMUSDT", 
            "ZECUSDT", "CCUSDT", "SUIUSDT", "LTCUSDT", "AVAXUSDT", "TONUSDT", "CROUSDT", 
            "DOTUSDT", "UNIUSDT", "MNTUSDT", "BGBUSDT", "TAOUSDT", "AAVEUSDT", "OKBUSDT", 
            "PEPEUSDT", "NEARUSDT", "ICPUSDT", "ETCUSDT", "FILUSDT", "QNTUSDT", "VETUSDT", 
            "CHZUSDT", "XTZUSDT", "CAKEUSDT", "NEXOUSDT", "ZROUSDT", "OPUSDT", "STXUSDT", 
            "DASHUSDT", "XDCUSDT", "AMPUSDT", "APEUSDT", "DYDXUSDT", "SNXUSDT", "1INCHUSDT", 
            "ARUSDT"
        ]
        # Benchmark is BTCUSDT
        st.session_state.crypto_data = scan_market(crypto_list, "BTCUSDT")

    if st.session_state.crypto_data is not None:
        st.dataframe(
            st.session_state.crypto_data.style.apply(highlight_rows, axis=1),
            column_config={"Action": st.column_config.LinkColumn("Chart")},
            hide_index=True,
            use_container_width=True,
            height=1200
        )

# --- TAB: COMMODITIES ---
with tab_commodities:
    st.info("🚧 Commodities data coming in v2.1")
