import streamlit as st
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from datetime import datetime, time
import pytz

st.set_page_config(layout="wide", page_title="Confluence Pro")

# --- 1. CONFIGURATION ---
# Define Market Close times (in Eastern Time)
STOCK_CLOSE_HOUR = 16  # 4:00 PM ET
CRYPTO_CLOSE_HOUR = 19 # 7:00 PM ET (Approx UTC midnight)

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
    "GC1!": "Gold", "SI1!": "Silver", "PL1!": "Platinum", "PA1!": "Palladium",
    "HG1!": "Copper", "ALI1!": "Aluminum", "NI1!": "Nickel", "ZNC1!": "Zinc",
    "CL1!": "Crude Oil WTI", "BZ1!": "Crude Oil Brent", "NG1!": "Natural Gas",
    "RB1!": "Gasoline RBOB", "HO1!": "Heating Oil", "UX1!": "Uranium Index",
    "URA": "Uranium ETF Proxy", "ZC1!": "Corn", "ZW1!": "Wheat",
    "ZS1!": "Soybeans", "KC1!": "Coffee", "SB1!": "Sugar"
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
@st.cache_data(ttl=3600, show_spinner="Analyzing Market Data...") # Cache for 1 hour to allow checking close status
def scan_market(tickers_map, benchmark_symbol, asset_type="Stock"):
    tv = get_tv_instance()
    results = []
    
    # 1. Determine Market Status (Time in New York)
    tz_ny = pytz.timezone('US/Eastern')
    now_ny = datetime.now(tz_ny)
    
    # Logic: If it is before 4:00 PM ET, we consider TODAY as "Open/Incomplete"
    # If it is after 4:00 PM ET, we consider TODAY as "Closed/Complete"
    market_cutoff_hour = STOCK_CLOSE_HOUR
    if asset_type == "Crypto":
        market_cutoff_hour = CRYPTO_CLOSE_HOUR # Different rule for crypto if needed, though usually 24/7
        
    is_market_closed_today = now_ny.hour >= market_cutoff_hour

    # Get Benchmark
    bench_exchange = 'AMEX' if "SPY" in benchmark_symbol else 'BINANCE'
    spy_data = tv.get_hist(symbol=benchmark_symbol, exchange=bench_exchange, interval=Interval.in_daily, n_bars=100)
    
    # --- SMART CANDLE SELECTION ---
    # We look at the timestamp of the LAST candle from TradingView
    last_candle_date = spy_data.index[-1].date()
    today_date = now_ny.date()
    
    # If the feed gives us a candle dated TODAY:
    if last_candle_date == today_date:
        if not is_market_closed_today:
            # It's today, but market isn't closed -> It's a live/fake candle. DROP IT.
            spy_subset = spy_data.iloc[:-1]
            display_date = spy_data.index[-2].strftime('%b %d, %Y')
            use_last_row = False
        else:
            # It's today, and market IS closed -> It's the fresh close. KEEP IT.
            spy_subset = spy_data
            display_date = spy_data.index[-1].strftime('%b %d, %Y')
            use_last_row = True
    else:
        # The feed hasn't updated to today yet (or it's weekend), so the last candle is definitely closed.
        spy_subset = spy_data
        display_date = spy_data.index[-1].strftime('%b %d, %Y')
        use_last_row = True

    progress_bar = st.progress(0, text=f"Scanning {asset_type} ({display_date})...")
    total = len(tickers_map)

    for i, (ticker, name) in enumerate(tickers_map.items()):
        try:
            exchange = 'NASDAQ' 
            if "USDT" in ticker: exchange = 'BINANCE'
            if "1!" in ticker: exchange = 'COMEX' 
            
            if ticker in ["CL1!", "NG1!", "RB1!", "HO1!", "BZ1!", "PL1!", "PA1!"]: exchange = "NYMEX"
            if ticker in ["ZC1!", "ZW1!", "ZS1!"]: exchange = "CBOT"
            if ticker in ["KC1!", "SB1!"]: exchange = "ICEUS"
            if ticker == "HG1!": exchange = "COMEX"
            
            df = tv.get_hist(symbol=ticker, exchange=exchange, interval=Interval.in_daily, n_bars=100)
            if df is None and exchange == 'NASDAQ': 
                df = tv.get_hist(symbol=ticker, exchange='NYSE', interval=Interval.in_daily, n_bars=100)
            
            if df is not None and not df.empty:
                # Apply the same "Drop Logic" to the individual stock/coin
                if not use_last_row:
                    df = df.iloc[:-1]

                trend_signal = get_ae_signal(df, 'hl2')
                
                # Rel Strength
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

# --- 5. THE UI ---
st.title("🎯 Confluence.bot Pro")

with st.sidebar:
    st.write("### ⚙️ System Status")
    if st.button("🔄 Force New Daily Scan"):
        st.cache_data.clear()
        st.rerun()
    st.info("System uses NY Time (ET) to determine if the daily candle is closed.")

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
