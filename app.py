import streamlit as st
import requests
import pandas as pd
import numpy as np
import altair as alt

# --- PAGE CONFIG ---
st.set_page_config(page_title="Profitability Terms Guide", page_icon="📘", layout="wide")

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- DEFINITIONS ---
SHORT_DESCRIPTIONS = {
    "Revenue": "Top-line sales indicate market demand for the product or service and the size of the operation.",
    "Gross Profit": "Revenue minus Cost of Goods Sold (COGS). Measures production efficiency.",
    "Operating Profit": "Gross Profit minus operating expenses (marketing, R&D, G&A). Core business profitability.",
    "EBITDA": "Proxy for operational cash flow before financing effects (Interest, Taxes, Depreciation, Amortization).",
    "NOPAT": "Net Operating Profit After Tax. Shows potential cash yield if the company had no debt.",
    "Net Income": "The bottom line. Profit left for shareholders after all expenses, interest, and taxes.",
    "EPS": "Net Income divided by shares outstanding. Shows how much profit is allocated to each share.",
    "Operating Cash Flow": "Cash generated from actual day-to-day business operations. Adjusts Net Income for non-cash items.",
    "Free Cash Flow": "Operating Cash Flow minus CapEx. The truly 'free' cash available for dividends or reinvestment."
}

FULL_DEFINITIONS = {
    "Revenue": "Top-line sales indicate market demand for the product or service and the size of the operation.",
    "Gross Profit": "Gross profit equals revenue minus the cost of goods sold. It measures a company’s production efficiency—if it’s negative, the company loses money on each product before covering overhead expenses like rent or salaries. COGS (cost of goods sold) includes raw materials, manufacturing costs, and depreciation on production assets such as machinery, factory buildings, production robots, tools and vehicles used in the manufacturing process.",
    "Operating Profit": "Operating profit equals gross profit minus operating expenses such as marketing, G&A, R&D, and depreciation. G&A (General and Administrative) covers indirect business costs like office rent, utilities, administrative salaries, and insurance, while R&D (Research and Development) covers costs to create or improve products, such as engineers’ salaries, lab work, and testing. It is a key measure of how profitable the core business is, without the effects of taxes and financing decisions.",
    "EBITDA": "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortization. It is calculated as operating profit plus depreciation and amortization, and is often used as a proxy for cash flow because non-cash charges like depreciation do not represent actual cash outflows. This makes EBITDA a popular metric for valuing companies, especially in tech and infrastructure sectors, as it focuses on operational cash generation before financing and tax effects.",
    "NOPAT": "NOPAT shows the capital allocation efficiency, or how much profit a business makes from its operations after an estimate of taxes, but without including the effects of debt or interest. It is calculated using the formula: NOPAT = EBIT × (1 − Tax Rate). It allows investors to compare companies with different levels of debt (leverage) on an apples-to-apples basis. This “clean” operating profit is commonly used in return metrics like ROIC to assess how efficiently a company uses its capital to generate profits.",
    "Net Income": "Net income is the profit left for shareholders after paying all expenses, including suppliers, employees, interest to banks, and taxes. It is the official earnings figure used in metrics like the Price-to-Earnings (P/E) ratio and is influenced by the company’s interest costs, unlike EBIT or NOPAT.",
    "EPS": "Earnings per share (EPS) is calculated by dividing net income by the number of common shares outstanding, using only the current, actual shares in existence. It shows how much of today’s profit is allocated to each existing share an investor owns.",
    "Operating Cash Flow": "Operating cash flow is the cash from operations that actually comes into or leaves the company from its day-to-day business activities. It adjusts net income for non-cash items and changes in working capital, so sales made on credit (like unpaid invoices in accounts receivable) increase net income but do not increase operating cash flow until the cash is collected.",
    "Free Cash Flow": "Free cash flow (FCF) is the cash left over after a company pays for its operating costs and necessary investments in equipment and machinery (CapEx). It represents the truly free money that can be used to pay dividends, buy back shares, or reinvest in growth without hurting the existing business, and because it’s calculated after interest in most cases, it shows how much cash is left for shareholders after servicing debt."
}

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
        
        div.metric-card {{
            background-color: {card_bg};
            border: 1px solid {border_color};
            border-radius: 12px;
            padding: 20px 20px 10px 20px;
            box-shadow: 0 4px 6px {shadow_color};
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            margin-bottom: 5px;
        }}
        
        h4.metric-label {{ font-size: 0.85rem; font-weight: 600; color: {label_color}; text-transform: uppercase; margin: 0 0 5px 0; letter-spacing: 0.05em; }}
        div.metric-value {{ font-size: 1.8rem; font-weight: 700; color: {text_color}; margin-bottom: 5px; }}
        p.metric-preview {{ font-size: 0.9rem; color: {desc_color}; margin-bottom: 8px; line-height: 1.4; }}

        .streamlit-expanderHeader {{
            font-size: 0.85rem !important;
            color: {desc_color} !important;
            padding-left: 0 !important;
        }}
        
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

        # Derived Metrics
        df['NOPAT'] = np.where(df['Operating Profit'].notna() & df['Income Tax'].notna(), 
                               df['Operating Profit'] - df['Income Tax'],
                               df['Operating Profit'] * (1 - 0.21)) 
        
        df['Free Cash Flow'] = np.where(df['FCF Reported'].notna() & (df['FCF Reported'] != 0), 
                             df['FCF Reported'], 
                             df['Operating Cash Flow'] - df['CapEx'].abs())

        # 2. Handle TTM
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
        
        cols_to_keep = ["Revenue", "Gross Profit", "Operating Profit", "EBITDA", "NOPAT", "Net Income", "EPS", "Operating Cash Flow", "Free Cash Flow"]
        return df_final[cols_to_keep], None

    except Exception as e:
        return None, f"Processing Error: {str(e)}"

