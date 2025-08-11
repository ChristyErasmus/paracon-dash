
import os
import io
import time
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

st.set_page_config(page_title="Paracon Revenue Dashboards", layout="wide")

# -------- Optional password gate --------
def check_password():
    pwd = st.secrets.get("APP_PASSWORD", "")
    if not pwd:
        return True  # no password set
    with st.sidebar:
        st.subheader("Login")
        entered = st.text_input("Password", type="password")
        if st.button("Sign in"):
            st.session_state["_ok"] = (entered == pwd)
        return st.session_state.get("_ok", False)

if not check_password():
    st.stop()

# -------- Styles --------
st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem;}
.badge {background: #0A2E5C; color: #fff; padding: 0.2rem 0.5rem; border-radius: 0.5rem; font-size: 0.75rem;}
.kpi {border-radius: 1rem; padding: 1rem; background: var(--secondary-background-color);}
.kpi h3 {margin: 0.1rem 0 0.25rem 0;}
.kpi .big {font-size: 1.8rem; font-weight: 700;}
.small {opacity: 0.7; font-size: 0.85rem;}
</style>
""", unsafe_allow_html=True)

st.title("Paracon: Revenue & Forecast Dashboards")
st.caption("Upload mode (no corporate connectors required) · continuous refresh · large-data friendly")

load_dotenv()
RA_DATA_PATH = os.getenv("RA_DATA_PATH", "")
FORECAST_PATH = os.getenv("FORECAST_PATH", "")

@st.cache_data(show_spinner=False)
def read_xlsx_filelike(file, sheet, usecols=None):
    df = pd.read_excel(file, sheet_name=sheet, engine="openpyxl", dtype_backend="pyarrow", usecols=usecols)
    df.columns = [str(c).strip() for c in df.columns]
    return df

@st.cache_data(show_spinner=False)
def read_xlsx_path(path, sheet, usecols=None):
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl", dtype_backend="pyarrow", usecols=usecols)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# ---- Choose source method: paths or uploads ----
st.subheader("Data sources")
mode = st.radio("Choose input method", ["Upload files", "Use local/server file paths"], horizontal=True)

if mode == "Upload files":
    up1 = st.file_uploader("Revenue Analysis - Data Source.xlsx", type=["xlsx"], key="u1")
    up2 = st.file_uploader("FY2026 Contracting Forecast.xlsx", type=["xlsx"], key="u2")
    if not up1 or not up2:
        st.info("Upload both files to proceed.")
        st.stop()
    # detect sheets
    x1 = pd.ExcelFile(up1)
    x2 = pd.ExcelFile(up2)
    s_source = next((s for s in x1.sheet_names if s.lower()=="source"), x1.sheet_names[0])
    s_quarters = next((s for s in x1.sheet_names if s.lower() in ["quaters","quarters"]), x1.sheet_names[-1])
    s_budget = next((s for s in x2.sheet_names if s.lower()=="budget details".lower()), x2.sheet_names[0])
    s_forecast = next((s for s in x2.sheet_names if s.lower()=="forecast detail".lower()), x2.sheet_names[-1])
    df_source = read_xlsx_filelike(up1, s_source)
    df_quarters = read_xlsx_filelike(up1, s_quarters)
    df_budget = read_xlsx_filelike(up2, s_budget)
    df_forecast = read_xlsx_filelike(up2, s_forecast)
else:
    RA_DATA_PATH = st.text_input("Path to Revenue Analysis - Data Source.xlsx", RA_DATA_PATH)
    FORECAST_PATH = st.text_input("Path to FY2026 Contracting Forecast.xlsx", FORECAST_PATH)
    if not (RA_DATA_PATH and os.path.exists(RA_DATA_PATH)):
        st.warning("Set a valid path for Revenue Analysis - Data Source.xlsx")
        st.stop()
    if not (FORECAST_PATH and os.path.exists(FORECAST_PATH)):
        st.warning("Set a valid path for FY2026 Contracting Forecast.xlsx")
        st.stop()
    x1 = pd.ExcelFile(RA_DATA_PATH)
    x2 = pd.ExcelFile(FORECAST_PATH)
    s_source = next((s for s in x1.sheet_names if s.lower()=="source"), x1.sheet_names[0])
    s_quarters = next((s for s in x1.sheet_names if s.lower() in ["quaters","quarters"]), x1.sheet_names[-1])
    s_budget = next((s for s in x2.sheet_names if s.lower()=="budget details".lower()), x2.sheet_names[0])
    s_forecast = next((s for s in x2.sheet_names if s.lower()=="forecast detail".lower()), x2.sheet_names[-1])
    df_source = read_xlsx_path(RA_DATA_PATH, s_source)
    df_quarters = read_xlsx_path(RA_DATA_PATH, s_quarters)
    df_budget = read_xlsx_path(FORECAST_PATH, s_budget)
    df_forecast = read_xlsx_path(FORECAST_PATH, s_forecast)

def find_col(df, candidates):
    cols = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None

def normalize_period(series):
    s = series.astype(str).str.strip()
    parsed = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
    m = parsed.notna()
    out = pd.Series(index=series.index, dtype="datetime64[ns]")
    out[m] = parsed[m]
    if (~m).any():
        out[~m] = pd.to_datetime(s[~m], errors="coerce", dayfirst=True, infer_datetime_format=True)
    return out

# Build fact/forecast
c_client = find_col(df_source, ["Client", "Customer", "Account"])
c_amount = find_col(df_source, ["Amount", "Value", "Revenue"])
c_cost = find_col(df_source, ["Cost", "Costs", "Direct Cost"])
c_period = find_col(df_source, ["Fin Period", "Period", "Month", "Date"])

fact = df_source.copy()
fact["__Period"] = normalize_period(fact[c_period]) if c_period else pd.NaT
fact["__Revenue"] = pd.to_numeric(fact[c_amount], errors="coerce") if c_amount in fact else np.nan
fact["__Cost"] = pd.to_numeric(fact[c_cost], errors="coerce") if c_cost in fact else np.nan
fact["__GP"] = fact["__Revenue"] - fact["__Cost"]
fact["__Client"] = fact[c_client].astype(str) if c_client else "(Unmapped)"

f_client = find_col(df_forecast, ["Client", "Customer"])
f_period = find_col(df_forecast, ["Period", "Month", "Fin Period", "Date"])
f_value = find_col(df_forecast, ["Forecast", "Amount", "Value", "Revenue"])

forecast = df_forecast.copy()
forecast["__Period"] = normalize_period(forecast[f_period]) if f_period else pd.NaT
forecast["__Forecast"] = pd.to_numeric(forecast[f_value], errors="coerce") if f_value in forecast else np.nan
forecast["__Client"] = forecast[f_client].astype(str) if f_client else "(Unmapped)"

# Filters
left, right = st.columns([3,1])
with left:
    st.subheader("Filters")
    uniq_clients = sorted([c for c in fact["__Client"].dropna().unique().tolist() if c])
    default_clients = uniq_clients[:10] if len(uniq_clients) > 0 else []
    sel_clients = st.multiselect("Clients", options=uniq_clients, default=default_clients)
    date_min = pd.to_datetime(fact["__Period"].min())
    date_max = pd.to_datetime(fact["__Period"].max())
    if pd.isna(date_min) or pd.isna(date_max):
        date_min = pd.to_datetime("2024-01-01")
        date_max = pd.to_datetime("2025-12-31")
    sel_date = st.slider("Date range", min_value=date_min.to_pydatetime(), max_value=date_max.to_pydatetime(),
                         value=(date_min.to_pydatetime(), date_max.to_pydatetime()))
with right:
    st.subheader("")
    st.markdown('<span class="badge">Data loaded</span>', unsafe_allow_html=True)
    st.write("Source rows:", len(fact))
    st.write("Forecast rows:", len(forecast))

mask = (fact["__Client"].isin(sel_clients) if sel_clients else True) &        (fact["__Period"].between(pd.to_datetime(sel_date[0]), pd.to_datetime(sel_date[1])))
fmask = (forecast["__Client"].isin(sel_clients) if sel_clients else True) &         (forecast["__Period"].between(pd.to_datetime(sel_date[0]), pd.to_datetime(sel_date[1])))
fact_f = fact[mask].copy()
forecast_f = forecast[fmask].copy()

# KPIs
k1, k2, k3, k4 = st.columns(4)
rev = fact_f["__Revenue"].sum(skipna=True)
cost = fact_f["__Cost"].sum(skipna=True)
gp = fact_f["__GP"].sum(skipna=True)
margin = (gp / rev * 100) if pd.notna(rev) and rev != 0 else np.nan

for col, title, val, fmt in [
    (k1, "Revenue", rev, "R{:,.0f}"),
    (k2, "Cost", cost, "R{:,.0f}"),
    (k3, "Gross Profit", gp, "R{:,.0f}"),
    (k4, "Margin %", margin, "{:,.1f}%"),
]:
    with col:
        st.markdown('<div class="kpi">', unsafe_allow_html=True)
        st.markdown(f"<h3>{title}</h3>", unsafe_allow_html=True)
        if pd.isna(val):
            st.markdown(f'<div class="big">–</div><div class="small">No data</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="big">{fmt.format(val)}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# Charts
st.divider()
st.subheader("Trends & Top Clients")

if fact_f["__Period"].notna().any():
    ts = (fact_f.dropna(subset=["__Period"])
          .assign(Period=lambda d: d["__Period"].dt.to_period("M").dt.to_timestamp())
          .groupby("Period", as_index=False)["__Revenue"].sum())
    st.plotly_chart(px.line(ts, x="Period", y="__Revenue", title="Revenue trend"), use_container_width=True)

top_clients = (fact_f.groupby("__Client", as_index=False)["__Revenue"].sum()
               .sort_values("__Revenue", ascending=False).head(15))
if len(top_clients) > 0:
    fig2 = px.bar(top_clients, x="__Client", y="__Revenue", title="Top clients by revenue")
    fig2.update_layout(xaxis_title="", yaxis_title="Revenue", xaxis_tickangle=-30)
    st.plotly_chart(fig2, use_container_width=True)

if forecast_f["__Period"].notna().any():
    act = (fact_f.dropna(subset=["__Period"])
           .assign(Period=lambda d: d["__Period"].dt.to_period("M").dt.to_timestamp())
           .groupby("Period", as_index=False)["__Revenue"].sum()
           .rename(columns={"__Revenue": "Actual"}))
    fc = (forecast_f.dropna(subset=["__Period"])
           .assign(Period=lambda d: d["__Period"].dt.to_period("M").dt.to_timestamp())
           .groupby("Period", as_index=False)["__Forecast"].sum()
           .rename(columns={"__Forecast": "Forecast"}))
    af = pd.merge(act, fc, on="Period", how="outer").sort_values("Period")
    if len(af) > 0:
        fig3 = px.bar(af.melt(id_vars="Period", value_vars=["Actual", "Forecast"],
                              var_name="Type", value_name="Amount"),
                      x="Period", y="Amount", color="Type",
                      title="Actual vs Forecast (Monthly)")
        st.plotly_chart(fig3, use_container_width=True)

st.divider()
st.subheader("Data Explorer")
tab1, tab2, tab3 = st.tabs(["Source fact", "Forecast detail", "Quarters map"])
with tab1:
    st.dataframe(fact_f.head(1000))
with tab2:
    st.dataframe(forecast_f.head(1000))
with tab3:
    st.dataframe(df_quarters.head(1000))

st.caption("Set APP_PASSWORD in Streamlit > Settings > Secrets to restrict access.")
