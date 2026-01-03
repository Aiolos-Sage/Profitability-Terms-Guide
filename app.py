import streamlit as st
import requests
import pandas as pd
import numpy as np
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="Profitability Terms Guide", page_icon="📘", layout="wide")

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- SESSION STATE & THEME ---
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'meta_data' not in st.session_state:
    st.session_state.meta_data = {}

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

# --- CSS STYLING (From guide-app.py) ---
def apply_css(is_dark):
    if is_dark:
        bg_color, text_color = "#0e1117", "#fafafa"
        card_bg, border_color = "#262730", "rgba(250, 250, 250, 0.1)"
        shadow_color = "rgba(0, 0, 0, 0.3)"
        label_color, desc_color = "#d0d0d0", "#b0b0b0"
    else:
        bg_color, text_color = "#ffffff", "#000000"
        card_bg, border_color = "#ffffff", "rgba(128, 128, 128, 0.1)"
        shadow_color = "rgba(0, 0, 0, 0.05)"
        label_color, desc_color = "#5f6368", "#70757a"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg_color}; color: {text_color}; }}
        html, body, [class*="css"] {{ font-family: 'Inter', 'Roboto', sans-serif; color: {text_color}; }}
        
        /* Metric Card Style */
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
        h4.metric-label {{ font-size: 0.9rem; font-weight: 600; color: {label_color}; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.05em; }}
        div.metric-value {{ font-size: 2.2rem; font-weight: 700; color: {text_color}; margin-bottom: 16px; }}
        p.metric-desc {{ font-size: 0.95rem; line-height: 1.5; color: {desc_color}; margin: 0; border-top: 1px solid {border_color}; padding-top: 12px; }}
        
        /* Input Styling Override */
        input[type="text"] {{ background-color: {card_bg} !important; color: {text_color} !important; border: 1px solid {border_color} !important; }}
    </style>
    """, unsafe_allow_html=True)

apply_css(st.session_state.dark_mode)

# --- HELPER FUNCTIONS ---
def format_currency(value, currency_symbol="$"):
    if value is None or pd.isna(value): return "N/A"
    abs_val = abs(value)
    if abs_val >= 1_000_000_000: return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000: return f"{currency_symbol}{value / 1_000_000:.2f}M"
    return f"{currency_symbol}{value:,.2f}"

def fetch_quickfs_data(ticker):
    url = f"https://public-api.quickfs.net/v1/data/all-data/{ticker}"
    params = {"api_key": API_KEY}
    try:
        r = requests.get(url, params=params)
        if r.status_code != 200: return None, f"API Error: {r.status_code}"
        data = r.json()
        if "data" not in data: return None, "Invalid data received."
        return data["data"], None
    except Exception as e:
        return None, str(e)

def safe_get_list(data_dict, keys):
    for k in keys:
        if k in data_dict and data_dict[k]:
            return data_dict[k]
    return []

def process_historical_data(raw_data):
    try:
        annual = raw_data.get("financials", {}).get("annual", {})
        quarterly = raw_data.get("financials", {}).get("quarterly", {})
        
        # 1. Extract Annual Lists
        dates = annual.get("period_end_date", annual.get("fiscal_year", []))
        rev = safe_get_list(annual, ["revenue"])
        gp = safe_get_list(annual, ["gross_profit"])
        op = safe_get_list(annual, ["operating_income"])
        ebitda = safe_get_list(annual, ["ebitda"])
        ni = safe_get_list(annual, ["net_income"])
        eps = safe_get_list(annual, ["eps_diluted"])
        tax = safe_get_list(annual, ["income_tax"])
        # Handling Fallback for CFO
        cfo = safe_get_list(annual, ["cf_cfo", "cfo", "cash_flow_operating"])
        capex = safe_get_list(annual, ["capex", "capital_expenditures"])
        fcf = safe_get_list(annual, ["fcf", "free_cash_flow"])

        if not dates: return None, "No historical dates found."

        # 2. Align Lists (pad with None or slice to min length)
        # We assume QuickFS returns aligned lists, but we handle length mismatch just in case
        length = len(dates)
        def align(arr, l): return (arr + [None]*(l-len(arr)))[:l] if len(arr) < l else arr[:l]

        df = pd.DataFrame({
            "revenue": align(rev, length),
            "gross_profit": align(gp, length),
            "operating_income": align(op, length),
            "ebitda": align(ebitda, length),
            "net_income": align(ni, length),
            "eps": align(eps, length),
            "income_tax": align(tax, length),
            "cfo": align(cfo, length),
            "capex": align(capex, length),
            "fcf_reported": align(fcf, length)
        }, index=[str(d).split('-')[0] for d in dates])

        # Calculate NOPAT and FCF (Calculated) if missing
        # NOPAT = EBIT - Tax (or EBIT * 0.79 approx if tax missing)
        df['nopat'] = np.where(df['operating_income'].notna() & df['income_tax'].notna(), 
                               df['operating_income'] - df['income_tax'],
                               df['operating_income'] * (1 - 0.21)) # Fallback
        
        # FCF Fallback
        df['fcf'] = np.where(df['fcf_reported'].notna() & (df['fcf_reported'] != 0), 
                             df['fcf_reported'], 
                             df['cfo'] - df['capex'].abs())

        # 3. Handle TTM (Append as a new row)
        q_rev = safe_get_list(quarterly, ["revenue"])
        q_gp = safe_get_list(quarterly, ["gross_profit"])
        q_op = safe_get_list(quarterly, ["operating_income"])
        q_ebitda = safe_get_list(quarterly, ["ebitda"])
        q_ni = safe_get_list(quarterly, ["net_income"])
        q_eps = safe_get_list(quarterly, ["eps_diluted"])
        q_tax = safe_get_list(quarterly, ["income_tax"])
        q_cfo = safe_get_list(quarterly, ["cf_cfo", "cfo"])
        q_capex = safe_get_list(quarterly, ["capex"])
        
        # Helper to sum last 4 quarters
        def get_ttm_sum(arr): return sum(arr[-4:]) if arr and len(arr) >= 4 else None

        ttm_row = {
            "revenue": get_ttm_sum(q_rev),
            "gross_profit": get_ttm_sum(q_gp),
            "operating_income": get_ttm_sum(q_op),
            "ebitda": get_ttm_sum(q_ebitda),
            "net_income": get_ttm_sum(q_ni),
            "eps": get_ttm_sum(q_eps),
            "income_tax": get_ttm_sum(q_tax),
            "cfo": get_ttm_sum(q_cfo),
            "capex": get_ttm_sum(q_capex),
        }
        
        # Calculate TTM derived metrics
        op_ttm = ttm_row.get("operating_income")
        tax_ttm = ttm_row.get("income_tax")
        
        if op_ttm is not None and tax_ttm is not None:
            ttm_row['nopat'] = op_ttm - tax_ttm
        elif op_ttm is not None:
            ttm_row['nopat'] = op_ttm * (1 - 0.21)
        else:
            ttm_row['nopat'] = None
            
        if ttm_row.get("cfo") is not None and ttm_row.get("capex") is not None:
            ttm_row['fcf'] = ttm_row["cfo"] - abs(ttm_row["capex"])
        else:
            ttm_row['fcf'] = None

        # Add TTM to DataFrame
        df_ttm = pd.DataFrame([ttm_row], index=["TTM"])
        df_final = pd.concat([df, df_ttm])
        
        return df_final, None

    except Exception as e:
        return None, f"Processing Error: {str(e)}"

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

# --- SIDEBAR & SEARCH ---
with st.sidebar:
    st.header("Settings")
    st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode, on_change=toggle_dark_mode)
    st.divider()
    st.markdown("### 🔍 Search Ticker")
    ticker_input = st.text_input("Enter Ticker", value="APG:US", placeholder="e.g. AAPL:US").strip().upper()
    
    if st.button("Load Financials", type="primary", use_container_width=True):
        with st.spinner("Fetching data..."):
            raw_data, error = fetch_quickfs_data(ticker_input)
            if error:
                st.error(error)
                st.session_state.data_loaded = False
            else:
                df, proc_error = process_historical_data(raw_data)
                if proc_error:
                    st.error(proc_error)
                else:
                    st.session_state.processed_df = df
                    st.session_state.meta_data = raw_data.get("metadata", {})
                    st.session_state.data_loaded = True

# --- MAIN APP ---
st.title("📘 Profitability Terms Guide")

if st.session_state.data_loaded and st.session_state.processed_df is not None:
    df = st.session_state.processed_df
    meta = st.session_state.meta_data
    
    # 1. Title Section
    st.markdown(f"## {meta.get('name', 'Unknown Company')} ({meta.get('symbol', ticker_input)})")
    
    # 2. Timeframe Selector
    available_periods = list(df.index)
    
    # Determine default indices
    default_end = len(available_periods) - 1 # TTM or last year
    default_start = max(0, default_end - 10) # 10 years ago or first year
    
    st.divider()
    c_sel1, c_sel2, c_info = st.columns([1, 1, 2])
    
    with c_sel1:
        start_period = st.selectbox("Start Date", available_periods, index=default_start)
    with c_sel2:
        # Filter end options to be >= start
        try:
            start_idx_num = available_periods.index(start_period)
            end_options = available_periods[start_idx_num:]
        except ValueError:
            end_options = available_periods
            
        end_period = st.selectbox("End Date", end_options, index=len(end_options)-1)
        
    with c_info:
        st.info(f"💡 Showing metrics for **{end_period}**. Select 'TTM' to see the most recent Trailing Twelve Months.")

    # 3. Get Data for the Selected END Period
    # For a terms guide, we display the "State" of the company at the end of the selected range
    row = df.loc[end_period]
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    # --- RENDER PROFITABILITY GUIDE ---
    
    # Income Statement Section
    st.subheader("📊 Income Statement")
    c_income = "#3b82f6"
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        render_card(
            "1. Revenue (Sales)", 
            format_currency(row['revenue'], curr_sym), 
            "Top-line sales indicate market demand for the product or service and the size of the operation.", 
            c_income
        )
    with c2: 
        render_card(
            "2. Gross Profit", 
            format_currency(row['gross_profit'], curr_sym), 
            "Revenue minus Cost of Goods Sold (COGS). Measures production efficiency. Covers raw materials and manufacturing costs.", 
            c_income
        )
    with c3: 
        render_card(
            "3. Operating Profit (EBIT)", 
            format_currency(row['operating_income'], curr_sym), 
            "Gross Profit minus operating expenses (marketing, R&D, G&A). A key measure of core business profitability before tax/interest.", 
            c_income
        )
    with c4: 
        render_card(
            "4. EBITDA", 
            format_currency(row['ebitda'], curr_sym), 
            "Earnings Before Interest, Taxes, Depreciation, and Amortization. A proxy for operational cash flow before financing effects.", 
            c_income
        )

    st.markdown(" ") # Spacer

    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        render_card(
            "5. NOPAT", 
            format_currency(row['nopat'], curr_sym), 
            "Net Operating Profit After Tax. EBIT × (1 - Tax Rate). Shows potential cash yield if the company had no debt.", 
            c_income
        )
    with c2: 
        render_card(
            "6. Net Income", 
            format_currency(row['net_income'], curr_sym), 
            "The bottom line. Profit left for shareholders after all expenses, interest, and taxes.", 
            c_income
        )
    with c3: 
        eps_val = row['eps']
        render_card(
            "7. EPS (Diluted)", 
            f"{curr_sym}{eps_val:.2f}" if pd.notna(eps_val) else "N/A", 
            "Net Income divided by shares outstanding. Shows how much profit is allocated to each share.", 
            c_income
        )
    with c4: 
        st.empty() 

    st.markdown("---")

    # Cash Flow Section
    st.subheader("💸 Cash Flow")
    c_cash = "#10b981"
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        render_card(
            "8. Operating Cash Flow", 
            format_currency(row['cfo'], curr_sym), 
            "Cash generated from actual day-to-day business operations. Adjusts Net Income for non-cash items (like depreciation).", 
            c_cash
        )
    with c2: 
        render_card(
            "9. Free Cash Flow", 
            format_currency(row['fcf'], curr_sym), 
            "Operating Cash Flow minus CapEx. The truly 'free' cash available for dividends, buybacks, or reinvestment.", 
            c_cash
        )
    with c3: st.empty()
    with c4: st.empty()

    # Data Table View (Optional but helpful for 10-year context)
    with st.expander(f"View Data Table ({start_period} - {end_period})"):
        # Slice the DF based on start/end selection
        
        # Handle TTM sorting logic (TTM usually comes after dates, but in string sort might differ)
        # We rely on the order of available_periods which was preserved from the list
        try:
            s_idx = available_periods.index(start_period)
            e_idx = available_periods.index(end_period)
            df_slice = df.iloc[s_idx : e_idx + 1]
            st.dataframe(df_slice.style.format("{:,.0f}", na_rep="N/A"))
        except:
            st.dataframe(df)

else:
    # --- LANDING STATE ---
    st.info("👈 Please enter a ticker in the sidebar to load the guide.")
    st.markdown("""
    ### About this Guide
    This tool pulls **10 years of historical data** (plus TTM) from QuickFS to illustrate key profitability terms using real-world numbers.
    
    1. **Search** for any global ticker (e.g., `AAPL:US`, `DNP:PL`).
    2. **Select a Date Range** to see how metrics have evolved.
    3. **Learn** the definitions with live data.
    """)
