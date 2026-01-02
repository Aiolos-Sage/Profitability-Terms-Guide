import streamlit as st
import requests
import pandas as pd
import time

# --- Configuration ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

# Preset examples for quick selection
EXAMPLE_STOCKS = {
    "DNP (Warsaw)": "DNP:PL",
    "Ashtead Group (London)": "AHT:LN",
    "APi Group (USA)": "APG:US"
}

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
    else:
        bg_color = "#ffffff"
        text_color = "#000000"
        card_bg = "#ffffff"
        border_color = "rgba(128, 128, 128, 0.1)"
        shadow_color = "rgba(0, 0, 0, 0.05)"
        label_color = "#5f6368"
        desc_color = "#70757a"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg_color}; color: {text_color}; }}
        html, body, [class*="css"] {{ font-family: 'Inter', 'Roboto', sans-serif; font-size: 1rem; color: {text_color}; }}
        
        /* Card Styles */
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
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        div.metric-card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 15px {shadow_color}; }}

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
            font-size: 0.9rem;
            line-height: 1.5;
            color: {desc_color};
            margin: 0;
            border-top: 1px solid {border_color};
            padding-top: 12px;
        }}
        div.metric-desc ul {{ padding-left: 20px; margin: 0; }}
        div.metric-desc li {{ margin-bottom: 6px; }}

        /* Table Styles for History View */
        .dataframe {{ font-size: 0.9rem !important; }}
        
        /* Overrides */
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
                else: st.error(f"❌ QuickFS Server Error (500) for {ticker}. API temporarily down."); return None
            elif response.status_code == 404:
                st.error(f"❌ Ticker '{ticker}' not found. Please check the format (e.g. AAPL:US)."); return None
            else: st.error(f"❌ Error {response.status_code}: {response.reason}"); return None
        except requests.exceptions.RequestException as e: st.error(f"🚨 Connection Error: {e}"); return None
    return None

def extract_ttm_metric(data, metric_key):
    """Extract single TTM value (for Cards)."""
    try:
        financials = data.get("data", {}).get("financials", {})
        keys_to_check = [metric_key] if isinstance(metric_key, str) else metric_key
        
        # 1. Explicit TTM
        for key in keys_to_check:
            if "ttm" in financials and key in financials["ttm"]: return financials["ttm"][key]
        
        # 2. Quarterly Sum Fallback
        quarterly = financials.get("quarterly", {})
        for key in keys_to_check:
            if key in quarterly:
                values = quarterly[key]
                if values and len(values) >= 4:
                    valid_values = [v for v in values if v is not None]
                    if len(valid_values) >= 4: return sum(valid_values[-4:])
        return None
    except Exception: return None

