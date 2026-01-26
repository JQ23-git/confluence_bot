import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
from tvDatafeed import TvDatafeed, Interval
from lightweight_charts.widgets import StreamlitChart

# --- 1. PAGE SETUP ---
st.set_page_config(layout="wide", page_title="Confluence.bot V1")
st.title("🏹 Confluence.bot V1")

tv = TvDatafeed()

st.sidebar.header("Settings")
ticker = st.sidebar.text_input("Ticker", value="BTCUSD")
exchange = st.sidebar.text_input("Exchange", value="BINANCE")
n_bars = st.sidebar.slider("Number of Candles", 100, 1000, 300)

# --- 2. DATA & LOGIC ---
@st.cache_data(ttl=3600)
def fetch_and_calc(ticker, exchange, n_bars):
    df = tv.get_hist(symbol=ticker, exchange=exchange,
                     interval=Interval.in_daily, n_bars=n_bars)
    if df is None: return None
    
    df = df.reset_index()
    df.columns = df.columns.str.lower()
    
    # Calculate Indicators
    df['ema9'] = ta.ema(df['close'], length=9)
    df['sma16'] = ta.sma(df['close'], length=16)
    df['prev_high'] = df['high'].shift(1)
    df['is_gold'] = df['ema9'] > df['sma16']
    df['pink_triangle'] = (df['close'] > df['prev_high']) & (df['is_gold'])
    
    # Clean time for JSON
    df['time'] = df['datetime'].dt.strftime('%Y-%m-%d')
    
    # Keep only clean columns (No Timestamps)
    cols = ['time', 'open', 'high', 'low', 'close', 'volume', 'ema9', 'sma16', 'pink_triangle', 'is_gold']
    return df[cols].copy()

data = fetch_and_calc(ticker, exchange, n_bars)

# --- 3. SIDEBAR SCOREBOARD ---
if data is not None:
    st.sidebar.markdown("---")
    st.sidebar.header("Live Scoreboard")
    
    current_gold = data['is_gold'].iloc[-1]
    status_color = "green" if current_gold else "red"
    st.sidebar.markdown(f"**Trend Status:** :{status_color}[{'GOLD ZONE' if current_gold else 'NEUTRAL'}]")
    
    signals = data[data['pink_triangle'] == True]
    if not signals.empty:
        last_sig_date = signals['time'].iloc[-1]
        st.sidebar.info(f"Last Gambit Signal: {last_sig_date}")

# --- 4. CHART DISPLAY ---
if data is not None:
    chart = StreamlitChart(width=1100, height=600)
    
    # Set Candle Data
    chart.set(data[['time', 'open', 'high', 'low', 'close', 'volume']]) 
    
    # THE "NUCLEAR" FIX: Create lines WITHOUT 'name' to avoid column matching errors
    line_ema = chart.create_line(color='rgba(255, 215, 0, 0.8)')
    line_ema.set(data[['time', 'ema9']].rename(columns={'ema9': 'value'}))
    
    line_sma = chart.create_line(color='rgba(0, 150, 255, 0.8)')
    line_sma.set(data[['time', 'sma16']].rename(columns={'sma16': 'value'}))

    # Add markers
    gambit_signals = data[data['pink_triangle'] == True]
    for _, row in gambit_signals.iterrows():
        chart.marker(time=row['time'], shape='arrowUp', color='magenta')

    chart.load() 
else:
    st.error("No data found.")
