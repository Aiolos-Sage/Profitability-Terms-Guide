import streamlit as st
import requests
import time

# --- Configuration ---
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

# --- CSS for Material Design ---
def local_css():
    st.markdown("""
    <style>
        html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; font-size: 1rem; }
        
        div.metric-card {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.1);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        div.metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
        }

        h4.metric-label {
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-color);
            opacity: 0.7;
            margin: 0 0 8px 0;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        div.metric-value {
            font-size: 2.2rem;
            font-weight: 700;
            color: var(--text-color);
            margin-bottom: 16px;
        }

        p.metric-desc {
            font-size: 0.95rem;
            line-height: 1.5;
            color: var(--text-color);
            opacity: 0.6;
            margin: 0;
            border-top: 1px solid rgba(128, 128, 128, 0.1);
            padding-top: 12px;
        }
        
        /* Error Box Styling */
        .stAlert {
            border-radius: 8px;
        }
    </style>
    """, unsafe_allow_html=True)

# --- Robust Data Fetching ---
def fetch_quickfs_data(ticker, api_key, retries=2):
    """
    Fetches data with retry logic and error handling.
    Retries twice if a 500 error occurs.
    """
    url = f"https://public-api.quickfs.net/v1/data/all-data/{ticker}?api_key={api_key}"
    
    for attempt in range(retries + 1):
        try:
            response = requests.get(url)
            
            # If successful, return JSON
            if response.status_code == 200:
                return response.json()
            
            # If server error (500), wait and retry
            elif response.status_code >= 500:
                if attempt < retries:
                    time.sleep(1) # Wait 1 second before retrying
                    continue
                else:
                    st.error(f"❌ QuickFS Server Error (500) for {ticker}. The API is temporarily down for this stock.")
                    return None
            
            # Client errors (404, 401, etc)
            else:
                st.error(f"❌ Error {response.status_code}: {response.reason} for {ticker}")
                return None

        except requests.exceptions.RequestException as e:
            st.error(f"🚨 Connection Error: {e}")
            return None
    return None

def extract_ttm_metric(data, metric_key):
    """Handles both explicit TTM keys and fallback lists (e.g. ['cf_cfo', 'cfo'])"""
    try:
        financials = data.get("data", {}).get("financials", {})
        keys_to_check = [metric_key] if isinstance(metric_key, str) else metric_key
        
        # 1. Try explicit TTM
        for key in keys_to_check:
            if "ttm" in financials and key in financials["ttm"]:
                return financials["ttm"][key]
            
        # 2. Try Quarterly Sum
        quarterly = financials.get("quarterly", {})
        for key in keys_to_check:
            if key in quarterly:
                values = quarterly[key]
                if values and len(values) >= 4:
                    valid_values = [v for v in values if v is not None]
                    if len(valid_values) >= 4:
                        return sum(valid_values[-4:])
        return None
    except Exception:
        return None

def format_currency(value, currency_symbol="$"):
    if value is None: return "N/A"
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"{currency_symbol}{value / 1_000_000:.2f}M"
    else:
        return f"{currency_symbol}{value:,.2f}"

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
local_css()

# Sidebar
with st.sidebar:
    st.header("Search")
    selected_stock_name = st.selectbox("Select Stock", list(STOCKS.keys()))
    selected_ticker = STOCKS[selected_stock_name]
    st.divider()
    st.caption("Data source: **QuickFS API**")

# Main Content
json_data = fetch_quickfs_data(selected_ticker, API_KEY)

