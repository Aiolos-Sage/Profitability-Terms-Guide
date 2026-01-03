import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

# --- Configuration ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- Session State for Dark Mode ---
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

# --- Dynamic CSS ---
def local_css(is_dark):
    if is_dark:
        bg_color = "#0e1117"
        text_color = "#fafafa"
        card_bg = "#262730"
        border_color = "rgba(250, 250, 250, 0.1)"
        shadow_color = "rgba(0, 0, 0, 0.3)"
        label_color = "#d0d0d0"
        desc_color = "#b0b0b0"
        btn_bg = "#d93025"
        btn_text = "#ffffff"
    else:
        bg_color = "#ffffff"
        text_color = "#000000"
        card_bg = "#ffffff"
        border_color = "rgba(128, 128, 128, 0.1)"
        shadow_color = "rgba(0, 0, 0, 0.05)"
        label_color = "#5f6368"
        desc_color = "#70757a"
        btn_bg = "#d93025"
        btn_text = "#ffffff"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg_color}; color: {text_color}; }}
        html, body, [class*="css"] {{ font-family: 'Inter', 'Roboto', sans-serif; font-size: 1rem; color: {text_color}; }}
        
        div.metric-card {{
            background-color: {card_bg};
            border: 1px solid {border_color};
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 6px {shadow_color};
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        h4.metric-label {{
            font-size: 0.9rem;
            font-weight: 600;
            color: {label_color};
            opacity: 0.9;
            margin: 0 0 8px 0;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        div.metric-value {{ font-size: 2.2rem; font-weight: 700; color: {text_color}; margin-bottom: 16px; }}
        div.metric-desc {{
            font-size: 0.95rem;
            line-height: 1.5;
            color: {desc_color};
            margin: 0;
            border-top: 1px solid {border_color};
            padding-top: 12px;
        }}
        
        /* Button & Inputs */
        div.stButton > button {{
            background-color: {btn_bg};
            color: {btn_text};
            border: none;
            width: 100%;
            font-weight: 500;
        }}
        div.stButton > button:hover {{ background-color: #b0281f; color: {btn_text}; }}
        h1, h2, h3, h4, h5, h6, .stMarkdown, .stText, .stRadio label {{ color: {text_color} !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- Data Fetching ---
def fetch_quickfs_data(ticker, api_key, retries=2):
    url = f"https://public-api.quickfs.net/v1/data/all-data/{ticker}?api_key={api_key}"
    for attempt in range(retries + 1):
        try:
            response = requests.get(url)
            if response.status_code == 200: return response.json()
            elif response.status_code >= 500:
                if attempt < retries: time.sleep(1); continue
                st.error(f"❌ QuickFS Server Error (500) for {ticker}."); return None
            elif response.status_code == 404:
                st.error(f"❌ Ticker '{ticker}' not found."); return None
            else: st.error(f"❌ Error {response.status_code}: {response.reason}"); return None
        except requests.exceptions.RequestException: return None
    return None

def extract_historical_df(data, start_year, end_year):
    """
    Robust data extraction using dictionary mapping to prevent index errors.
    """
    try:
        # 1. Safe Access to API sections
        d = data.get("data", {})
        fin = d.get("financials", {})
        annual = fin.get("annual", {})
        ttm_data = fin.get("ttm", {})
        meta = d.get("metadata", {})
        
        # 2. Parse Dates (The "Index")
        raw_dates = meta.get("period_end_date", [])
        if not raw_dates: return pd.DataFrame()
        
        # Create a list of years. QuickFS sends oldest -> newest.
        # Example: [2014, 2015, ... 2023]
        years = []
        for dt in raw_dates:
            try: years.append(int(str(dt).split("-")[0]))
            except: years.append(None)
            
        if not years: return pd.DataFrame()

        # 3. Define Metric Map
        # Note: We include 'income_tax' solely for NOPAT calculation
        map_keys = {
            "Revenue": ["revenue"],
            "Gross Profit": ["gross_profit"],
            "Operating Profit": ["operating_income"],
            "EBITDA": ["ebitda"],
            "Net Income": ["net_income"],
            "EPS (Diluted)": ["eps_diluted"],
            "Operating Cash Flow": ["cf_cfo", "cfo"],
            "Free Cash Flow": ["fcf"],
            "Income Tax": ["income_tax"] # Hidden helper
        }

        # 4. Build DataFrame Dictionary (Year -> Value)
        # We zip the 'years' list with the 'data' list. This aligns them perfectly.
        df_dict = {}
        
        for label, keys in map_keys.items():
            # Find valid key in annual data
            valid_key = next((k for k in keys if k in annual), None)
            
            # Create a dictionary for this metric: {2014: 100, 2015: 110...}
            metric_series = {}
            if valid_key and annual[valid_key]:
                data_list = annual[valid_key]
                # Zip strictly ensures we only pair available years with available data
                for y, val in zip(years, data_list):
                    if y is not None:
                        metric_series[y] = val
            
            df_dict[label] = metric_series

        # 5. Convert to Pandas DataFrame
        df = pd.DataFrame(df_dict)
        
        # Calculate NOPAT safely using Pandas Vectorization
        # NOPAT = Operating Profit - Income Tax
        if "Operating Profit" in df.columns:
            if "Income Tax" in df.columns:
                df["NOPAT"] = df["Operating Profit"] - df["Income Tax"]
            else:
                # Fallback: 21% Tax assumption
                df["NOPAT"] = df["Operating Profit"] * (1 - 0.21)
        
        # Drop the helper 'Income Tax' column if you don't want to display it
        if "Income Tax" in df.columns:
            df = df.drop(columns=["Income Tax"])

        # 6. Filter by User Selection
        # Ensure index is numeric and sorted
        df.index = df.index.astype(int)
        df.sort_index(inplace=True)
        
        target_start = int(start_year)
        if end_year == "TTM":
            target_end = 2100 # Future-proof max
        else:
            target_end = int(end_year)
            
        # Filter Rows
        df = df[(df.index >= target_start) & (df.index <= target_end)]
        
        # 7. Handle TTM Column
        if end_year == "TTM":
            # We add a new row or column. For display, we want TTM as the *last column* in a transposed view.
            # Let's prepare a TTM Series
            ttm_vals = {}
            for label in df.columns:
                # Find TTM value from API 'ttm' dictionary
                # We need to map 'label' back to API keys. This is a bit tricky.
                # Easier way: Re-check the map_keys
                found = None
                
                # Special NOPAT Logic for TTM
                if label == "NOPAT":
                     op = ttm_data.get("operating_income")
                     tax = ttm_data.get("income_tax")
                     if op is not None:
                         found = (op - tax) if tax is not None else (op * 0.79)
                else:
                    # Standard Lookup
                    # Find which API keys correspond to this Label
                    candidates = map_keys.get(label, [])
                    for k in candidates:
                        if k in ttm_data:
                            found = ttm_data[k]
                            break
                            
                ttm_vals[label] = found
            
            # Add TTM as a new row with index 9999 (temp)
            df.loc[9999] = ttm_vals
            # Rename index 9999 to 'TTM'
            df.rename(index={9999: "TTM"}, inplace=True)

        # Transpose: Metrics become Rows, Years become Columns
        return df.T

    except Exception as e:
        # st.error(f"Debug Error: {e}") # Uncomment for debugging
        return pd.DataFrame()

def format_currency(value, currency_symbol="$"):
    if value is None or pd.isna(value): return "N/A"
    try:
        abs_val = abs(value)
        if abs_val >= 1_000_000_000: return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
        elif abs_val >= 1_000_000: return f"{currency_symbol}{value / 1_000_000:.2f}M"
        else: return f"{currency_symbol}{value:,.2f}"
    except: return "N/A"

def render_card(label, value_str, description, accent_color="#4285F4"):
    html = f"""
    <div class="metric-card" style="border-top: 4px solid {accent_color};">
        <div>
            <h4 class="metric-label">{label}</h4>
            <div class="metric-value">{value_str}</div>
        </div>
        <p class="metric-desc">{description}</p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Main App ---
st.set_page_config(page_title="Financial Dashboard", layout="wide")

# (1) Clean Sidebar
with st.sidebar:
    st.header("Settings")
    st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode, on_change=toggle_dark_mode)
    st.markdown("---")
    st.caption("Data source: **QuickFS API**")

local_css(st.session_state.dark_mode)

# (2) Top Search Bar
col_search, col_btn = st.columns([4, 1])
with col_search:
    search_input = st.text_input("Enter Ticker", placeholder="e.g. APG:US", label_visibility="collapsed")
with col_btn:
    load_btn = st.button("Load Financials")

st.markdown("---")

# (3) Filters
col_start, col_end = st.columns(2)
current_year = datetime.now().year
years_range = list(range(2000, current_year + 1))
years_str = [str(y) for y in years_range]

with col_start:
    # Default to 2017 or similar
    def_idx = years_str.index("2017") if "2017" in years_str else 0
    start_year_sel = st.selectbox("Start Year", years_str, index=def_idx)

with col_end:
    end_opts = years_str + ["TTM"]
    end_year_sel = st.selectbox("End Year", end_opts, index=len(end_opts)-1)

st.markdown("---")

# Logic: Persist Data
if 'data_cache' not in st.session_state: st.session_state.data_cache = None
if 'current_ticker' not in st.session_state: st.session_state.current_ticker = ""

if load_btn and search_input:
    ticker = search_input.strip()
    with st.spinner(f"Loading {ticker}..."):
        data = fetch_quickfs_data(ticker, API_KEY)
        if data:
            st.session_state.data_cache = data
            st.session_state.current_ticker = ticker
        else:
            st.session_state.data_cache = None

# Render Data
if st.session_state.data_cache:
    json_data = st.session_state.data_cache
    ticker = st.session_state.current_ticker
    meta = json_data.get("data", {}).get("metadata", {})
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    st.markdown(f"## {meta.get('name', ticker)} <span style='color:gray'>({ticker})</span>", unsafe_allow_html=True)
    st.caption(f"Reporting Currency: {currency}")

    # Validate Inputs
    valid = True
    if end_year_sel != "TTM" and int(end_year_sel) < int(start_year_sel):
        st.error("End Year must be after Start Year.")
        valid = False

    if valid:
        # Extract Data
        df = extract_historical_df(json_data, start_year_sel, end_year_sel)
        
        if not df.empty:
            # 1. Cards View (Snapshot of the LAST column - TTM or End Year)
            latest_col = df.columns[-1] # "TTM" or "2023"
            
            st.subheader(f"📊 Snapshot ({latest_col})")
            
            # Helper to get value
            def val(metric): return df.loc[metric, latest_col] if metric in df.index else None

            # Cards Logic
            c_inc = "#3b82f6"
            c1, c2, c3, c4 = st.columns(4)
            with c1: render_card("Revenue", format_currency(val("Revenue"), curr_sym), "Top-line sales indicating market demand.", c_inc)
            with c2: render_card("Gross Profit", format_currency(val("Gross Profit"), curr_sym), "Revenue minus COGS. Production efficiency.", c_inc)
            with c3: render_card("Operating Profit", format_currency(val("Operating Profit"), curr_sym), "Core business profit (EBIT).", c_inc)
            with c4: render_card("EBITDA", format_currency(val("EBITDA"), curr_sym), "Proxy for operational cash flow.", c_inc)

            st.markdown("")
            c1, c2, c3, c4 = st.columns(4)
            with c1: render_card("NOPAT", format_currency(val("NOPAT"), curr_sym), "Potential cash earnings if debt-free.", c_inc)
            with c2: render_card("Net Income", format_currency(val("Net Income"), curr_sym), "Bottom-line earnings for shareholders.", c_inc)
            with c3: render_card("EPS (Diluted)", f"{curr_sym}{val('EPS (Diluted)'):.2f}" if val('EPS (Diluted)') else "N/A", "Profit attributed to each share.", c_inc)
            with c4: st.empty()

            st.markdown("---")
            st.subheader(f"💸 Cash Flow ({latest_col})")
            c_cf = "#10b981"
            c1, c2, c3, c4 = st.columns(4)
            with c1: render_card("Operating Cash Flow", format_currency(val("Operating Cash Flow"), curr_sym), "Cash from actual operations.", c_cf)
            with c2: render_card("Free Cash Flow", format_currency(val("Free Cash Flow"), curr_sym), "Real owner's earnings (OCF - CapEx).", c_cf)
            with c3: st.empty()
            with c4: st.empty()
            
            # 2. Raw Data View
            st.markdown("---")
            with st.expander("📂 View Raw Data (Selected Period)", expanded=True):
                # Format DF for display
                df_disp = df.copy()
                for c in df_disp.columns:
                    df_disp[c] = df_disp[c].apply(lambda x: format_currency(x, curr_sym) if pd.notnull(x) else "N/A")
                st.dataframe(df_disp, use_container_width=True)

                st.markdown("### Trend Visualization")
                # Plot requires numeric data (df), not string formatted (df_disp)
                # Also, index is Metrics, Columns are Years. We need to Transpose for st.bar_chart
                metric_plot = st.selectbox("Select Metric", df.index)
                if metric_plot:
                    row_data = df.loc[metric_plot]
                    # If TTM is in index (it's a string mixed with ints), chart might look odd. 
                    # Convert index to string for uniform x-axis
                    row_data.index = row_data.index.astype(str)
                    st.bar_chart(row_data)

        else:
            st.warning("No data found for the selected period. Try an earlier Start Year.")

elif load_btn and not search_input:
    st.warning("Please enter a ticker.")
