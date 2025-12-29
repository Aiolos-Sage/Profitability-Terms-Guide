import streamlit as st
import requests
import pandas as pd

# --- Configuration ---
API_KEY = "00b9c73b6efbcec191ef17c4450743a1e741e794"
STOCKS = {
    "DNP (Warsaw)": "DNP:PL",
    "Ashtead Group (London)": "AHT:LN",
    "APi Group (USA)": "APG:US"
}

# --- Helper Functions ---
def fetch_quickfs_data(ticker, api_key):
    """Fetches full financial data from QuickFS API."""
    url = f"https://public-api.quickfs.net/v1/data/all-data/{ticker}?api_key={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

def extract_ttm_metric(data, metric_key):
    """
    Extracts the TTM value for a specific metric.
    Prioritizes explicit 'ttm' keys, otherwise calculates from the last 4 quarters.
    """
    try:
        financials = data.get("data", {}).get("financials", {})
        
        # 1. Try to find explicit TTM dictionary
        if "ttm" in financials and metric_key in financials["ttm"]:
            return financials["ttm"][metric_key]
            
        # 2. Fallback: Sum last 4 quarters (if available)
        # Note: This works for Flow metrics (Revenue, Income, Cash Flow), not Balance Sheet.
        quarterly = financials.get("quarterly", {})
        if metric_key in quarterly:
            values = quarterly[metric_key]
            # Ensure we have at least 4 quarters to calculate TTM
            if values and len(values) >= 4:
                # Get the last 4 non-null values
                valid_values = [v for v in values if v is not None]
                if len(valid_values) >= 4:
                    return sum(valid_values[-4:])
        
        return None
    except Exception as e:
        return None

def format_currency(value, currency_symbol="$"):
    """Formats large numbers into readable strings (e.g., 1.2B, 500M)."""
    if value is None:
        return "N/A"
    
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"{currency_symbol}{value / 1_000_000:.2f}M"
    else:
        return f"{currency_symbol}{value:,.2f}"

# --- Main App Logic ---
st.set_page_config(page_title="Financial Analyst Dashboard", layout="wide")

st.title("Financial Analyst Dashboard")
st.markdown("### Fundamental Analysis: TTM Metrics")

# Sidebar for Stock Selection
selected_stock_name = st.sidebar.selectbox("Select Stock", list(STOCKS.keys()))
selected_ticker = STOCKS[selected_stock_name]

# Fetch Data
with st.spinner(f"Fetching data for {selected_ticker}..."):
    json_data = fetch_quickfs_data(selected_ticker, API_KEY)

if json_data:
    # Metadata
    meta = json_data.get("data", {}).get("metadata", {})
    currency = meta.get("currency", "USD")
    currency_symbol = "$" if currency == "USD" else (currency + " ")
    
    st.header(f"{selected_stock_name} ({selected_ticker})")
    st.caption(f"Reporting Currency: {currency}")

    # --- 1. Accounting Metrics (Income Statement) ---
    st.subheader("1. Accounting Metrics (Income Statement)")
    
    col1, col2 = st.columns([1, 2])

    # Metric Extraction
    revenue = extract_ttm_metric(json_data, "revenue")
    gross_profit = extract_ttm_metric(json_data, "gross_profit")
    operating_profit = extract_ttm_metric(json_data, "operating_income")
    ebitda = extract_ttm_metric(json_data, "ebitda")
    net_income = extract_ttm_metric(json_data, "net_income")
    eps = extract_ttm_metric(json_data, "eps_diluted")
    
    # NOPAT Calculation: EBIT * (1 - Tax Rate) if not explicit
    # Using a simplified 21% tax assumption if actual tax rate isn't easily derived, 
    # or trying to fetch explicit key if QuickFS provides it (often they don't explicitly in basic endpoints).
    # Here we calculate it manually: EBIT - Income Tax Expense (from TTM)
    income_tax = extract_ttm_metric(json_data, "income_tax")
    if operating_profit is not None and income_tax is not None:
         nopat = operating_profit - income_tax
    elif operating_profit is not None:
         # Fallback to standard 21% assumption if tax data missing
         nopat = operating_profit * (1 - 0.21) 
    else:
         nopat = None

    metrics_is = [
        ("1.2 Revenue (TTM)", revenue, 
         "Top-line sales growth indicates market demand and business scalability. Consistent growth is key for long-term value."),
        ("1.3 Gross Profit (TTM)", gross_profit, 
         "Measures production efficiency. High gross profit provides a buffer for operating expenses and R&D."),
        ("1.4 Operating Profit / EBIT (TTM)", operating_profit, 
         "Core business profitability before interest and taxes. It shows how viable the business model is operationally."),
        ("1.5 NOPAT (TTM)", nopat, 
         "Net Operating Profit After Tax. It represents the potential cash earnings if the company had no debt (unlevered), crucial for ROIC analysis."),
        ("1.6 EBITDA (TTM)", ebitda, 
         "Proxy for operating cash flow. It removes non-cash accounting decisions (depreciation) and capital structure (interest) to compare pure operational performance."),
        ("1.7 Net Income (TTM)", net_income, 
         "The 'bottom line'. It shows total earnings available to shareholders after all costs, interest, and taxes."),
        ("1.8 EPS (Diluted) (TTM)", eps, 
         "Earnings Per Share. The primary driver of stock price; shows how much profit is attributed to each share held by an investor.")
    ]

    for label, val, desc in metrics_is:
        with st.container():
            c1, c2 = st.columns([1, 3])
            val_fmt = format_currency(val, currency_symbol) if "EPS" not in label else f"{currency_symbol}{val:.2f}"
            c1.metric(label=label.split(" (")[0], value=val_fmt)
            c2.markdown(f"**What it shows to investors?**\n\n{desc}")
            st.divider()

    # --- 2. Cash Flow Metrics ---
    st.subheader("2. Cash Flow Metrics (Cash Flow Statement)")

    # Metric Extraction
    ocf = extract_ttm_metric(json_data, "cfo") # QuickFS key for Operating Cash Flow often 'cfo'
    fcf = extract_ttm_metric(json_data, "fcf") # QuickFS key for Free Cash Flow often 'fcf'

    metrics_cf = [
        ("2.1 Operating Cash Flow (OCF)", ocf, 
         "Cash generated from actual business operations. Unlike Net Income, it cannot be easily manipulated by accounting adjustments. It proves the quality of earnings."),
        ("2.2 Free Cash Flow (FCF)", fcf, 
         "The cash remaining after maintaining capital assets (CapEx). This is the 'real' owner's earnings available for dividends, buybacks, debt paydown, or reinvestment.")
    ]

    for label, val, desc in metrics_cf:
        with st.container():
            c1, c2 = st.columns([1, 3])
            c1.metric(label=label.split(" (")[0], value=format_currency(val, currency_symbol))
            c2.markdown(f"**What it shows to investors?**\n\n{desc}")
            st.divider()

else:
    st.warning("Please check the API key or connection.")
