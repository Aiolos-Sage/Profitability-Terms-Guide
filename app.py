import streamlit as st
import requests
import pandas as pd
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Profitability Terms Guide", page_icon="📘", layout="wide")

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- SESSION STATE ---
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

# --- CSS STYLING ---
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
            padding: 20px;
            box-shadow: 0 4px 6px {shadow_color};
            height: 100%; /* Ensure full height */
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            margin-bottom: 10px;
        }}
        
        h4.metric-label {{ font-size: 0.85rem; font-weight: 600; color: {label_color}; text-transform: uppercase; margin: 0 0 5px 0; letter-spacing: 0.05em; }}
        div.metric-value {{ font-size: 1.8rem; font-weight: 700; color: {text_color}; margin-bottom: 10px; }}
        p.metric-desc {{ font-size: 0.9rem; line-height: 1.4; color: {desc_color}; margin: 0; border-top: 1px solid {border_color}; padding-top: 10px; }}
        
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
        cfo = safe_get_list(annual, ["cf_cfo", "cfo", "cash_flow_operating"])
        capex = safe_get_list(annual, ["capex", "capital_expenditures"])
        fcf = safe_get_list(annual, ["fcf", "free_cash_flow"])

        if not dates: return None, "No historical dates found."

        # 2. Align Lists
        length = len(dates)
        def align(arr, l): return (arr + [None]*(l-len(arr)))[:l] if len(arr) < l else arr[:l]

        df = pd.DataFrame({
            "Revenue": align(rev, length),
            "Gross Profit": align(gp, length),
            "Operating Profit": align(op, length),
            "EBITDA": align(ebitda, length),
            "Net Income": align(ni, length),
            "EPS": align(eps, length),
            "Income Tax": align(tax, length),
            "Operating Cash Flow": align(cfo, length),
            "CapEx": align(capex, length),
            "FCF Reported": align(fcf, length)
        }, index=[str(d).split('-')[0] for d in dates])

        # Calculate Derived Metrics (NOPAT & FCF Fallback)
        # NOPAT
        df['NOPAT'] = np.where(df['Operating Profit'].notna() & df['Income Tax'].notna(), 
                               df['Operating Profit'] - df['Income Tax'],
                               df['Operating Profit'] * (1 - 0.21)) 
        
        # FCF (Preferred: Reported, Fallback: CFO - CapEx)
        df['Free Cash Flow'] = np.where(df['FCF Reported'].notna() & (df['FCF Reported'] != 0), 
                             df['FCF Reported'], 
                             df['Operating Cash Flow'] - df['CapEx'].abs())

        # 3. Handle TTM
        q_rev = safe_get_list(quarterly, ["revenue"])
        q_gp = safe_get_list(quarterly, ["gross_profit"])
        q_op = safe_get_list(quarterly, ["operating_income"])
        q_ebitda = safe_get_list(quarterly, ["ebitda"])
        q_ni = safe_get_list(quarterly, ["net_income"])
        q_eps = safe_get_list(quarterly, ["eps_diluted"])
        q_tax = safe_get_list(quarterly, ["income_tax"])
        q_cfo = safe_get_list(quarterly, ["cf_cfo", "cfo"])
        q_capex = safe_get_list(quarterly, ["capex"])
        
        def get_ttm_sum(arr): return sum(arr[-4:]) if arr and len(arr) >= 4 else None

        ttm_row = {
            "Revenue": get_ttm_sum(q_rev),
            "Gross Profit": get_ttm_sum(q_gp),
            "Operating Profit": get_ttm_sum(q_op),
            "EBITDA": get_ttm_sum(q_ebitda),
            "Net Income": get_ttm_sum(q_ni),
            "EPS": get_ttm_sum(q_eps),
            "Income Tax": get_ttm_sum(q_tax),
            "Operating Cash Flow": get_ttm_sum(q_cfo),
            "CapEx": get_ttm_sum(q_capex),
        }
        
        # TTM Derived
        op_ttm = ttm_row.get("Operating Profit")
        tax_ttm = ttm_row.get("Income Tax")
        
        if op_ttm is not None and tax_ttm is not None:
            ttm_row['NOPAT'] = op_ttm - tax_ttm
        elif op_ttm is not None:
            ttm_row['NOPAT'] = op_ttm * (1 - 0.21)
        else:
            ttm_row['NOPAT'] = None
            
        if ttm_row.get("Operating Cash Flow") is not None and ttm_row.get("CapEx") is not None:
            ttm_row['Free Cash Flow'] = ttm_row["Operating Cash Flow"] - abs(ttm_row["CapEx"])
        else:
            ttm_row['Free Cash Flow'] = None

        df_ttm = pd.DataFrame([ttm_row], index=["TTM"])
        df_final = pd.concat([df, df_ttm])
        
        # Clean columns for display/charting
        cols_to_keep = ["Revenue", "Gross Profit", "Operating Profit", "EBITDA", "NOPAT", "Net Income", "EPS", "Operating Cash Flow", "Free Cash Flow"]
        return df_final[cols_to_keep], None

    except Exception as e:
        return None, f"Processing Error: {str(e)}"

