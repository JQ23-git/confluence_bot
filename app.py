import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# --- 1. CONFIG & DARK STYLE ---
st.set_page_config(layout="wide", page_title="confluence.bot", page_icon="favicon.ico")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .stApp { background-color: #0e1117; color: #ffffff; }
    button[data-baseweb="tab"] div p { font-size: 18px !important; font-weight: 700 !important; color: #ffffff !important; }
    .status-text { color: #22d3ee; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
    div.stButton > button { border: 1px solid #333; background-color: #0e1117; color: #ffffff; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# --- 2. DATA MAPPING ---
STOCK_GROUPS = {
    "Tech & AI": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "QCOM", "INTC", "MU", "ASML", "TSM"],
    "Cyber & Cloud": ["PANW", "CRWD", "FTNT", "ZS", "CHKP", "OKTA", "IBM", "ORCL", "ADBE", "CRM", "CSCO"],
    "Defense & Space": ["RTX", "BA", "LMT", "NOC", "LHX", "RKLB", "ASTS", "PL", "IRDM", "RDW", "SPIR", "SPCE"],
    "Energy": ["GEV", "NEE", "FSLR", "BEP", "RUN", "CWEN", "FLNC", "XOM", "CVX"],
    "Bio & Blue Chips": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "NVO", "TMO", "DNA", "SANA", "BRK-B", "WMT", "JPM", "V", "MA", "PG", "HD", "NFLX", "BABA", "TM", "BAC", "PEP", "KO", "MCD", "T", "NIO"]
}
STOCK_MAP = {t: t for cat in STOCK_GROUPS.values() for t in cat}

CRYPTO_MAP = {
    "2Z-USD": "DoubleZero", "A7A5-USD": "A7A5", "AAVE-USD": "Aave", "AB-USD": "AB", "ADA-USD": "Cardano",
    "AERO-USD": "Aerodrome Finance", "ALGO-USD": "Algorand", "APE-USD": "ApeCoin", "APT-USD": "Aptos", "ARB-USD": "Arbitrum",
    "ASTER-USD": "Aster", "ATOM-USD": "Cosmos Hub", "AVAX-USD": "Avalanche", "AXS-USD": "Axie Infinity", "BCH-USD": "Bitcoin Cash",
    "BDX-USD": "Beldex", "BFUSD-USD": "BFUSD", "BGB-USD": "Bitget Token", "BNB-USD": "BNB", "BNSOL-USD": "Binance Staked SOL",
    "BONK-USD": "Bonk", "BSC-USD-USD": "Binance Bridged USDT", "BSV-USD": "Bitcoin SV", "BTC-USD": "Bitcoin",
    "BTC.B-USD": "Avalanche Bridged BTC", "BTT-USD": "BitTorrent", "BUIDL-USD": "BlackRock USD Fund", "CAKE-USD": "PancakeSwap",
    "CBBTC-USD": "Coinbase Wrapped BTC", "CC-USD": "Canton", "CFX-USD": "Conflux", "CHZ-USD": "Chiliz", "CLBTC-USD": "clBTC",
    "CRO-USD": "Cronos", "CRV-USD": "Curve DAO", "CRVUSD-USD": "crvUSD", "CTM-USD": "c8ntinuum", "CUSD-USD": "Cap USD",
    "DAI-USD": "Dai", "DASH-USD": "Dash", "DCR-USD": "Decred", "DOGE-USD": "Dogecoin", "DOT-USD": "Polkadot",
    "EETH-USD": "ether.fi Staked ETH", "EGLD-USD": "MultiversX", "ENA-USD": "Ethena", "ENS-USD": "Ethereum Name Service",
    "EOS-USD": "EOS", "ETC-USD": "Ethereum Classic", "ETH-USD": "Ethereum", "ETHFI-USD": "Ether.fi", "ETHX-USD": "Stader ETHx",
    "EURC-USD": "EURC", "EUTBL-USD": "Spiko EU T-Bills", "EZETH-USD": "Renzo Restaked ETH", "FARTCOIN-USD": "Fartcoin",
    "FBTC-USD": "Function FBTC", "FDUSD-USD": "First Digital USD", "FET-USD": "Artificial Superintelligence",
    "FIGR_HELOC-USD": "Figure Heloc", "FIL-USD": "Filecoin", "FLOKI-USD": "FLOKI", "FLR-USD": "Flare", "FTN-USD": "Fasttoken",
    "GHO-USD": "GHO", "GNO-USD": "Gnosis", "GRT-USD": "The Graph", "GT-USD": "Gate", "GTETH-USD": "GTETH", "H-USD": "Humanity",
    "HASH-USD": "Provenance Blockchain", "HBAR-USD": "Hedera", "HTX-USD": "HTX DAO", "HYPE-USD": "Hyperliquid",
    "ICP-USD": "Internet Computer", "INJ-USD": "Injective", "IOTA-USD": "IOTA", "IP-USD": "Story", "JAAA-USD": "Janus Henderson AAA",
    "JASMY-USD": "JasmyCoin", "JITOSOL-USD": "Jito Staked SOL", "JLP-USD": "Jupiter LP", "JST-USD": "JUST",
    "JTRSY-USD": "Janus Henderson Treasury", "JUP-USD": "Jupiter", "JUPSOL-USD": "Jupiter Staked SOL", "KAG-USD": "Kinesis Silver",
    "KAIA-USD": "Kaia", "KAS-USD": "Kaspa", "KAU-USD": "Kinesis Gold", "KCS-USD": "KuCoin", "KHYPE-USD": "Kinetiq Staked HYPE",
    "LBTC-USD": "Lombard Staked BTC", "LDO-USD": "Lido DAO", "LEO-USD": "LEO Token", "LINK-USD": "Chainlink",
    "LIQUIDETH-USD": "Ether.Fi Liquid ETH", "LIT-USD": "Lighter", "LSETH-USD": "Liquid Staked ETH", "LTC-USD": "Litecoin",
    "M-USD": "MemeCore", "MANA-USD": "Decentraland", "MATIC-USD": "Polygon", "METH-USD": "Mantle Staked Ether", "MNT-USD": "Mantle",
    "MORPHO-USD": "Morpho", "MSOL-USD": "Marinade Staked SOL", "MYX-USD": "MYX Finance", "NEAR-USD": "NEAR Protocol",
    "NEXO-USD": "NEXO", "NFT-USD": "AINFT", "NIGHT-USD": "Midnight", "OHM-USD": "Olympus", "OKB-USD": "OKB", "ONDO-USD": "Ondo",
    "OP-USD": "Optimism", "OSETH-USD": "StakeWise Staked ETH", "OUSG-USD": "OUSG", "PAXG-USD": "PAX Gold", "PENDLE-USD": "Pendle",
    "PENGU-USD": "Pudgy Penguins", "PEPE-USD": "Pepe", "PI-USD": "Pi Network", "PIPPIN-USD": "pippin", "POL-USD": "POL (ex-MATIC)",
    "PUMP-USD": "Pump.fun", "PYTH-USD": "Pyth Network", "PYUSD-USD": "PayPal USD", "QNT-USD": "Quant", "RAIN-USD": "Rain",
    "RENDER-USD": "Render", "RIVER-USD": "River", "RLUSD-USD": "Ripple USD", "RSETH-USD": "Kelp DAO Restaked ETH",
    "SAND-USD": "The Sandbox", "SBTC-USD": "sBTC", "SEI-USD": "Sei", "SHIB-USD": "Shiba Inu", "SKY-USD": "Sky",
    "SOL-USD": "Solana", "SOLVBTC-USD": "Solv Protocol BTC", "SPX-USD": "SPX6900", "STABLE-USD": "​​Stable",
    "STEAKUSDC-USD": "Steakhouse USDC", "STKAAVE-USD": "Staked Aave", "STRK-USD": "Starknet", "STX-USD": "Stacks", "SUI-USD": "Sui",
    "SUN-USD": "Sun Token", "SUSDE-USD": "Ethena Staked USDe", "SUSDS-USD": "sUSDS", "SYRUP-USD": "Maple Finance",
    "SYRUPUSDC-USD": "syrupUSDC", "SYRUPUSDT-USD": "syrupUSDT", "TAO-USD": "Bittensor", "TBTC-USD": "tBTC", "TEL-USD": "Telcoin",
    "THETA-USD": "Theta Network", "TIA-USD": "Celestia", "TON-USD": "Toncoin", "TRUMP-USD": "Official Trump", "TRX-USD": "TRON",
    "TWT-USD": "Trust Wallet", "UBTC-USD": "Unit Bitcoin", "UDS-USD": "Undeads Games", "UNI-USD": "Uniswap", "USD0-USD": "Usual USD",
    "USD1-USD": "USD1", "USDAI-USD": "USDai", "USDB-USD": "USDB", "USDC.E-USD": "Polygon Bridged USDC", "USDE-USD": "Ethena USDe",
    "USDF-USD": "Falcon USD", "USDG-USD": "Global Dollar", "USDS-USD": "USDS", "USDT0-USD": "USDT0", "USDTB-USD": "USDtb",
    "USDY-USD": "Ondo US Dollar Yield", "USR-USD": "Resolv USR", "USTB-USD": "Superstate USTB", "USX-USD": "USX", "USYC-USD": "Circle USYC",
    "VET-USD": "VeChain", "VIRTUAL-USD": "Virtuals Protocol", "WAPE-USD": "Wrapped ApeCoin", "WBETH-USD": "Wrapped Beacon ETH",
    "WBNB-USD": "Wrapped BNB", "WBT-USD": "WhiteBIT Coin", "WEETH-USD": "Wrapped eETH", "WFLR-USD": "Wrapped Flare",
    "WIF-USD": "dogwifhat", "WLD-USD": "Worldcoin", "WLFI-USD": "World Liberty Fin", "WM-USD": "WrappedM by M0",
    "WSTUSR-USD": "Resolv wstUSR", "WSTX-USD": "Wrapped STX", "XAUT-USD": "Tether Gold", "XDC-USD": "XDC Network",
    "XLM-USD": "Stellar", "XMR-USD": "Monero", "XRP-USD": "XRP", "XTZ-USD": "Tezos", "ZEC-USD": "Zcash", "ZRO-USD": "LayerZero"
}

COMMODITY_MAP = {"GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil", "NG=F": "Natural Gas", "ZC=F": "Corn"}

# --- 3. INDICATORS ---
def calculate_smma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()

def get_ae_signal(df, target_col='hl2'):
    src = (df['High'] + df['Low']) / 2 if target_col == 'hl2' else df[target_col]
    f, m, s = calculate_smma(src, 16), calculate_smma(src, 26), calculate_smma(src, 34)
    return (f > m) & (m > s) & (src > f), (f < m) & (m < s) & (src < f)

def get_gambit_signal(df):
    l_s = df['Low'].ewm(alpha=3.5/17, adjust=False).mean()
    h_s = df['High'].ewm(alpha=3.5/17, adjust=False).mean()
    rev_up = (df['Close'].shift(1) < l_s.shift(1)) & (df['Close'] > l_s) & (df['Close'] > df['Open'])
    rev_down = (df['Close'].shift(1) > h_s.shift(1)) & (df['Close'] < h_s) & (df['Close'] < df['Open'])
    return rev_up, rev_down

# --- 4. ENGINE ---
def fetch_ticker(args):
    ticker, name, asset_type, spy_sub, is_closed = args
    try:
        df = yf.Ticker(ticker).history(period="1y")
        if df is None or len(df) < 50: return None
        if asset_type == "Crypto" or not is_closed: df = df.iloc[:-1]
        bull, bear = get_ae_signal(df)
        buy, sell = get_gambit_signal(df)
        t_stat = "Neutral ⚪"; g_stat = "—"; c_stat = "⚪ Neutral"
        if bull.iloc[-1]: t_stat = "Bullish 🟢"
        elif bear.iloc[-1]: t_stat = "Bearish 🔴"
        if buy.iloc[-1]: g_stat = "🟢 BUY (Reversal)"
        elif sell.iloc[-1]: g_stat = "🔴 SELL (Pivot)"
        if bull.iloc[-1]: c_stat = "🚀 STRONG BUY" if buy.iloc[-1] else "📈 Trending Up"
        elif bear.iloc[-1]: c_stat = "⬇️ STRONG SELL" if sell.iloc[-1] else "📉 Trending Down"
        elif buy.iloc[-1]: c_stat = "🔥 REVERSAL"
        common = df.index.intersection(spy_sub.index)
        rs_stat = "—"
        if len(common) > 20:
            ratio = df.loc[common, 'Close'] / spy_sub.loc[common, 'Close']
            r_bull, r_bear = get_ae_signal(pd.DataFrame({'ratio': ratio}), 'ratio')
            rs_stat = "Bullish 🟢" if r_bull.iloc[-1] else "Bearish 🔴" if r_bear.iloc[-1] else "Neutral ⚪"
        return {"Company": name, "Ticker": ticker.replace("-USD", ""), "Price": f"${df['Close'].iloc[-1]:.2f}",
                "Trend (vs USD)": t_stat, "BenchTrend": rs_stat, "Gambit Reversals": g_stat, "Confluence": c_stat,
                "Action": f"https://www.tradingview.com/chart/?symbol={ticker}"}
    except: return None

@st.cache_data(ttl=3600)
def scan(t_map, bench, a_type):
    tz = pytz.timezone('US/Eastern'); now = datetime.now(tz); is_closed = now.hour >= 16
    spy = yf.Ticker(bench).history(period="1y")
    spy_sub = spy.iloc[:-1] if not is_closed or a_type == "Crypto" else spy
    tasks = [(t, n, a_type, spy_sub, is_closed) for t, n in t_map.items()]
    with ThreadPoolExecutor(max_workers=20) as exe:
        results = [r for r in list(exe.map(fetch_ticker, tasks)) if r]
    df = pd.DataFrame(results)
    if not df.empty:
        cats = ["🚀 STRONG BUY", "🔥 REVERSAL", "📈 Trending Up", "⚪ Neutral", "📈 Pullback", "📉 Trending Down", "⬇️ STRONG SELL"]
        df['Confluence'] = pd.Categorical(df['Confluence'], categories=cats, ordered=True)
        df = df.sort_values('Confluence')
    return df, spy_sub.index[-1].strftime('%b %d, %Y')

# --- 5. UI ---
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("logo.png"): st.image("logo.png", width=350)
    else: st.title("confluence.bot v4.2")
with col2:
    st.markdown('<div class="status-container"><div class="status-text">● Turbo Online</div></div>', unsafe_allow_html=True)
    if st.button("Refresh"): st.cache_data.clear(); st.rerun()

t_stocks, t_coins, t_comm = st.tabs(["STOCKS 📈", "COINS ₿", "COMMODITIES 🛢️"])

def draw(df, bench_name="Trend (vs SPY)"):
    buy_c, sell_c, rev_c, t_up, t_down = "#06402B", "#4a0f0f", "#5c4d00", "#1b4d3e", "#4d1b1b"
    def highlight(row):
        val = str(row.get('Confluence', ''))
        if "STRONG BUY" in val: return [f'background-color: {buy_c}'] * len(row)
        if "STRONG SELL" in val: return [f'background-color: {sell_c}'] * len(row)
        if "REVERSAL" in val: return [f'background-color: {rev_c}'] * len(row)
        if "Trending Up" in val: return [f'background-color: {t_up}'] * len(row)
        if "Trending Down" in val: return [f'background-color: {t_down}'] * len(row)
        return [''] * len(row)
    
    # Rename the column specifically for display
    df_display = df.rename(columns={"BenchTrend": bench_name})
    
    st.dataframe(df_display.style.apply(highlight, axis=1), 
                 column_config={"Action": st.column_config.LinkColumn("Chart")}, 
                 hide_index=True, use_container_width=True, height=1200)

with t_stocks:
    df_s, d_s = scan(STOCK_MAP, "SPY", "Stock")
    st.caption(f"📅 Data Date: {d_s}")
    sub = st.tabs(["📋 ALL"] + list(STOCK_GROUPS.keys()))
    with sub[0]:
        draw(df_s, "Trend (vs SPY)")
    for i, cat in enumerate(STOCK_GROUPS.keys()):
        with sub[i+1]:
            # STRICT FILTERING: Only show tickers assigned to this specific group
            subset = df_s[df_s['Ticker'].isin(STOCK_GROUPS[cat])]
            draw(subset, "Trend (vs SPY)")

with t_coins:
    df_c, d_c = scan(CRYPTO_MAP, "BTC-USD", "Crypto")
    st.caption(f"📅 Data Date: {d_c}")
    draw(df_c, "Trend (vs BTC)")

with t_comm:
    df_m, d_m = scan(COMMODITY_MAP, "SPY", "Comm")
    st.caption(f"📅 Data Date: {d_m}")
    draw(df_m, "Trend (vs SPY)")