def extract_historical_df(data, years=10):
    """Extracts last 10 years of annual data + TTM into a DataFrame."""
    try:
        fin = data.get("data", {}).get("financials", {})
        annual = fin.get("annual", {})
        ttm = fin.get("ttm", {})
        
        # Get Dates (Fiscal Years)
        dates = data.get("data", {}).get("metadata", {}).get("period_end_date", [])
        # QuickFS dates are usually YYYY-MM-DD. We just want the Year.
        years_list = [d.split("-")[0] for d in dates]
        
        # Define the metrics we want to track
        # Map: Display Name -> [List of QuickFS Keys to try]
        metrics_map = {
            "Revenue": ["revenue"],
            "Gross Profit": ["gross_profit"],
            "Operating Profit": ["operating_income"],
            "EBITDA": ["ebitda"],
            "NOPAT": ["nopat_derived"], # Calculated manually below
            "Net Income": ["net_income"],
            "EPS (Diluted)": ["eps_diluted"],
            "Operating Cash Flow": ["cf_cfo", "cfo"],
            "Free Cash Flow": ["fcf"]
        }

        history_data = {}
        
        # Loop through metrics and build rows
        for label, keys in metrics_map.items():
            row_data = []
            
            # 1. Get TTM Value first (Column 0)
            ttm_val = extract_ttm_metric(data, keys)
            
            # Special manual calculation for NOPAT TTM if missing
            if label == "NOPAT" and ttm_val is None:
                op = extract_ttm_metric(data, "operating_income")
                tax = extract_ttm_metric(data, "income_tax")
                if op and tax: ttm_val = op - tax
                elif op: ttm_val = op * (1 - 0.21)

            row_data.append(ttm_val)

            # 2. Get Annual History
            # Find the first valid key in 'annual' dictionary
            valid_key = next((k for k in keys if k in annual), None)
            
            if valid_key:
                annual_vals = annual[valid_key]
                # Combine NOPAT manual calc for history if needed
                if label == "NOPAT" and not any(k in annual for k in keys):
                    op_hist = annual.get("operating_income", [])
                    tax_hist = annual.get("income_tax", [])
                    annual_vals = []
                    for i in range(len(op_hist)):
                        try:
                            o = op_hist[i] or 0
                            t = tax_hist[i] or 0
                            annual_vals.append(o - t)
                        except: annual_vals.append(None)
                
                # Reverse to have newest first (conceptually), but usually API sends oldest -> newest.
                # We want a table with columns: TTM, 2023, 2022...
                # So we take the end of the list.
                # Slice last 'years'
                sliced_vals = annual_vals[-years:] 
                sliced_vals.reverse() # Newest first
                row_data.extend(sliced_vals)
            else:
                # Fill with None if missing
                row_data.extend([None] * years)

            history_data[label] = row_data

        # Create Columns: TTM + Last N Years
        cols = ["TTM"]
        sliced_years = years_list[-years:]
        sliced_years.reverse()
        cols.extend(sliced_years)
        
        # Ensure row lengths match columns (pad if history is short)
        final_data = {}
        for k, v in history_data.items():
            if len(v) < len(cols):
                v.extend([None] * (len(cols) - len(v)))
            final_data[k] = v[:len(cols)]

        df = pd.DataFrame(final_data, index=cols).T # Transpose: Metrics as Rows, Years as Cols
        return df

    except Exception as e:
        st.error(f"Error processing history: {e}")
        return pd.DataFrame()

def format_currency(value, currency_symbol="$"):
    if value is None: return "N/A"
    abs_val = abs(value)
    if abs_val >= 1_000_000_000: return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000: return f"{currency_symbol}{value / 1_000_000:.2f}M"
    else: return f"{currency_symbol}{value:,.2f}"

