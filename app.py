import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
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
    
    /* --- TAB STYLING --- */
    button[data-baseweb="tab"] div p {
        font-size: 18px !important;    
        font-weight: 700 !important;   
        letter-spacing: 0.5px !important;
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
STOCK_GROUPS = {
    "Tech & AI": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM", "SNDK"],
    "Cyber & Cloud": ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space": ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy": ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA", "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}

STOCK_MAP = {}
for category, tickers in STOCK_GROUPS.items():
    for t in tickers:
        STOCK_MAP[t] = t 

CRYPTO_MAP = {
    "2Z-USD": "DoubleZero",    "A7A5-USD": "A7A5",    "AAVE-USD": "Aave",    "AB-USD": "AB",
    "ADA-USD": "Cardano",    "AERO-USD": "Aerodrome Finance",    "ALGO-USD": "Algorand",    "APE-USD": "ApeCoin",
    "APT-USD": "Aptos",    "ARB-USD": "Arbitrum",    "ASTER-USD": "Aster",    "ATOM-USD": "Cosmos Hub",
    "AVAX-USD": "Avalanche",    "AXS-USD": "Axie Infinity",    "BCH-USD": "Bitcoin Cash",    "BDX-USD": "Beldex",
    "BFUSD-USD": "BFUSD",    "BGB-USD": "Bitget Token",    "BNB-USD": "BNB",    "BNSOL-USD": "Binance Staked SOL",
    "BONK-USD": "Bonk",    "BSC-USD-USD": "Binance Bridged USDT",    "BSV-USD": "Bitcoin SV",    "BTC-USD": "Bitcoin",
    "BTC.B-USD": "Avalanche Bridged BTC",    "BTT-USD": "BitTorrent",    "BUIDL-USD": "BlackRock USD Fund",    "CAKE-USD": "PancakeSwap",
    "CBBTC-USD": "Coinbase Wrapped BTC",    "CC-USD": "Canton",    "CFX-USD": "Conflux",    "CHZ-USD": "Chiliz",
    "CLBTC-USD": "clBTC",    "CRO-USD": "Cronos",    "CRV-USD": "Curve DAO",    "CRVUSD-USD": "crvUSD",
    "CTM-USD": "c8ntinuum",    "CUSD-USD": "Cap USD",    "DAI-USD": "Dai",    "DASH-USD": "Dash",
    "DCR-USD": "Decred",    "DOGE-USD": "Dogecoin",    "DOT-USD": "Polkadot",    "EETH-USD": "ether.fi Staked ETH",
    "EGLD-USD": "MultiversX",    "ENA-USD": "Ethena",    "ENS-USD": "Ethereum Name Service",    "EOS-USD": "EOS",
    "ETC-USD": "Ethereum Classic",    "ETH-USD": "Ethereum",    "ETHFI-USD": "Ether.fi",    "ETHX-USD": "Stader ETHx",
    "EURC-USD": "EURC",    "EUTBL-USD": "Spiko EU T-Bills",    "EZETH-USD": "Renzo Restaked ETH",    "FARTCOIN-USD": "Fartcoin",
    "FBTC-USD": "Function FBTC",    "FDUSD-USD": "First Digital USD",    "FET-USD": "Artificial Superintelligence",    "FIGR_HELOC-USD": "Figure Heloc",
    "FIL-USD": "Filecoin",    "FLOKI-USD": "FLOKI",    "FLR-USD": "Flare",    "FTN-USD": "Fasttoken",
    "GHO-USD": "GHO",    "GNO-USD": "Gnosis",    "GRT-USD": "The Graph",    "GT-USD": "Gate",
    "GTETH-USD": "GTETH",    "H-USD": "Humanity",    "HASH-USD": "Provenance Blockchain",    "HBAR-USD": "Hedera",
    "HTX-USD": "HTX DAO",    "HYPE-USD": "Hyperliquid",    "ICP-USD": "Internet Computer",    "INJ-USD": "Injective",
    "IOTA-USD": "IOTA",    "IP-USD": "Story",    "JAAA-USD": "Janus Henderson AAA",    "JASMY-USD": "JasmyCoin",
    "JITOSOL-USD": "Jito Staked SOL",    "JLP-USD": "Jupiter LP",    "JST-USD": "JUST",    "JTRSY-USD": "Janus Henderson Treasury",
    "JUP-USD": "Jupiter",    "JUPSOL-USD": "Jupiter Staked SOL",    "KAG-USD": "Kinesis Silver",    "KAIA-USD": "Kaia",
    "KAS-USD": "Kaspa",    "KAU-USD": "Kinesis Gold",    "KCS-USD": "KuCoin",    "KHYPE-USD": "Kinetiq Staked HYPE",
    "LBTC-USD": "Lombard Staked BTC",    "LDO-USD": "Lido DAO",    "LEO-USD": "LEO Token",    "LINK-USD": "Chainlink",
    "LIQUIDETH-USD": "Ether.Fi Liquid ETH",    "LIT-USD": "Lighter",    "LSETH-USD": "Liquid Staked ETH",    "LTC-USD": "Litecoin",
    "M-USD": "MemeCore",    "MANA-USD": "Decentraland",    "MATIC-USD": "Polygon",    "METH-USD": "Mantle Staked Ether",
    "MNT-USD": "Mantle",    "MORPHO-USD": "Morpho",    "MSOL-USD": "Marinade Staked SOL",    "MYX-USD": "MYX Finance",
    "NEAR-USD": "NEAR Protocol",    "NEXO-USD": "NEXO",    "NFT-USD": "AINFT",    "NIGHT-USD": "Midnight",
    "OHM-USD": "Olympus",    "OKB-USD": "OKB",    "ONDO-USD": "Ondo",    "OP-USD": "Optimism",
    "OSETH-USD": "StakeWise Staked ETH",    "OUSG-USD": "OUSG",    "PAXG-USD": "PAX Gold",    "PENDLE-USD": "Pendle",
    "PENGU-USD": "Pudgy Penguins",    "PEPE-USD": "Pepe",    "PI-USD": "Pi Network",    "PIPPIN-USD": "pippin",
    "POL-USD": "POL (ex-MATIC)",    "PUMP-USD": "Pump.fun",    "PYTH-USD": "Pyth Network",    "PYUSD-USD": "PayPal USD",
    "QNT-USD": "Quant",    "RAIN-USD": "Rain",    "RENDER-USD": "Render",    "RIVER-USD": "River",
    "RLUSD-USD": "Ripple USD",    "RSETH-USD": "Kelp DAO Restaked ETH",    "SAND-USD": "The Sandbox",    "SBTC-USD": "sBTC",
    "SEI-USD": "Sei",    "SHIB-USD": "Shiba Inu",    "SKY-USD": "Sky",    "SOL-USD": "Solana",
    "SOLVBTC-USD": "Solv Protocol BTC",    "SPX-USD": "SPX6900",    "STABLE-USD": "​​Stable",    "STEAKUSDC-USD": "Steakhouse USDC",
    "STKAAVE-USD": "Staked Aave",    "STRK-USD": "Starknet",    "STX-USD": "Stacks",    "SUI-USD": "Sui",
    "SUN-USD": "Sun Token",    "SUSDE-USD": "Ethena Staked USDe",    "SUSDS-USD": "sUSDS",    "SYRUP-USD": "Maple Finance",
    "SYRUPUSDC-USD": "syrupUSDC",    "SYRUPUSDT-USD": "syrupUSDT",    "TAO-USD": "Bittensor",    "TBTC-USD": "tBTC",
    "TEL-USD": "Telcoin",    "THETA-USD": "Theta Network",    "TIA-USD": "Celestia",    "TON-USD": "Toncoin",
    "TRUMP-USD": "Official Trump",    "TRX-USD": "TRON",    "TWT-USD": "Trust Wallet",    "UBTC-USD": "Unit Bitcoin",
    "UDS-USD": "Undeads Games",    "UNI-USD": "Uniswap",    "USD0-USD": "Usual USD",    "USD1-USD": "USD1",
    "USDAI-USD": "USDai",    "USDB-USD": "USDB",    "USDC.E-USD": "Polygon Bridged USDC",    "USDE-USD": "Ethena USDe",
    "USDF-USD": "Falcon USD",    "USDG-USD": "Global Dollar",    "USDS-USD": "USDS",    "USDT0-USD": "USDT0",
    "USDTB-USD": "USDtb",    "USDY-USD": "Ondo US Dollar Yield",    "USR-USD": "Resolv USR",    "USTB-USD": "Superstate USTB",
    "USX-USD": "USX",    "USYC-USD": "Circle USYC",    "VET-USD": "VeChain",    "VIRTUAL-USD": "Virtuals Protocol",
    "WAPE-USD": "Wrapped ApeCoin",    "WBETH-USD": "Wrapped Beacon ETH",    "WBNB-USD": "Wrapped BNB",    "WBT-USD": "WhiteBIT Coin",
    "WEETH-USD": "Wrapped eETH",    "WFLR-USD": "Wrapped Flare",    "WIF-USD": "dogwifhat",    "WLD-USD": "Worldcoin",
    "WLFI-USD": "World Liberty Fin",    "WM-USD": "WrappedM by M0",    "WSTUSR-USD": "Resolv wstUSR",    "WSTX-USD": "Wrapped STX",
    "XAUT-USD": "Tether Gold",    "XDC-USD": "XDC Network",    "XLM-USD": "Stellar",    "XMR-USD": "Monero",
    "XRP-USD": "XRP",    "XTZ-USD": "Tezos",    "ZEC-USD": "Zcash",    "ZRO-USD": "LayerZero"
}

COMMODITY_MAP = {
    "GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum", "PA=F": "Palladium",
    "HG=F": "Copper", "CL=F": "Crude Oil", "BZ=F": "Brent Crude",
    "NG=F": "Natural Gas", "RB=F": "Gasoline", "HO=F": "Heating Oil",
    "ZC=F": "Corn", "ZW=F": "Wheat", "ZS=F": "Soybeans",
    "KC=F": "Coffee", "SB=F": "Sugar", "CC=F": "Cocoa", "CT=F": "Cotton"
}

# --- 3. INDICATOR LOGIC ---

def calculate_smma(series, length):
    return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    if target_col == 'hl2':
        src = (df['High'] + df['Low']) / 2
    else:
        src = df[target_col]

    fast = calculate_smma(src, 16)
    mid = calculate_smma(src, 26)
    slow = calculate_smma(src, 34)

    f, m, s, p = fast, mid, slow, src
    is_bull = (f > m) & (m > s) & (p > f)
    is_bear = (f < m) & (m < s) & (p < f)
    return is_bull, is_bear

def get_gambit_signal(df):
    len_val = 16
    alpha_fast = 3.5 / (len_val + 1)
    alpha_slow = 2.0 / (len_val + 1)
    
    tl1 = df['Low'].ewm(alpha=alpha_fast, adjust=False).mean()
    tl = df['Low'].ewm(alpha=alpha_slow, adjust=False).mean()
    tl3 = tl - tl1
    tl4 = tl3.rolling(8).rank(pct=True)
    tl5 = (tl3 < 0) & (tl4 > 0.75)
    l = np.where(tl5, tl, tl1)
    l_series = pd.Series(l, index=df.index)

    th1 = df['High'].ewm(alpha=alpha_fast, adjust=False).mean()
    th = df['High'].ewm(alpha=alpha_slow, adjust=False).mean()
    th3 = th1 - th
    th4 = th3.rolling(8).rank(pct=True)
    th5 = (th3 > 0) & (th4 < 0.25)
    h = np.where(th5, th, th1)
    h_series = pd.Series(h, index=df.index)

    prev_close = df['Close'].shift(1)
    prev_l = l_series.shift(1)
    is_ucru = (prev_close < prev_l) & (df['Close'] > l_series) & (df['Close'] < h_series) & (df['Close'] > df['open'])
    rev_up = is_ucru.shift(1) & (df['Close'] > df['High'].shift(1))
    is_ur = (df['Close'] < h_series) & (df['Close'] < prev_close) & (df['Close'].shift(2) > h_series.shift(2))
    return rev_up, is_ur

# --- 4. THE YAHOO TURBO SCANNER ---
def fetch_single_ticker(args):
    ticker, name, asset_type, spy_subset, is_market_closed_today = args
    try:
        df = yf.Ticker(ticker).history(period="1y")
        
        if df is None or df.empty: return None
        if len(df) < 50: return None
        
        target_df = df.copy()
        
        # --- MARKET OPEN LOGIC ---
        # If Stock market is Open, last row is live (drop it).
        # Crypto is 24/7, so last row is ALWAYS live (drop it).
        # This ensures we only see CONFIRMED Daily Closes for everything.
        if (asset_type == "Crypto") or (not is_market_closed_today):
             target_df = target_df.iloc[:-1]

        # --- SIGNALS ---
        bull_series, bear_series = get_ae_signal(target_df, 'hl2')
        rev_up_series, rev_down_series = get_gambit_signal(target_df)
        
        today_bull = bull_series.iloc[-1]
        today_bear = bear_series.iloc[-1]
        gambit_buy = rev_up_series.iloc[-1]
        gambit_sell = rev_down_series.iloc[-1]
        
        trend_status = "Neutral ⚪"
        if today_bull: trend_status = "Bullish 🟢"
        elif today_bear: trend_status = "Bearish 🔴"
        
        gambit_status = "—"
        if gambit_buy: gambit_status = "🟢 BUY (Reversal)"
        elif gambit_sell: gambit_status = "🔴 SELL (Pivot)"
        
        confluence_text = "⚪ Neutral"
        
        if today_bull:
            if gambit_buy:
                confluence_text = "🚀 STRONG BUY"
            elif gambit_sell:
                confluence_text = "⚠️ PULLBACK"
            else:
                confluence_text = "📈 Trending Up"
        elif today_bear:
            if gambit_sell:
                confluence_text = "⬇️ STRONG SELL"
            elif gambit_buy:
                confluence_text = "🔥 REVERSAL"
            else:
                confluence_text = "📉 Trending Down"
        
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

        common_idx = target_df.index.intersection(spy_subset.index)
        if len(common_idx) > 20:
            aligned_stock = target_df.loc[common_idx]['Close']
            aligned_bench = spy_subset.loc[common_idx]['Close']
            ratio = aligned_stock / aligned_bench
            
            ratio_df = pd.DataFrame({'ratio': ratio})
            r_bull, r_bear = get_ae_signal(ratio_df, 'ratio')
            
            rs_status = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"
        else:
            rs_status = "—"

        clean_ticker = ticker.replace("=F", "")
        tv_link_ticker = ticker
        if asset_type == "Crypto": 
            tv_link_ticker = "BINANCE:" + ticker.replace("-USD", "USDT")
        else:
            tv_link_ticker = clean_ticker

        return {
            "Company": name, 
            "Ticker": clean_ticker,
            "Price": f"${target_df['Close'].iloc[-1]:.2f}",
            "Trend (vs USD)": trend_status,
            "Trend (vs SPY)" if asset_type != "Crypto" else "Trend (vs BTC)": rs_status,
            "Gambit Reversals": gambit_status,
            "Confluence": confluence_text,
            "Action": f"https://www.tradingview.com/chart/?symbol={tv_link_ticker}",
            "is_flip": is_flip,
            "flip_type": flip_text
        }
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner="Turbo Scanning Markets...") 
def scan_market(tickers_map, benchmark_symbol, asset_type="Stock"):
    tz_ny = pytz.timezone('US/Eastern')
    now_ny = datetime.now(tz_ny)
    
    market_cutoff_hour = 16
    is_market_closed_today = now_ny.hour >= market_cutoff_hour

    bench_ticker = yf.Ticker(benchmark_symbol)
    bench_hist = bench_ticker.history(period="1y")
    
    # --- DISPLAY DATE FIX ---
    # Since we are forcing a drop of the last row for Crypto, the "Date" should reflect the CLOSED candle.
    # If market is open (or Crypto), we used iloc[:-1], so the date is index[-2].
    if (asset_type == "Crypto") or (not is_market_closed_today):
         display_date = bench_hist.index[-2].strftime('%b %d, %Y')
         spy_subset = bench_hist.iloc[:-1]
    else:
         display_date = bench_hist.index[-1].strftime('%b %d, %Y')
         spy_subset = bench_hist.copy()

    tasks = []
    for ticker, name in tickers_map.items():
        tasks.append((ticker, name, asset_type, spy_subset, is_market_closed_today))
    
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        processed = list(executor.map(fetch_single_ticker, tasks))
    results = [p for p in processed if p is not None]

    # --- CATEGORICAL & AUTO-SORT LOGIC ---
    df = pd.DataFrame(results)
    
    if not df.empty:
        trend_cats = ["Bullish 🟢", "Neutral ⚪", "Bearish 🔴", "—"]
        if 'Trend (vs USD)' in df.columns:
             df['Trend (vs USD)'] = pd.Categorical(df['Trend (vs USD)'], categories=trend_cats, ordered=True)
        
        bench_col = "Trend (vs BTC)" if asset_type == "Crypto" else "Trend (vs SPY)"
        if bench_col in df.columns:
             df[bench_col] = pd.Categorical(df[bench_col], categories=trend_cats, ordered=True)
             
        confluence_cats = [
            "🚀 STRONG BUY",
            "📈 Trending Up",
            "🔥 REVERSAL",
            "⚪ Neutral",
            "⚠️ PULLBACK",
            "📉 Trending Down",
            "⬇️ STRONG SELL"
        ]
        if 'Confluence' in df.columns:
            df['Confluence'] = pd.Categorical(df['Confluence'], categories=confluence_cats, ordered=True)
            df = df.sort_values(by='Confluence')

    return df, display_date

