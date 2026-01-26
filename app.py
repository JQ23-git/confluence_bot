import streamlit as st
import pandas as pd

st.set_page_config(page_title="Confluence Bot", layout="wide")

st.title("🎯 Confluence.bot Scoreboard")
st.write("Scanner active: Daily (Crypto) | Weekly/Daily (Stocks)")

# This is our logic blueprint for the dashboard
data = {
    'Ticker': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AAPL', 'TSLA'],
    'Timeframe': ['Daily', 'Daily', 'Daily', 'Weekly', 'Weekly'],
    'Relative Strength': ['🟡 Gold Flip', '🔵 Blue', '🟡 Gold Flip', '🟢 Bullish', '🟡 Gold Flip'],
    'Vs. Benchmark': ['BTC', 'BTC', 'BTC', 'SPY', 'SPY'],
    'Action': [
        '[Open Chart](https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT&interval=D)',
        '[Open Chart](https://www.tradingview.com/chart/?symbol=BINANCE:ETHUSDT&interval=D)',
        '[Open Chart](https://www.tradingview.com/chart/?symbol=BINANCE:SOLUSDT&interval=D)',
        '[Open Chart](https://www.tradingview.com/chart/?symbol=NASDAQ:AAPL&interval=W)',
        '[Open Chart](https://www.tradingview.com/chart/?symbol=NASDAQ:TSLA&interval=W)'
    ]
}

df = pd.DataFrame(data)

# Display the scoreboard as a clean table
st.table(df)

st.info("💡 Note: The 'Open Chart' links will open the asset in the correct timeframe on TradingView.")