def render_card(label, value_str, description_html, accent_color="#4285F4"):
    html = f"""
    <div class="metric-card" style="border-top: 4px solid {accent_color};">
        <div><h4 class="metric-label">{label}</h4><div class="metric-value">{value_str}</div></div>
        <div class="metric-desc">{description_html}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Main App ---
st.set_page_config(page_title="Financial Dashboard", layout="wide")

with st.sidebar:
    st.header("Search")
    
    # 1. Search Logic
    search_input = st.text_input("Enter Ticker (e.g. AAPL:US)", value="")
    
    st.markdown("**Quick Select:**")
    selected_example = st.selectbox("Choose Example", ["(Custom Search)"] + list(EXAMPLE_STOCKS.keys()))
    
    # Determine which ticker to use
    if search_input:
        target_ticker = search_input.strip()
    elif selected_example != "(Custom Search)":
        target_ticker = EXAMPLE_STOCKS[selected_example]
    else:
        target_ticker = "DNP:PL" # Default

    st.markdown("---")
    
    # 2. View Filters
    st.subheader("Data Settings")
    view_mode = st.radio("View Mode", ["TTM Snapshot", "10-Year History"])
    
    st.markdown("---")
    st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode, on_change=toggle_dark_mode)
    st.caption("Data source: **QuickFS API**")

local_css(st.session_state.dark_mode)

# Fetch Data
json_data = fetch_quickfs_data(target_ticker, API_KEY)

if json_data:
    meta = json_data.get("data", {}).get("metadata", {})
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"{meta.get('name', target_ticker)}")
        st.markdown(f"#### Ticker: **{target_ticker}** | Currency: **{currency}**")
    st.divider()

    # --- VIEW 1: TTM SNAPSHOT (Original Card View) ---
    if view_mode == "TTM Snapshot":
        # Data Extraction
        rev = extract_ttm_metric(json_data, "revenue")
        gp = extract_ttm_metric(json_data, "gross_profit")
        op = extract_ttm_metric(json_data, "operating_income")
        ebitda = extract_ttm_metric(json_data, "ebitda")
        ni = extract_ttm_metric(json_data, "net_income")
        eps = extract_ttm_metric(json_data, "eps_diluted")
        
        tax = extract_ttm_metric(json_data, "income_tax")
        nopat = (op - tax) if (op and tax) else (op * (1 - 0.21) if op else None)
        
        ocf = extract_ttm_metric(json_data, ["cf_cfo", "cfo"]) 
        fcf = extract_ttm_metric(json_data, "fcf")

        # Explanations
        desc_revenue = "<ul><li>Top-line sales indicating market demand.</li><li>Reflects scale of operations.</li></ul>"
        desc_gp = "<ul><li>Revenue minus COGS. Measures production efficiency.</li><li>Negative values imply losses on every unit sold.</li></ul>"
        desc_op = "<ul><li>Gross Profit minus operating expenses (Marketing, G&A, R&D).</li><li>Shows core profitability before tax/interest.</li></ul>"
        desc_ebitda = "<ul><li>Earnings Before Interest, Taxes, Depreciation, Amortization.</li><li>Proxy for operational cash flow.</li></ul>"
        desc_nopat = "<ul><li>Net Operating Profit After Tax.</li><li>Shows potential earnings if debt-free (unlevered).</li></ul>"
        desc_ni = "<ul><li>'Bottom Line' profit for shareholders.</li><li>Official figure for P/E ratios.</li></ul>"
        desc_eps = "<ul><li>Net Income divided by shares outstanding.</li><li>Profit attributed to each share.</li></ul>"
        desc_ocf = "<ul><li>Cash generated from daily operations.</li><li>Adjusts Net Income for non-cash items.</li></ul>"
        desc_fcf = "<ul><li>Cash remaining after CapEx.</li><li>'Truly free' money for dividends/buybacks.</li></ul>"

        st.subheader("📊 Income Statement (TTM)")
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_card("Revenue", format_currency(rev, curr_sym), desc_revenue, "#3b82f6")
        with c2: render_card("Gross Profit", format_currency(gp, curr_sym), desc_gp, "#3b82f6")
        with c3: render_card("Operating Profit", format_currency(op, curr_sym), desc_op, "#3b82f6")
        with c4: render_card("EBITDA", format_currency(ebitda, curr_sym), desc_ebitda, "#3b82f6")
        
        st.markdown(" ")
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_card("NOPAT", format_currency(nopat, curr_sym), desc_nopat, "#3b82f6")
        with c2: render_card("Net Income", format_currency(ni, curr_sym), desc_ni, "#3b82f6")
        with c3: render_card("EPS (Diluted)", f"{curr_sym}{eps:.2f}" if eps else "N/A", desc_eps, "#3b82f6")
        with c4: st.empty()

        st.markdown("---")
        st.subheader("💸 Cash Flow (TTM)")
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_card("Operating Cash Flow", format_currency(ocf, curr_sym), desc_ocf, "#10b981")
        with c2: render_card("Free Cash Flow", format_currency(fcf, curr_sym), desc_fcf, "#10b981")
        with c3: st.empty()
        with c4: st.empty()

    # --- VIEW 2: 10-YEAR HISTORY (Table View) ---
    else:
        st.subheader(f"📅 10-Year Historical Data ({currency})")
        st.caption("Displaying Trailing Twelve Months (TTM) plus the last 10 fiscal years.")
        
        df_history = extract_historical_df(json_data, years=10)
        
        if not df_history.empty:
            # Format numbers for display in the dataframe (Millions/Billions)
            # We use a copy for display so we don't break math if we added charts later
            df_display = df_history.copy()
            for col in df_display.columns:
                df_display[col] = df_display[col].apply(lambda x: format_currency(x, curr_sym) if pd.notnull(x) else "N/A")
            
            st.dataframe(df_display, use_container_width=True, height=400)
            
            st.markdown("### 📈 Trend Visualization")
            metric_to_plot = st.selectbox("Select Metric to Plot", df_history.index.tolist())
            
            # Prepare data for chart (reverse columns so time goes left->right)
            chart_data = df_history.loc[metric_to_plot].iloc[1:] # Skip TTM for chart, usually looks better with strict years
            chart_data = chart_data.iloc[::-1] # Reverse to Oldest -> Newest
            
            st.bar_chart(chart_data)
        else:
            st.warning("Historical data not available for this ticker.")