col_left, col_right = st.columns([3, 1])
with col_left:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot v3.2") 
with col_right:
    st.markdown("""<div class="status-container"><div class="status-text">● Turbo Online</div></div>""", unsafe_allow_html=True)
    if st.button("Refresh Data", key="refresh_top"):
        st.cache_data.clear()
        st.rerun()

st.write("") 
st.markdown("""<style>.stDataFrame { width: 100%; }</style>""", unsafe_allow_html=True)

def highlight_rows(row):
    val = str(row.get('Confluence', '')) 
    if "STRONG BUY" in val: return ['background-color: #06402B'] * len(row) 
    if "STRONG SELL" in val: return ['background-color: #4a0f0f'] * len(row) 
    if "REVERSAL" in val: return ['background-color: #5c4d00'] * len(row) 
    if "PULLBACK" in val: return ['background-color: #5c2b00'] * len(row)
    if "Trending Up" in val: return ['background-color: #1b4d3e'] * len(row)
    if "Trending Down" in val: return ['background-color: #4d1b1b'] * len(row)
    return [''] * len(row)

tab_stocks, tab_coins, tab_commodities, tab_flips = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️", "⚡ NEW FLIPS"])

def get_col_config(asset_type):
    bench_name = "Trend (vs BTC)" if asset_type == "Crypto" else "Trend (vs SPY)"
    return {
        "is_flip": None, 
        "flip_type": None, 
        "Action": st.column_config.LinkColumn("Chart"),
        "Trend (vs USD)": st.column_config.TextColumn("Trend (vs USD)"),
        bench_name: st.column_config.TextColumn(bench_name),
        "Gambit Reversals": st.column_config.TextColumn("Gambit Reversals"),
        "Confluence": st.column_config.TextColumn("Confluence")
    }

