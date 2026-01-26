import streamlit as st
import pandas as pd
from tvdatafeed import TvDatafeed, Interval

st.set_page_config(layout="wide", page_title="Confluence Pro")

# --- 1. THE ENGINE (Logic Translation) ---
def calculate_smma(series, length):
    """Calculates Smoothed Moving Average (equivalent to Pine Script logic)"""
    return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    """
    Applies the Allocation Engine Trend Logic:
    Fast(16) > Mid(26) > Slow(34) -> Bullish
    Fast(16) < Mid(26) < Slow(34) -> Bearish
    """
    # Create HL2 if it doesn't exist (High + Low) / 2
    if target_col == 'hl2':
        src = (df['high'] + df['low']) / 2
    else:
        src = df[target_col]

    # Calculate SMMAs
    fast = calculate_smma(src, 16)
    mid = calculate_smma(src, 26)
    slow = calculate_smma(src, 34)

    # Get the latest values (last closed bar)
    f, m, s, p = fast.iloc[-1], mid.iloc[-1], slow.iloc[-1], src.iloc[-1]

    # Logic Checks
    is_bull = (f > m) and (m > s) and (p > f)
    is_bear = (f < m) and (m < s) and (p < f)

    if is_bull:
        return "Bullish 🟢"
    elif is_bear:
        return "Bearish 🔴"
    else:
        return "Neutral ⚪"

# --- 2. DATA FETCHING ---
@st.cache_resource
def get_tv_instance():
    return TvDatafeed()

def scan_market(tickers, benchmark_symbol="SPY"):
    tv = get_tv_instance()
    results = []
    
    # Get Benchmark Data first (SPY)
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
    
    # Progress Bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(tickers)
    for i, ticker in enumerate(tickers):
        status_text.text(f"Scanning {ticker}...")
        try:
            # 1. Get Stock Data
            df = tv.get_hist(symbol=ticker, exchange='NASDAQ', interval=Interval.in_daily, n_bars=100)
            if df is None: # Try NYSE if NASDAQ fails
                df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
            
            if df is not None and not df.empty:
                # 2. Calculate Trend (Stock vs USD)
                trend_signal = get_ae_signal(df, 'hl2')
                
                # 3. Calculate RS (Stock vs SPY)
                # Align dates just in case
                aligned_df = df['close'].to_frame(name='stock').join(spy_data['close'].to_frame(name='spy')).dropna()
                aligned_df['ratio'] = aligned_df['stock'] / aligned_df['spy']
                
                rs_signal = get_ae_signal(aligned_df, 'ratio')
                
                results.append({
                    "Ticker": ticker,
                    "Price": f"${df['close'].iloc[-1]:.2f}",
                    "Trend (vs USD)": trend_signal,
                    "Rel Strength (vs SPY)": rs_signal,
                    "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"
                })
        except Exception as e:
            print(f"Failed {ticker}: {e}")
            
        progress_bar.progress((i + 1) / total)
        
    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(results)

# --- 3. THE UI ---
st.title("🎯 Confluence.bot Pro")
st.markdown("### Allocation Engine: Daily Trend Scanner")

# Tabs
tab_stocks, tab_coins, tab_commodities = st.tabs(["Stocks 📈", "Coins 🪙", "Commodities 🛢️"])

with tab_stocks:
    st.header("US Equities Radar")
    
    # The Filtered List (No International)
    stock_list = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK.B", "TSLA", 
        "AVGO", "TSM", "LLY", "WMT", "JPM", "V", "UNH", "JNJ", "MA", 
        "PG", "HD", "NFLX", "BABA", "XOM", "CVX", "TM", "BAC", "MRK", 
        "PEP", "KO", "ABBV", "ORCL", "ADBE", "CRM", "CSCO", "AMD", 
        "QCOM", "INTC", "AMGN", "PFE", "ASML", "NVO", "MCD", "TMO"
    ]
    
    if st.button("Run Stock Scan 🚀"):
        df_stocks = scan_market(stock_list, "SPY")
        
        # Color coding function
        def highlight_rows(row):
            trend = row["Trend (vs USD)"]
            rs = row["Rel Strength (vs SPY)"]
            
            # Gold (Green) Row if BOTH are Bullish
            if "Bullish" in trend and "Bullish" in rs:
                return ['background-color: #1b4d3e'] * len(row) # Dark Green
            # Red Row if BOTH are Bearish
            elif "Bearish" in trend and "Bearish" in rs:
                return ['background-color: #4d1b1b'] * len(row) # Dark Red
            else:
                return [''] * len(row)

        st.dataframe(
            df_stocks.style.apply(highlight_rows, axis=1),
            column_config={
                "Action": st.column_config.LinkColumn("Chart")
            },
            hide_index=True,
            use_container_width=True
        )

with tab_coins:
    st.header("Crypto Radar (BTC/ETH)")
    if st.button("Run Crypto Scan 🪙"):
        # Quick Crypto Scan
        crypto_df = scan_market(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "BTCUSDT") # Comparing vs BTC as benchmark
        st.dataframe(crypto_df, use_container_width=True)

with tab_commodities:
    st.info("🚧 Commodities data coming in v2.1")

