import streamlit as st
import requests

# --- Configuration ---
# Securely access the API key from Streamlit secrets
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

STOCKS = {
    "DNP (Warsaw)": "DNP:PL",
    "Ashtead Group (London)": "AHT:LN",
    "APi Group (USA)": "APG:US"
}

# --- Custom CSS for Material Design (Min Font 1rem) ---
def local_css():
    st.markdown("""
    <style>
        /* Enforce minimum 1rem across the entire Streamlit App */
        html, body, .stApp {
            font-size: 1rem;
        }

        /* Metric Card Style */
        div.metric-card {
            background-color: #ffffff;
            border-radius: 8px;
            padding: 24px;
            box-shadow: 0 1px 2px 0 rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15);
            margin-bottom: 24px;
            height: 100%;
            transition: box-shadow 0.2s ease-in-out;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        
        div.metric-card:hover {
            box-shadow: 0 4px 8px 3px rgba(60,64,67,0.15);
        }

        /* Typography Updates for 1rem Minimum */
        h4.metric-label {
            font-family: 'Roboto', sans-serif;
            font-size: 1.1rem; 
            font-weight: 500;
            color: #5f6368;
            margin: 0 0 10px 0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        div.metric-value {
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 2.5rem; 
            font-weight: 400;
            color: #202124;
            margin-bottom: 16px;
        }
        
        p.metric-desc {
            font-family: 'Roboto', sans-serif;
            font-size: 1rem; 
            line-height: 1.6;
            color: #70757a;
            margin: 0;
            border-top: 1px solid #f1f3f4;
            padding-top: 12px;
        }
        
        /* Force Streamlit widgets to respect the minimum */
        .stMarkdown p, .stCaption, .stText, small, label, .stSelectbox label {
            font-size: 1rem !important;
        }
        
        /* Adjust layout spacing */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
    </style>
    """, unsafe_allow_html=True)

# --- Helper Functions ---
def fetch_quickfs_data(ticker, api_key):
    """Fetches full financial data from QuickFS API."""
    url = f"https://public-api.quickfs.net/v1/data/all-data/{ticker}?api_key={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data: {e}")
        return None

def extract_ttm_metric(data, metric_key):
    """Extracts TTM value, prioritizing explicit TTM keys or summing last 4 quarters."""
    try:
        financials = data.get("data", {}).get("financials", {})
        
        # 1. Try explicit TTM
        if "ttm" in financials and metric_key in financials["ttm"]:
            return financials["ttm"][metric_key]
            
        # 2. Fallback: Sum last 4 quarters
        quarterly = financials.get("quarterly", {})
        if metric_key in quarterly:
            values = quarterly[metric_key]
            if values and len(values) >= 4:
                valid_values = [v for v in values if v is not None]
                if len(valid_values) >= 4:
                    return sum(valid_values[-4:])
        return None
    except Exception:
        return None

def format_currency(value, currency_symbol="$"):
    """Formats large numbers (e.g., 1.2B, 500M)."""
    if value is None: return "N/A"
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"{currency_symbol}{value / 1_000_000:.2f}M"
    else:
        return f"{currency_symbol}{value:,.2f}"

def render_card(label, value_str, description):
    """Renders a HTML card component."""
    html = f"""
    <div class="metric-card">
        <div>
            <h4 class="metric-label">{label}</h4>
            <div class="metric-value">{value_str}</div>
        </div>
        <p class="metric-desc">{description}</p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Main App Logic ---
st.set_page_config(page_title="Financial Analyst Dashboard", layout="wide")
local_css()

# Sidebar
with st.sidebar:
    st.markdown("## Search")
    selected_stock_name = st.selectbox("Select Stock", list(STOCKS.keys()))
    selected_ticker = STOCKS[selected_stock_name]
    st.markdown("---")
    st.markdown("Data source: **QuickFS API**")

# Main Content
json_data = fetch_quickfs_data(selected_ticker, API_KEY)

if json_data:
    meta = json_data.get("data", {}).get("metadata", {})
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    st.markdown(f"## {selected_stock_name} <span style='font-size:1.5rem; color: #5f6368'>({selected_ticker})</span>", unsafe_allow_html=True)
    st.markdown("---")

    # --- Data Prep ---
    rev = extract_ttm_metric(json_data, "revenue")
    gp = extract_ttm_metric(json_data, "gross_profit")
    op = extract_ttm_metric(json_data, "operating_income")
    ebitda = extract_ttm_metric(json_data, "ebitda")
    ni = extract_ttm_metric(json_data, "net_income")
    eps = extract_ttm_metric(json_data, "eps_diluted")
    
    # NOPAT Calc (EBIT - Tax)
    tax = extract_ttm_metric(json_data, "income_tax")
    if op is not None and tax is not None:
        nopat = op - tax
    elif op is not None:
        # Fallback 21% tax assumption
        nopat = op * (1 - 0.21)
    else:
        nopat = None

    # UPDATED: Using 'cf_cfo' for Operating Cash Flow
    ocf = extract_ttm_metric(json_data, "cf_cfo") 
    fcf = extract_ttm_metric(json_data, "fcf")

    # --- Section 1: Income Statement ---
    st.subheader("Income Statement")
    
    # Row 1
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_card("Revenue", format_currency(rev, curr_sym), "Top-line sales indicating market demand.")
    with c2: render_card("Gross Profit", format_currency(gp, curr_sym), "Revenue minus cost of goods. Shows production efficiency.")
    with c3: render_card("Operating Profit (EBIT)", format_currency(op, curr_sym), "Profit from core operations before interest/tax.")
    with c4: render_card("EBITDA", format_currency(ebitda, curr_sym), "Proxy for operational cash flow (excludes non-cash items).")
    
    # Row 2
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_card("NOPAT", format_currency(nopat, curr_sym), "Potential cash earnings if the company had no debt.")
    with c2: render_card("Net Income", format_currency(ni, curr_sym), "Total earnings for shareholders after all costs.")
    with c3: render_card("EPS (Diluted)", f"{curr_sym}{eps:.2f}" if eps else "N/A", "Profit attributed to each share.")
    with c4: st.empty() 

    st.markdown("---")

    # --- Section 2: Cash Flow ---
    st.subheader("Cash Flow")
    
    # Row 3
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_card("Operating Cash Flow", format_currency(ocf, curr_sym), "Cash generated from actual business operations.")
    with c2: render_card("Free Cash Flow", format_currency(fcf, curr_sym), "Cash remaining after CapEx. The 'real' owner's earnings.")
    with c3: st.empty()
    with c4: st.empty()

else:
    st.error("Failed to load data. Please check your connection or API key.")