def render_metric_block(col, label, current_val, desc, series_data, color_code):
    """Renders the Card AND the Chart inside the provided column"""
    with col:
        # 1. Render Card
        st.markdown(f"""
        <div class="metric-card" style="border-top: 4px solid {color_code};">
            <div>
                <h4 class="metric-label">{label}</h4>
                <div class="metric-value">{current_val}</div>
            </div>
            <p class="metric-desc">{desc}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 2. Render Chart (Mini Trend)
        # We need a clean series for charting (drop NaNs)
        clean_series = series_data.dropna()
        if not clean_series.empty:
            st.line_chart(clean_series, height=150, use_container_width=True, color=color_code)
        else:
            st.caption("No historical data for chart.")

# --- SIDEBAR ---
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
    
    st.markdown(f"## {meta.get('name', 'Unknown Company')} ({meta.get('symbol', ticker_input)})")
    
    # --- Timeframe Selector ---
    all_periods = list(df.index)
    
    # Defaults: Start 10 years ago (or as far back as possible), End at TTM
    default_end = len(all_periods) - 1
    default_start = max(0, default_end - 10)
    
    st.divider()
    c_sel1, c_sel2, c_info = st.columns([1, 1, 2])
    
    with c_sel1:
        start_period = st.selectbox("Start Date", all_periods, index=default_start)
    with c_sel2:
        # Filter End options to be >= Start
        try:
            s_idx = all_periods.index(start_period)
            end_options = all_periods[s_idx:]
        except:
            end_options = all_periods
        end_period = st.selectbox("End Date", end_options, index=len(end_options)-1)
    
    with c_info:
        st.info(f"Showing values for **{end_period}**. Charts show trend from **{start_period}** to **{end_period}**.")

    # --- DATA SLICING ---
    # Create the subset for charts
    try:
        s_idx = all_periods.index(start_period)
        e_idx = all_periods.index(end_period)
        # Note: iloc upper bound is exclusive, so +1
        df_slice = df.iloc[s_idx : e_idx + 1]
    except:
        df_slice = df
        
    # Get current values (scalar)
    row = df.loc[end_period]
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    # --- RENDER SECTIONS ---
    
    # 1. Income Statement
    st.subheader("📊 Income Statement")
    c_income = "#3b82f6"
    
    # Row 1
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "1. Revenue (Sales)", format_currency(row['Revenue'], curr_sym), 
                        "Top-line sales indicate market demand and operation size.", 
                        df_slice['Revenue'], c_income)
                        
    render_metric_block(c2, "2. Gross Profit", format_currency(row['Gross Profit'], curr_sym), 
                        "Revenue minus COGS. Measures production efficiency.", 
                        df_slice['Gross Profit'], c_income)
                        
    render_metric_block(c3, "3. Operating Profit (EBIT)", format_currency(row['Operating Profit'], curr_sym), 
                        "Gross Profit minus OpEx. Core profitability before tax/interest.", 
                        df_slice['Operating Profit'], c_income)
                        
    render_metric_block(c4, "4. EBITDA", format_currency(row['EBITDA'], curr_sym), 
                        "Proxy for operational cash flow before financing effects.", 
                        df_slice['EBITDA'], c_income)

    st.markdown("---")
    
    # Row 2
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "5. NOPAT", format_currency(row['NOPAT'], curr_sym), 
                        "Net Operating Profit After Tax. Potential yield if no debt.", 
                        df_slice['NOPAT'], c_income)
                        
    render_metric_block(c2, "6. Net Income", format_currency(row['Net Income'], curr_sym), 
                        "Bottom line. Profit after all expenses, interest, and taxes.", 
                        df_slice['Net Income'], c_income)
                        
    eps_val = row['EPS']
    eps_str = f"{curr_sym}{eps_val:.2f}" if pd.notna(eps_val) else "N/A"
    render_metric_block(c3, "7. EPS (Diluted)", eps_str, 
                        "Net Income divided by shares outstanding.", 
                        df_slice['EPS'], c_income)
                        
    with c4: st.empty()

    st.markdown("---")

    # 2. Cash Flow
    st.subheader("💸 Cash Flow")
    c_cash = "#10b981"
    
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "8. Operating Cash Flow", format_currency(row['Operating Cash Flow'], curr_sym), 
                        "Cash from day-to-day operations. Adjusts for non-cash items.", 
                        df_slice['Operating Cash Flow'], c_cash)
                        
    render_metric_block(c2, "9. Free Cash Flow", format_currency(row['Free Cash Flow'], curr_sym), 
                        "OCF minus CapEx. Truly 'free' cash for dividends/reinvestment.", 
                        df_slice['Free Cash Flow'], c_cash)
    
    with c3: st.empty()
    with c4: st.empty()

    # --- VIEW DATA SECTION ---
    st.write("")
    st.write("") # Extra vertical space
    with st.expander(f"View Data Table ({start_period} - {end_period})"):
        st.write("")
        st.write("") # Line breaks inside expander for UI/UX
        st.dataframe(df_slice.style.format("{:,.0f}", na_rep="N/A"))

else:
    # --- LANDING PAGE ---
    st.info("👈 Enter a ticker in the sidebar to load the guide.")
    st.markdown("""
    ### About this Guide
    This tool pulls **10 years of historical data** (plus TTM) from QuickFS to illustrate key profitability terms using real-world numbers.
    
    1. **Search** for any global ticker (e.g., `AAPL:US`, `DNP:PL`).
    2. **Select a Date Range** to see how metrics have evolved.
    3. **Visualize Trends** with dynamic charts for every metric.
    """)
