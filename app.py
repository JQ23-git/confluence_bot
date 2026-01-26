import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

st.set_page_config(layout="wide", page_title="Confluence Pro")

# --- 1. SESSION STATE SETUP (The Memory Fix) ---
# This ensures data survives when you switch tabs
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
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
    # Fallback for crypto benchmark if AMEX fails (e.g. using BTCUSDT)
    if spy_data is None:
        spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='BINANCE', interval=Interval.in_daily, n_bars=100)

    total = len(tickers)
    for i, ticker in enumerate(tickers):
        try:
            # Smart Exchange Selection
            exchange = 'NASDAQ'
            if "USDT" in ticker: exchange = 'BINANCE'
            
            df = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_daily, n_bars=100)
            if df is None: 
                df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
            
            if df is not None and not df.empty:
                trend_signal = get_ae_signal(df, 'hl2')
                
                # Relative Strength Calculation
                aligned_df = df['close'].to_frame(name='stock').join(spy_data['close'].to_frame(name='spy')).dropna()
                aligned_df['ratio'] = aligned_df['stock'] / aligned_df['spy']
                rs_signal = get_ae_signal(aligned_df, 'ratio')
                
                results.append({
                    "Ticker": ticker,
                    "Price": f"${df['close'].iloc[-1]:.2f}",
                    "Trend (vs USD)": trend_signal,
                    "Rel Strength (vs Benchmark)": rs_signal,
                    "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"
                })
        except Exception as e:
            print(f"Skipping {ticker}: {e}")
            
        my_bar.progress((i + 1) / total, text=f"Scanning {ticker}...")
        
    my_bar.empty()
    return pd.DataFrame(results)

# --- 3. THE UI ---
st.title("🎯 Confluence.bot Pro")

# Custom CSS to make the table look less like an iframe
st.markdown("""
<style>
    .stDataFrame { width: 100%; }
</style>
""", unsafe_allow_html=True)

tab_stocks, tab_coins, tab_commodities = st.tabs(["Stocks 📈", "Coins 🪙", "Commodities 🛢️"])

# Helper function for coloring
def highlight_rows(row):
    trend = row["Trend (vs USD)"]
    rs = row["Rel Strength (vs Benchmark)"]
    if "Bullish" in trend and "Bullish" in rs:
        return ['background-color: #1b4d3e'] * len(row) # Dark Green
    elif "Bearish" in trend and "Bearish" in rs:
        return ['background-color: #4d1b1b'] * len(row) # Dark Red
    else:
        return [''] * len(row)

with tab_stocks:
    st.header("US Equities Radar")
    
    # 1. The Trigger
    if st.button("Run Stock Scan 🚀", key="btn_stocks"):
        stock_list = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK.B", "TSLA", 
            "AVGO", "TSM", "LLY", "WMT", "JPM", "V", "UNH", "JNJ", "MA", 
            "PG", "HD", "NFLX", "BABA", "XOM", "CVX", "TM", "BAC", "MRK", 
            "PEP", "KO", "ABBV", "ORCL", "ADBE", "CRM", "CSCO", "AMD", 
            "QCOM", "INTC", "AMGN", "PFE", "ASML", "NVO", "MCD", "TMO"
        ]
        # Save to Session State
        st.session_state.stock_data = scan_market(stock_list, "SPY")

    # 2. The Display (Checks Memory)
    if st.session_state.stock_data is not None:
        st.dataframe(
            st.session_state.stock_data.style.apply(highlight_rows, axis=1),
            column_config={"Action": st.column_config.LinkColumn("Chart")},
            hide_index=True,
            use_container_width=True,
            height=1200  # <--- This fixes the "tiny box" look
        )

with tab_coins:
    st.header("Crypto Radar")
    
    if st.button("Run Crypto Scan 🪙", key="btn_crypto"):
        # Save to Session State
        st.session_state.crypto_data = scan_market(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"], "BTCUSDT")

    if st.session_state.crypto_data is not None:
        st.dataframe(
            st.session_state.crypto_data.style.apply(highlight_rows, axis=1),
            column_config={"Action": st.column_config.LinkColumn("Chart")},
            hide_index=True,
            use_container_width=True,
            height=500
        )

with tab_commodities:
    st.info("🚧 Commodities data coming in v2.1")