if json_data:
    meta = json_data.get("data", {}).get("metadata", {})
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"{selected_stock_name}")
        st.markdown(f"#### Ticker: **{selected_ticker}**")
    
    st.divider()

    # --- Data Extraction ---
    rev = extract_ttm_metric(json_data, "revenue")
    gp = extract_ttm_metric(json_data, "gross_profit")
    op = extract_ttm_metric(json_data, "operating_income")
    ebitda = extract_ttm_metric(json_data, "ebitda")
    ni = extract_ttm_metric(json_data, "net_income")
    eps = extract_ttm_metric(json_data, "eps_diluted")
    
    tax = extract_ttm_metric(json_data, "income_tax")
    if op is not None and tax is not None:
        nopat = op - tax
    elif op is not None:
        nopat = op * (1 - 0.21)
    else:
        nopat = None

    # THE FIX FOR N/A: Check cf_cfo first, then cfo
    ocf = extract_ttm_metric(json_data, ["cf_cfo", "cfo"]) 
    fcf = extract_ttm_metric(json_data, "fcf")

    # --- Income Statement ---
    st.subheader("📊 Income Statement")
    c_income = "#3b82f6"
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_card("1. Revenue (Sales) — Top-Line", format_currency(rev, curr_sym), "Top-line sales indicate market demand for the product or service and the size of the operation.", c_income)
    with c2: render_card("2. Gross Profit (Production Efficiency)", format_currency(gp, curr_sym), "Gross profit equals revenue minus the cost of goods sold. It measures a company’s production efficiency—if it’s negative, the company loses money on each product before covering overhead expenses like rent or salaries. COGS (cost of goods sold) includes raw materials, manufacturing costs, and depreciation on production assets such as machinery, factory buildings, production robots, tools and vehicles used in the manufacturing process.", c_income)
    with c3: render_card("3. Operating Profit / EBIT (Profitability)", format_currency(op, curr_sym), "Operating profit equals gross profit minus operating expenses such as marketing, G&A, R&D, and depreciation. G&A (General and Administrative) covers indirect business costs like office rent, utilities, administrative salaries, and insurance, while R&D (Research and Development) covers costs to create or improve products, such as engineers’ salaries, lab work, and testing. It is a key measure of how profitable the core business is, without the effects of taxes and financing decisions.", c_income)
    with c4: render_card("4. EBITDA (Operating Profit)", format_currency(ebitda, curr_sym), "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortization. It is calculated as operating profit plus depreciation and amortization, and is often used as a proxy for cash flow because non-cash charges like depreciation do not represent actual cash outflows. This makes EBITDA a popular metric for valuing companies, especially in tech and infrastructure sectors, as it focuses on operational cash generation before financing and tax effects.", c_income)
    
    st.markdown(" ") 
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_card("5. NOPAT (After-Tax Operating Profit)", format_currency(nopat, curr_sym), "NOPAT shows the capital allocation efficiency, or how much profit a business makes from its operations after an estimate of taxes, but without including the effects of debt or interest. It is calculated using the formula: NOPAT = EBIT × (1 − Tax Rate). It allows investors to compare companies with different levels of debt (leverage) on an apples-to-apples basis. This “clean” operating profit is commonly used in return metrics like ROIC to assess how efficiently a company uses its capital to generate profits.", c_income)
    with c2: render_card("6. Net Income (Earnings) — Bottom-Line Profit", format_currency(ni, curr_sym), "Net income is the profit left for shareholders after paying all expenses, including suppliers, employees, interest to banks, and taxes. It is the official earnings figure used in metrics like the Price-to-Earnings (P/E) ratio and is influenced by the company’s interest costs, unlike EBIT or NOPAT.", c_income)
    with c3: render_card("7. EPS (Diluted)", f"{curr_sym}{eps:.2f}" if eps else "N/A", "Profit attributed to each share.", c_income)
    with c4: st.empty() 

    st.markdown("---")

    # --- Cash Flow ---
    st.subheader("💸 Cash Flow")
    c_cash = "#10b981"
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_card("1. Operating Cash Flow", format_currency(ocf, curr_sym), "Cash from actual operations.", c_cash)
    with c2: render_card("2. Free Cash Flow", format_currency(fcf, curr_sym), "Cash remaining after CapEx.", c_cash)
    with c3: st.empty()
    with c4: st.empty()
