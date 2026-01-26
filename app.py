import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from datetime import datetime, date

st.set_page_config(layout="wide", page_title="Confluence Pro")

# --- 1. DATA MAPPING (Names & Tickers) ---
# We map tickers to friendly names for the UI
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

# --- 3. THE SCANNER ---
@st.cache_data(ttl=86400, show_spinner="Analyzing Market Data...")
def scan_market(tickers, benchmark_symbol, asset_type="Stock"):
    tv = get_tv_instance()
    results = []
    
    # Benchmark Data
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='AMEX', interval=Interval.in_daily, n_bars=100)
    if spy_data is None:
        spy_data = tv.get_hist(symbol=benchmark_symbol, exchange='BINANCE', interval=Interval.in_daily, n_bars=100)
    
    # Date Handling
    last_dt = spy_data.index[-1].date()
    today = date.today()
    
    # Logic: If the candle date is today, it's LIVE. If it's earlier, it's CLOSED.
    # Note: For crypto, this will likely return 'today', meaning it's a live candle.
    if last_dt == today:
        date_label = f"{last_dt.strftime('%b %d, %Y')} (Live Action 🔴)"
    else:
        date_label = f"{last_dt.strftime('%b %d, %Y')} (Market Close 🏁)"

    progress_bar = st.progress(0, text=f"Scanning {asset_type}...")
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
                
                # Rel Strength (Ratio Logic)
                aligned_df = df['close'].to_frame(name='stock').join(spy_data['close'].to_frame(name='spy')).dropna()
                aligned_df['ratio'] = aligned_df['stock'] / aligned_df['spy']
                rs_signal = get_ae_signal(aligned_df, 'ratio')
                
                # Look up Name
                if asset_type == "Stock":
                    name = STOCK_MAP.get(ticker, ticker)
                    col_order = ["Company", "Ticker", "Price", "Trend (vs USD)", "Trend (vs SPY)", "Chart"]
                else:
                    name = CRYPTO_MAP.get(ticker, ticker)
                    col_order = ["Name", "Ticker", "Price", "Trend (vs USD)", "Trend (vs BTC)", "Chart"]

                row = {
                    "Company": name, # Used for Stocks
                    "Name": name,    # Used for Coins
                    "Ticker": ticker,
                    "Price": f"${df['close'].iloc[-1]:.2f}",
                    "Trend (vs USD)": trend_signal,
                    "Chart": f"https://www.tradingview.com/chart/?symbol={ticker}"
                }
                
                # Dynamic Column Naming based on Asset
                if asset_type == "Stock":
                    row["Trend (vs SPY)"] = rs_signal
                else:
                    row["Trend (vs BTC)"] = rs_signal
                
                results.append(row)
        except Exception:
            pass
            
        progress_bar.progress((i + 1) / total)
        
    progress_bar.empty()
    
    # Return ordered dataframe
    df_final = pd.DataFrame(results)
    # Filter only columns that exist (handles the different Trend column names)
    final_cols = [c for c in col_order if c in df_final.columns]
    return df_final[final_cols], date_label

# --- 4. THE UI ---
st.title("🎯 Confluence.bot Pro")

with st.sidebar:
    st.write("### ⚙️ System Status")
    if st.button("🔄 Force New Daily Scan"):
        st.cache_data.clear()
        st.rerun()
    st.info("System optimizes for daily close data. Click refresh to force a live update.")

st.markdown("""<style>.stDataFrame { width: 100%; }</style>""", unsafe_allow_html=True)

def highlight_rows(row):
    # Find the trend columns dynamically
    trend_cols = [c for c in row.index if "Trend" in c]
    if len(trend_cols) < 2: return [''] * len(row)
    
    t1 = row[trend_cols[0]] # vs USD
    t2 = row[trend_cols[1]] # vs Bench
    
    if "Bullish" in t1 and "Bullish" in t2:
        return ['background-color: #1b4d3e'] * len(row)
    elif "Bearish" in t1 and "Bearish" in t2:
        return ['background-color: #4d1b1b'] * len(row)
    else:
        return [''] * len(row)

tab_stocks, tab_coins, tab_commodities = st.tabs(["Stocks 📈", "Coins 🪙", "Commodities 🛢️"])

with tab_stocks:
    df_stocks, stock_date = scan_market(list(STOCK_MAP.keys()), "SPY", "Stock")
    st.caption(f"📅 Data Snapshot: {stock_date}")
    
    st.dataframe(
        df_stocks.style.apply(highlight_rows, axis=1),
        column_config={"Chart": st.column_config.LinkColumn("Action")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_coins:
    df_crypto, crypto_date = scan_market(list(CRYPTO_MAP.keys()), "BTCUSDT", "Crypto")
    st.caption(f"📅 Data Snapshot: {crypto_date}")
    
    st.dataframe(
        df_crypto.style.apply(highlight_rows, axis=1),
        column_config={"Chart": st.column_config.LinkColumn("Action")},
        hide_index=True,
        use_container_width=True,
        height=1200
    )

with tab_commodities:
    st.info("🚧 Commodities data coming in v2.1")