def render_metric_block(col, label_key, current_val, series_data, color_code):
    """
    Renders Card -> Preview Text -> Read Details -> Currency Chart
    """
    short_desc = SHORT_DESCRIPTIONS.get(label_key, "")
    full_desc = FULL_DEFINITIONS.get(label_key, "Description not available.")
    
    with col:
        # 1. Card Header & Value
        st.markdown(f"""
        <div class="metric-card" style="border-top: 4px solid {color_code};">
            <div>
                <h4 class="metric-label">{label_key}</h4>
                <div class="metric-value">{current_val}</div>
            </div>
            <p class="metric-preview">{short_desc}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 2. Expander (Read Details)
        with st.expander("Read Details"):
            st.markdown(f"<div style='font-size: 0.9rem; line-height: 1.4; color: #888;'>{full_desc}</div>", unsafe_allow_html=True)
        
        # 3. Altair Chart with Custom Formatting
        clean_series = series_data.dropna()
        if not clean_series.empty:
            chart_data = clean_series.reset_index()
            chart_data.columns = ['Year', 'Value']
            
            # --- CUSTOM FORMATTING LOGIC ---
            # Y Axis Format: SI prefix (s) creates "G" for billions. We replace G with B in the label expression.
            # Tooltip Format: "$,.0f" creates full currency string (e.g. $12,300,400)
            
            y_format = "$.2f" if label_key == "EPS" else "$.2s"
            tooltip_format = "$.2f" if label_key == "EPS" else "$,.0f"
            
            # Base Chart
            base = alt.Chart(chart_data).encode(
                x=alt.X('Year', axis=alt.Axis(labels=False, title=None, tickSize=0)),
                tooltip=[
                    alt.Tooltip('Year', title='Period'),
                    alt.Tooltip('Value', format=tooltip_format, title=label_key)
                ]
            )
            
            # Line Layer
            line = base.mark_line(color=color_code)
            
            # Bullet Layer (Points)
            points = base.mark_point(filled=True, fill=color_code, size=60)
            
            # Combine
            chart = (line + points).encode(
                y=alt.Y(
                    'Value', 
                    axis=alt.Axis(
                        format=y_format, 
                        title=None, 
                        labelExpr="replace(datum.label, 'G', 'B')" # Force B instead of G
                    )
                )
            ).properties(
                height=150
            ).configure_axis(
                grid=True # Show horizontal lines
            ).configure_view(
                strokeWidth=0
            )
            
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No historical data.")

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
    
    all_periods = list(df.index)
    default_end = len(all_periods) - 1
    default_start = max(0, default_end - 10)
    
    st.divider()
    c_sel1, c_sel2, c_info = st.columns([1, 1, 2])
    
    with c_sel1:
        start_period = st.selectbox("Start Date", all_periods, index=default_start)
    with c_sel2:
        try:
            s_idx = all_periods.index(start_period)
            end_options = all_periods[s_idx:]
        except:
            end_options = all_periods
        end_period = st.selectbox("End Date", end_options, index=len(end_options)-1)
    
    with c_info:
        st.info(f"Showing values for **{end_period}**. Charts show trend from **{start_period}** to **{end_period}**.")

    # Data Slicing
    try:
        s_idx = all_periods.index(start_period)
        e_idx = all_periods.index(end_period)
        df_slice = df.iloc[s_idx : e_idx + 1]
    except:
        df_slice = df
        
    row = df.loc[end_period]
    currency = meta.get("currency", "USD")
    curr_sym = "$" if currency == "USD" else (currency + " ")

    # --- RENDER SECTIONS ---
    
    # 1. Income Statement
    st.subheader("📊 Income Statement")
    c_income = "#3b82f6"
    
    # Row 1
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "Revenue", format_currency(row['Revenue'], curr_sym), 
                        df_slice['Revenue'], c_income)
                        
    render_metric_block(c2, "Gross Profit", format_currency(row['Gross Profit'], curr_sym), 
                        df_slice['Gross Profit'], c_income)
                        
    render_metric_block(c3, "Operating Profit", format_currency(row['Operating Profit'], curr_sym), 
                        df_slice['Operating Profit'], c_income)
                        
    render_metric_block(c4, "EBITDA", format_currency(row['EBITDA'], curr_sym), 
                        df_slice['EBITDA'], c_income)

    st.markdown("---")
    
    # Row 2
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "NOPAT", format_currency(row['NOPAT'], curr_sym), 
                        df_slice['NOPAT'], c_income)
                        
    render_metric_block(c2, "Net Income", format_currency(row['Net Income'], curr_sym), 
                        df_slice['Net Income'], c_income)
                        
    eps_val = row['EPS']
    eps_str = f"{curr_sym}{eps_val:.2f}" if pd.notna(eps_val) else "N/A"
    render_metric_block(c3, "EPS", eps_str, 
                        df_slice['EPS'], c_income)
                        
    with c4: st.empty()

    st.markdown("---")

    # 2. Cash Flow
    st.subheader("💸 Cash Flow")
    c_cash = "#10b981"
    
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "Operating Cash Flow", format_currency(row['Operating Cash Flow'], curr_sym), 
                        df_slice['Operating Cash Flow'], c_cash)
                        
    render_metric_block(c2, "Free Cash Flow", format_currency(row['Free Cash Flow'], curr_sym), 
                        df_slice['Free Cash Flow'], c_cash)
    
    with c3: st.empty()
    with c4: st.empty()

    # --- VIEW DATA SECTION ---
    st.write("")
    st.write("")
    with st.expander(f"View Data Table ({start_period} - {end_period})"):
        st.write("")
        st.write("")
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