# --- STOCKS TAB WITH SUB-TABS (NESTED) ---
with tab_stocks:
    df_stocks, stock_date = scan_market(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Data Date: **{stock_date}**")
    
    subtabs = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
    
    with subtabs[0]:
        st.dataframe(df_stocks.style.apply(highlight_rows, axis=1), column_config=get_col_config("Stock"), hide_index=True, use_container_width=False, height=1200)
    
    for i, category in enumerate(STOCK_GROUPS.keys()):
        with subtabs[i+1]:
            target_tickers = [t.replace("=F", "").replace("-USD", "") for t in STOCK_GROUPS[category]]
            subset_df = df_stocks[df_stocks['Ticker'].isin(target_tickers)]
            st.dataframe(subset_df.style.apply(highlight_rows, axis=1), column_config=get_col_config("Stock"), hide_index=True, use_container_width=False, height=1200)

with tab_coins:
    df_crypto, crypto_date = scan_market(CRYPTO_MAP, "BTC-USD", "Crypto")
    st.caption(f"📅 Data Date: **{crypto_date}**")
    st.dataframe(df_crypto.style.apply(highlight_rows, axis=1), column_config=get_col_config("Crypto"), hide_index=True, use_container_width=False, height=1200)

with tab_commodities:
    df_comm, comm_date = scan_market(COMMODITY_MAP, "SPY", "Commodity")
    st.caption(f"📅 Data Date: **{comm_date}**")
    st.dataframe(df_comm.style.apply(highlight_rows, axis=1), column_config=get_col_config("Commodity"), hide_index=True, use_container_width=False, height=1200)

with tab_flips:
    st.caption("⚡ Assets that triggered a Signal or Flip TODAY")
    all_flips = []
    if 'df_stocks' in locals() and not df_stocks.empty: all_flips.append(df_stocks[df_stocks['is_flip'] == True].copy())
    if 'df_crypto' in locals() and not df_crypto.empty: all_flips.append(df_crypto[df_crypto['is_flip'] == True].copy())
    if 'df_comm' in locals() and not df_comm.empty: all_flips.append(df_comm[df_comm['is_flip'] == True].copy())
    
    if all_flips:
        df_flips = pd.concat(all_flips, ignore_index=True)
        cols = ['Company', 'Ticker', 'flip_type', 'Trend (vs USD)', 'Gambit Reversals', 'Confluence', 'Price', 'Action']
        cols = [c for c in cols if c in df_flips.columns]
        
        flips_config = get_col_config("Stock") 
        flips_config["flip_type"] = st.column_config.TextColumn("Trigger Event")
        
        st.dataframe(
            df_flips[cols].style.apply(highlight_rows, axis=1),
            column_config=flips_config,
            hide_index=True, use_container_width=False
        )
    else:
        st.info("No trend flips or gambit signals detected today.")
