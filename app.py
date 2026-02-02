import streamlit as st
import requests
import pandas as pd
import numpy as np
import altair as alt

# --- PAGE CONFIG ---
st.set_page_config(page_title="Profitability Dashboard", page_icon="📘", layout="wide")

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("🚨 API Key missing! Please add `QUICKFS_API_KEY` to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- DEFINITIONS ---
SHORT_DESCRIPTIONS = {
    "1. Revenue": "Top-line sales indicate market demand for the product or service and the size of the operation.",
    "2. Gross Profit": "Revenue minus Cost of Goods Sold (COGS). Measures production efficiency.",
    "3. EBITDA": "Proxy for operational cash flow before financing effects (Interest, Taxes, Depreciation, Amortization).",
    "4. Operating Income (EBIT)": "Operating income (EBIT) is what a company earns from its core business after subtracting operating expenses.",
    "5. NOPAT": "Net Operating Profit After Tax. Shows potential cash yield if the company had no debt.",
    "6. Income Tax": "The amount paid to the government. A negative value indicates a tax benefit (refund/credit).",
    "7. Net Income": "The bottom line. Profit left for shareholders after all expenses, interest, and taxes.",
    "8. EPS (Diluted)": "Net Income divided by shares outstanding. Shows how much profit is allocated to each share.",
    "9. Operating Cash Flow": "Cash generated from actual day-to-day business operations. Adjusts Net Income for non-cash items.",
    "10. Free Cash Flow": "Operating Cash Flow minus CapEx. The truly 'free' cash available for dividends or reinvestment.",
    "11. Return on Equity (ROE)": "Net Income divided by Shareholders' Equity. Measures return on shareholders' money.",
    "12. Return on Invested Capital (ROIC)": "NOPAT divided by Total Invested Capital (Debt + Equity). Measures total business efficiency.",
    "13. Return on Capital Employed (ROCE)": "EBIT divided by Capital Employed (Assets - Current Liab). Pre-tax efficiency metric.",
    "14. Cash Return on Invested Capital (CROIC)": "Free Cash Flow divided by Invested Capital. The 'brutal' cash-based efficiency metric."
}

FULL_DEFINITIONS = {
    "1. Revenue": "Top-line sales indicate market demand for the product or service and the size of the operation.",
    "2. Gross Profit": "Gross profit equals revenue minus the cost of goods sold. It measures a company’s production efficiency—if it’s negative, the company loses money on each product before covering overhead expenses like rent or salaries. COGS (cost of goods sold) includes raw materials, manufacturing costs, and depreciation on production assets such as machinery, factory buildings, production robots, tools and vehicles used in the manufacturing process.",
    "3. EBITDA": "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortization. It is calculated as operating profit plus depreciation and amortization, and is often used as a proxy for cash flow because non-cash charges like depreciation do not represent actual cash outflows. This makes EBITDA a popular metric for valuing companies, especially in tech and infrastructure sectors, as it focuses on operational cash generation before financing and tax effects.",
    "4. Operating Income (EBIT)": "Operating income (EBIT) is what a company earns from its core business after subtracting operating expenses, but before interest and taxes (and after depreciation and amortization). Operating expenses include items like G&A (General and Administrative)—indirect costs such as office rent, utilities, administrative salaries, and insurance—and R&D (Research and Development), which covers the costs of creating or improving products, such as engineers’ salaries, lab work, and testing. Because it strips out taxes and financing choices, EBIT is a useful measure of the underlying profitability of the core business.",
    "5. NOPAT": "NOPAT (Net Operating Profit After Tax) represents the cash profit from operations. It is calculated as <b>Operating Income (EBIT) − Reported Income Tax</b>.<br><br><b>Key Scenarios:</b><br>• <b>If company pays taxes:</b> NOPAT is <i>lower</i> than EBIT.<br>• <b>If company gets a tax refund:</b> NOPAT is <i>higher</i> than EBIT. A negative tax expense (benefit) increases the after-tax profit.<br>• <b>If Net Income > NOPAT:</b> This usually happens for cash-rich companies (like Nvidia) that earn significant Interest Income, which is added to the bottom line but not to operating profit.",
    "6. Income Tax": "Income Tax represents the tax expense recognized in the income statement. A positive number indicates a tax expense paid to the government, reducing Net Income. A negative number indicates a tax benefit (or credit), which increases Net Income. This line item explains a significant portion of the difference between Operating Income and Net Income.",
    "7. Net Income": "Net income is the profit left for shareholders after paying all expenses, including suppliers, employees, interest to banks, and taxes. It is the official earnings figure used in metrics like the Price-to-Earnings (P/E) ratio and is influenced by the company’s interest costs, unlike EBIT or NOPAT.",
    "8. EPS (Diluted)": "Earnings per share (EPS) is calculated by dividing net income by the number of common shares outstanding, using only the current, actual shares in existence. It shows how much of today’s profit is allocated to each existing share an investor owns.",
    "9. Operating Cash Flow": "Operating cash flow is the cash from operations that actually comes into or leaves the company from its day-to-day business activities. It adjusts net income for non-cash items and changes in working capital, so sales made on credit (like unpaid invoices in accounts receivable) increase net income but do not increase operating cash flow until the cash is collected.",
    "10. Free Cash Flow": "Free cash flow (FCF) is the cash left over after a company pays for its operating costs and necessary investments in equipment and machinery (CapEx). It represents the truly free money that can be used to pay dividends, buy back shares, or reinvest in growth without hurting the existing business, and because it’s calculated after interest in most cases, it shows how much cash is left for shareholders after servicing debt.",
    "11. Return on Equity (ROE)": "<b>Formula:</b> Net Income ÷ Shareholders' Equity.<br><b>Meaning:</b> Measures how much return the company generates on shareholders' money alone.<br><b>Drawback:</b> Can be artificially inflated by taking on debt (leverage). A very risky company can present a high ROE.",
    "12. Return on Invested Capital (ROIC)": "<b>Formula:</b> NOPAT ÷ Total Invested Capital (Debt + Equity).<br><b>Meaning:</b> Checks the efficiency of the entire business, regardless of financing method (debt or equity). This is the preferred metric for checking for an 'Economic Moat' and competitive advantage.",
    "13. Return on Capital Employed (ROCE)": "<b>Formula:</b> EBIT ÷ Capital Employed (Total Assets − Current Liabilities).<br><b>Meaning:</b> Very similar to ROIC, but uses pre-tax profit (EBIT). Very common in heavy industrial companies and in the UK.<br><b>Difference:</b> Usually, ROCE presents a higher number than ROIC because the numerator (EBIT) is pre-tax.",
    "14. Cash Return on Invested Capital (CROIC)": "<b>Formula:</b> Free Cash Flow ÷ Invested Capital.<br><b>Meaning:</b> The 'brutal' and most honest version. It checks how much actual cash the company generated on the invested capital. This is the basis for the 'Compounder' formula."
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
    if value is None or pd.isna(value) or np.isinf(value): return "N/A"
    abs_val = abs(value)
    if abs_val >= 1_000_000_000: return f"{currency_symbol}{value / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000: return f"{currency_symbol}{value / 1_000_000:.2f}M"
    return f"{currency_symbol}{value:,.2f}"

def format_percentage(value):
    if value is None or pd.isna(value) or np.isinf(value): return "N/A"
    return f"{value * 100:.1f}%"

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
        
        # Balance Sheet items for Ratios
        equity = safe_get_list(annual, ["total_equity", "total_stockholders_equity"])
        assets = safe_get_list(annual, ["total_assets"])
        curr_liab = safe_get_list(annual, ["total_current_liabilities"])
        debt = safe_get_list(annual, ["total_debt"])

        if not dates: return None, "No historical dates found."

        length = len(dates)
        def align(arr, l): return (arr + [None]*(l-len(arr)))[:l] if len(arr) < l else arr[:l]

        df = pd.DataFrame({
            "Revenue": align(rev, length),
            "Gross Profit": align(gp, length),
            "Operating Income (EBIT)": align(op, length),
            "EBITDA": align(ebitda, length),
            "Net Income": align(ni, length),
            "EPS (Diluted)": align(eps, length),
            "Income Tax": align(tax, length),
            "Operating Cash Flow": align(cfo, length),
            "CapEx": align(capex, length),
            "FCF Reported": align(fcf, length),
            "Total Equity": align(equity, length),
            "Total Assets": align(assets, length),
            "Current Liabilities": align(curr_liab, length),
            "Total Debt": align(debt, length)
        }, index=[str(d).split('-')[0] for d in dates])

        # --- FIX: Convert all columns to numeric to safely handle NaN and avoid ZeroDivisionError ---
        df = df.apply(pd.to_numeric, errors='coerce')

        # Derived Metrics
        # NOPAT = Operating Income - Reported Income Tax
        df['NOPAT'] = df['Operating Income (EBIT)'] - df['Income Tax'].fillna(0)
        
        # FCF (Preferred: Reported, Fallback: CFO - CapEx)
        df['Free Cash Flow'] = np.where(df['FCF Reported'].notna() & (df['FCF Reported'] != 0), 
                             df['FCF Reported'], 
                             df['Operating Cash Flow'] - df['CapEx'].abs())
                             
        # --- RATIO CALCULATIONS ---
        # 11. ROE = Net Income / Equity
        # We fillna(0) for denominator or let it result in inf/nan, handled by display logic
        df['Return on Equity (ROE)'] = df['Net Income'] / df['Total Equity']
        
        # Invested Capital = Total Debt + Total Equity
        df['Invested Capital'] = df['Total Debt'].fillna(0) + df['Total Equity'].fillna(0)
        
        # 12. ROIC = NOPAT / Invested Capital
        df['Return on Invested Capital (ROIC)'] = df['NOPAT'] / df['Invested Capital']
        
        # Capital Employed = Total Assets - Current Liabilities
        df['Capital Employed'] = df['Total Assets'] - df['Current Liabilities']
        
        # 13. ROCE = EBIT / Capital Employed
        df['Return on Capital Employed (ROCE)'] = df['Operating Income (EBIT)'] / df['Capital Employed']
        
        # 14. CROIC = FCF / Invested Capital
        df['Cash Return on Invested Capital (CROIC)'] = df['Free Cash Flow'] / df['Invested Capital']

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
        
        # Quarterly Balance Sheet (Point in Time - use LAST value)
        q_equity = safe_get_list(quarterly, ["total_equity", "total_stockholders_equity"])
        q_assets = safe_get_list(quarterly, ["total_assets"])
        q_curr_liab = safe_get_list(quarterly, ["total_current_liabilities"])
        q_debt = safe_get_list(quarterly, ["total_debt"])
        
        def get_ttm_sum(arr): return sum(arr[-4:]) if arr and len(arr) >= 4 else None
        def get_last(arr): return arr[-1] if arr and len(arr) > 0 else None

        ttm_row = {
            "Revenue": get_ttm_sum(q_rev),
            "Gross Profit": get_ttm_sum(q_gp),
            "Operating Income (EBIT)": get_ttm_sum(q_op),
            "EBITDA": get_ttm_sum(q_ebitda),
            "Net Income": get_ttm_sum(q_ni),
            "EPS (Diluted)": get_ttm_sum(q_eps),
            "Income Tax": get_ttm_sum(q_tax),
            "Operating Cash Flow": get_ttm_sum(q_cfo),
            "CapEx": get_ttm_sum(q_capex),
            # BS Items
            "Total Equity": get_last(q_equity),
            "Total Assets": get_last(q_assets),
            "Current Liabilities": get_last(q_curr_liab),
            "Total Debt": get_last(q_debt)
        }
        
        op_ttm = ttm_row.get("Operating Income (EBIT)")
        tax_ttm = ttm_row.get("Income Tax") or 0
        
        # TTM Derived
        if op_ttm is not None:
            ttm_row['NOPAT'] = op_ttm - tax_ttm
        else:
            ttm_row['NOPAT'] = None
            
        if ttm_row.get("Operating Cash Flow") is not None and ttm_row.get("CapEx") is not None:
            ttm_row['Free Cash Flow'] = ttm_row["Operating Cash Flow"] - abs(ttm_row["CapEx"])
        else:
            ttm_row['Free Cash Flow'] = None
            
        # TTM Ratios
        inv_cap = (ttm_row['Total Debt'] or 0) + (ttm_row['Total Equity'] or 0)
        cap_emp = (ttm_row['Total Assets'] or 0) - (ttm_row['Current Liabilities'] or 0)
        
        ttm_row['Invested Capital'] = inv_cap if inv_cap != 0 else None
        ttm_row['Capital Employed'] = cap_emp if cap_emp != 0 else None
        
        # Safe Division for TTM
        def safe_div(n, d): return n / d if (n is not None and d) else None

        ttm_row['Return on Equity (ROE)'] = safe_div(ttm_row['Net Income'], ttm_row['Total Equity'])
        ttm_row['Return on Invested Capital (ROIC)'] = safe_div(ttm_row['NOPAT'], inv_cap)
        ttm_row['Return on Capital Employed (ROCE)'] = safe_div(ttm_row['Operating Income (EBIT)'], cap_emp)
        ttm_row['Cash Return on Invested Capital (CROIC)'] = safe_div(ttm_row['Free Cash Flow'], inv_cap)

        df_ttm = pd.DataFrame([ttm_row], index=["TTM"])
        df_final = pd.concat([df, df_ttm])
        
        # Display Columns
        cols_to_keep = [
            "Revenue", "Gross Profit", "EBITDA", "Operating Income (EBIT)", 
            "NOPAT", "Income Tax", "Net Income", "EPS (Diluted)", 
            "Operating Cash Flow", "Free Cash Flow",
            "Return on Equity (ROE)", "Return on Invested Capital (ROIC)",
            "Return on Capital Employed (ROCE)", "Cash Return on Invested Capital (CROIC)"
        ]
        return df_final[cols_to_keep], None

    except Exception as e:
        return None, f"Processing Error: {str(e)}"

def render_metric_block(col, label_key, current_val, series_data, color_code):
    """
    Renders Card -> Preview Text -> Read Details -> Currency/Percent Chart
    """
    short_desc = SHORT_DESCRIPTIONS.get(label_key, "")
    full_desc = FULL_DEFINITIONS.get(label_key, "Description not available.")
    
    # Determine Formatting
    is_percent = "Return" in label_key or "RO" in label_key
    
    if isinstance(current_val, (int, float)):
        val_str = format_percentage(current_val) if is_percent else format_currency(current_val)
    else:
        val_str = str(current_val) 
        
    with col:
        st.markdown(f"""
        <div class="metric-card" style="border-top: 4px solid {color_code};">
            <div>
                <h4 class="metric-label">{label_key}</h4>
                <div class="metric-value">{val_str}</div>
            </div>
            <p class="metric-preview">{short_desc}</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("Read Details"):
            st.markdown(f"<div style='font-size: 0.9rem; line-height: 1.4; color: #888;'>{full_desc}</div><br>", unsafe_allow_html=True)
        
        # Chart
        clean_series = series_data.dropna()
        # Remove infinite values for charting
        clean_series = clean_series[~clean_series.isin([np.inf, -np.inf])]
        
        if not clean_series.empty:
            chart_data = clean_series.reset_index()
            chart_data.columns = ['Year', 'Value']
            
            if is_percent:
                y_format = ".1%"
                tooltip_format = ".1%"
            elif "EPS" in label_key:
                y_format = "$.2f"
                tooltip_format = "$.2f"
            else:
                y_format = "$.2s"
                tooltip_format = "$,.0f"
            
            base = alt.Chart(chart_data).encode(
                x=alt.X('Year', axis=alt.Axis(labels=False, title=None, tickSize=0)),
                tooltip=[
                    alt.Tooltip('Year', title='Period'),
                    alt.Tooltip('Value', format=tooltip_format, title=label_key)
                ]
            )
            
            line = base.mark_line(color=color_code)
            points = base.mark_point(filled=True, fill=color_code, size=60)
            
            chart = (line + points).encode(
                y=alt.Y(
                    'Value', 
                    axis=alt.Axis(
                        format=y_format, 
                        title=None, 
                        labelExpr="replace(datum.label, 'G', 'B')" 
                    )
                )
            ).properties(
                height=150
            ).configure_axis(
                grid=True
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
st.title("📘 Profitability Dashboard")

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
        st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
        st.info(f"All the charts are showing values from **{start_period}** to **{end_period}**.")

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
    st.subheader(f"📊 Income Statement ({end_period})")
    c_income = "#3b82f6"
    
    # Row 1
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "1. Revenue", row['Revenue'], df_slice['Revenue'], c_income)
    render_metric_block(c2, "2. Gross Profit", row['Gross Profit'], df_slice['Gross Profit'], c_income)
    render_metric_block(c3, "3. EBITDA", row['EBITDA'], df_slice['EBITDA'], c_income)
    render_metric_block(c4, "4. Operating Income (EBIT)", row['Operating Income (EBIT)'], df_slice['Operating Income (EBIT)'], c_income)

    st.markdown("---")
    
    # Row 2
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "5. NOPAT", row['NOPAT'], df_slice['NOPAT'], c_income)
    render_metric_block(c2, "6. Income Tax", row['Income Tax'], df_slice['Income Tax'], c_income)
    render_metric_block(c3, "7. Net Income", row['Net Income'], df_slice['Net Income'], c_income)
    render_metric_block(c4, "8. EPS (Diluted)", row['EPS (Diluted)'], df_slice['EPS (Diluted)'], c_income)

    st.markdown("---")

    # 2. Cash Flow
    st.subheader(f"💸 Cash Flow ({end_period})")
    c_cash = "#10b981"
    
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "9. Operating Cash Flow", row['Operating Cash Flow'], df_slice['Operating Cash Flow'], c_cash)
    render_metric_block(c2, "10. Free Cash Flow", row['Free Cash Flow'], df_slice['Free Cash Flow'], c_cash)
    
    with c3: st.empty()
    with c4: st.empty()
    
    st.markdown("---")

    # 3. Ratios
    st.subheader(f"📈 Ratios & Return on Capital ({end_period})")
    c_ratio = "#8b5cf6"
    
    c1, c2, c3, c4 = st.columns(4)
    render_metric_block(c1, "11. Return on Equity (ROE)", row['Return on Equity (ROE)'], df_slice['Return on Equity (ROE)'], c_ratio)
    render_metric_block(c2, "12. Return on Invested Capital (ROIC)", row['Return on Invested Capital (ROIC)'], df_slice['Return on Invested Capital (ROIC)'], c_ratio)
    render_metric_block(c3, "13. Return on Capital Employed (ROCE)", row['Return on Capital Employed (ROCE)'], df_slice['Return on Capital Employed (ROCE)'], c_ratio)
    render_metric_block(c4, "14. Cash Return on Invested Capital (CROIC)", row['Cash Return on Invested Capital (CROIC)'], df_slice['Cash Return on Invested Capital (CROIC)'], c_ratio)

    # --- VIEW DATA SECTION ---
    st.write("")
    st.write("")
    with st.expander(f"View Data Table ({start_period} - {end_period})"):
        st.write("")
        st.write("")
        st.dataframe(df_slice.style.format({
            col: "{:,.0f}" if "Return" not in col else "{:.1%}" 
            for col in df_slice.columns if "EPS" not in col
        }).format({"EPS (Diluted)": "{:.2f}"}))

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
