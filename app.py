import streamlit as st
import os
import re
import time
import pickle
import html
import io
import pandas as pd
from datetime import datetime
from PIL import Image

import engine

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="UPI Shield — Intelligent Fraud Mitigation Gateway",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ensure Database is Initialized
engine.init_db()

# -----------------------------------------------------------------------------
# Device ID Persistence via Query Parameters
# -----------------------------------------------------------------------------
if "did" not in st.query_params or not st.query_params["did"]:
    st.query_params["did"] = f"DEV-{engine.secrets.token_hex(4).upper()}"
device_id = st.query_params["did"]

# -----------------------------------------------------------------------------
# Dynamic CSS (Inherits Native Streamlit Light / Dark Mode Automatically)
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }

    /* Adaptive Bento Cards */
    .bento-card {
        background: var(--secondary-background-color);
        border-radius: 16px;
        border: 1px solid rgba(128, 128, 128, 0.25);
        padding: 22px;
        margin-bottom: 20px;
        color: var(--text-color) !important;
    }
    
    .bento-card-title {
        font-weight: 800;
        font-size: 1.35rem;
        color: var(--text-color) !important;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    /* Metric Tiles Grid */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
        margin-top: 12px;
    }
    
    .metric-tile {
        border-radius: 14px;
        padding: 16px;
        background: rgba(128, 128, 128, 0.08);
        border: 1px solid rgba(128, 128, 128, 0.22);
    }
    
    .tile-lbl {
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        opacity: 0.8;
        color: var(--text-color) !important;
        margin-bottom: 4px;
    }
    
    .tile-val {
        font-size: 1.8rem;
        font-weight: 900;
        color: var(--text-color) !important;
    }

    /* Themed Adaptive HTML Tables */
    .themed-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
        margin-top: 8px;
    }
    
    .themed-table th {
        background-color: rgba(128, 128, 128, 0.12);
        color: var(--text-color) !important;
        padding: 12px;
        text-align: left;
        border-bottom: 2px solid rgba(128, 128, 128, 0.3);
    }
    
    .themed-table td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.18);
        color: var(--text-color) !important;
    }
    
    .themed-table tr:nth-child(even) {
        background-color: rgba(128, 128, 128, 0.04);
    }

    /* Explainable Audit Checklist Item */
    .step-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 16px;
        border-radius: 12px;
        margin-bottom: 10px;
        background: rgba(128, 128, 128, 0.07);
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    
    .step-title {
        font-weight: 700;
        font-size: 1.05rem;
        color: var(--text-color) !important;
    }
    
    .step-sub {
        font-size: 0.9rem;
        font-weight: 500;
        opacity: 0.85;
        color: var(--text-color) !important;
    }
    
    /* High-Contrast Badges */
    .badge-pass {
        background: rgba(16, 185, 129, 0.2);
        color: #10B981 !important;
        padding: 5px 14px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
        border: 1px solid #10B981;
    }
    
    .badge-hold {
        background: rgba(245, 158, 11, 0.2);
        color: #F59E0B !important;
        padding: 5px 14px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
        border: 1px solid #F59E0B;
    }
    
    .badge-block {
        background: rgba(239, 68, 68, 0.2);
        color: #EF4444 !important;
        padding: 5px 14px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
        border: 1px solid #EF4444;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Load Machine Learning Model (Random Forest Artifacts)
# -----------------------------------------------------------------------------
@st.cache_resource
def load_rf_artifacts():
    m_path = "upi_fraud_model.pkl" if os.path.exists("upi_fraud_model.pkl") else ("upi_fraud_model (3).pkl" if os.path.exists("upi_fraud_model (3).pkl") else None)
    s_path = "scaler.pkl" if os.path.exists("scaler.pkl") else ("scaler (3).pkl" if os.path.exists("scaler (3).pkl") else None)
    
    if m_path and s_path:
        try:
            with open(m_path, "rb") as f:
                model = pickle.load(f)
            with open(s_path, "rb") as f:
                scaler = pickle.load(f)
            return model, scaler, "Active Random Forest Loaded"
        except Exception as e:
            return None, None, f"Failed to deserialize artifacts: {str(e)}"
    return None, None, "Model Artifacts Missing (Fallback to Rules-Only Gateway)"

rf_model, rf_scaler, rf_status_msg = load_rf_artifacts()

# -----------------------------------------------------------------------------
# Navigation State Management & Direct Redirection Helper
# -----------------------------------------------------------------------------
pages = ["Home", "Dashboard", "Fraud Detection", "Settings"]

if "active_nav" not in st.session_state:
    st.session_state["active_nav"] = "Home"

def navigate_to(page_name):
    st.session_state["active_nav"] = page_name
    st.session_state["sidebar_nav_radio"] = page_name

# -----------------------------------------------------------------------------
# Sidebar Navigation
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🛡️ UPI Shield")
    st.caption("Intelligent Fraud Mitigation Gateway")
    
    cur_idx = pages.index(st.session_state["active_nav"]) if st.session_state["active_nav"] in pages else 0
    selected_page = st.radio("Navigation", pages, index=cur_idx, key="sidebar_nav_radio")
    
    if selected_page != st.session_state["active_nav"]:
        st.session_state["active_nav"] = selected_page
        st.rerun()

    st.markdown("---")
    st.markdown(f"**Session Device:** `{html.escape(device_id)}`")
    if "Active" in rf_status_msg:
        st.success(f"🟢 {rf_status_msg}")
    else:
        st.warning(f"🟡 {rf_status_msg}")

# -----------------------------------------------------------------------------
# Helper: Native SVG Donut Gauge
# -----------------------------------------------------------------------------
def render_donut_gauge(risk_score, tier):
    if tier == "CLEARED":
        fill_color = "#10B981"
        status_label = "CLEARED"
    elif tier == "PENDING_OTP":
        fill_color = "#F59E0B"
        status_label = "FROZEN (OTP)"
    else:
        fill_color = "#EF4444"
        status_label = "BLOCKED"

    pct = max(0.0, min(100.0, round(risk_score * 100, 1)))
    dash_val = round(pct * 2.83, 1)

    return f"""
    <div style="display:flex; align-items:center; justify-content:center; gap:28px; padding:12px 0;">
        <div style="position:relative; width:180px; height:180px;">
            <svg viewBox="0 0 100 100" style="width:180px; height:180px; transform:rotate(-90deg);">
                <circle cx="50" cy="50" r="45" fill="none" stroke="rgba(128,128,128,0.25)" stroke-width="10"/>
                <circle cx="50" cy="50" r="45" fill="none" stroke="{fill_color}" stroke-width="10"
                        stroke-dasharray="283" stroke-dashoffset="{283 - dash_val}" stroke-linecap="round"/>
            </svg>
            <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); text-align:center;">
                <div style="font-size:2.1rem; font-weight:900; color:{fill_color}; line-height:1;">{pct}%</div>
                <div style="font-size:0.85rem; font-weight:800; opacity:0.8; color:var(--text-color); margin-top:2px;">{status_label}</div>
            </div>
        </div>
        <div>
            <div style="font-size:0.95rem; font-weight:800; opacity:0.8; color:var(--text-color); text-transform:uppercase;">Composite Risk</div>
            <div style="font-size:2.0rem; font-weight:900; color:{fill_color}; margin-bottom:6px;">{status_label}</div>
            <div style="font-size:1.1rem; font-weight:800; color:var(--text-color);">Clear Margin: <strong>{round(100 - pct, 1)}%</strong></div>
        </div>
    </div>
    """

# =============================================================================
# VIEW 1: HOME PAGE
# =============================================================================
if st.session_state["active_nav"] == "Home":
    st.markdown("""
    <div style="padding: 10px 0 25px 0;">
        <h1 style="font-size: 3.2rem; font-weight: 900; margin-bottom: 8px;">🛡️ UPI Shield</h1>
        <p style="font-size: 1.35rem; font-weight: 700; opacity: 0.85; margin-bottom: 18px;">
            Intelligent Pre-Debit Fraud Mitigation Gateway
        </p>
        <p style="font-size: 1.15rem; line-height: 1.7; max-width: 850px;">
            UPI payments are frequently targeted by scam operations including fake refund requests, digital arrest extortion, 
            and token-takeover attacks. <strong>UPI Shield</strong> acts as an inline defensive barrier situated directly between the consumer 
            PSP application and bank debit settlement. Transactions undergo instantaneous multi-vector telemetry inspection using transparent 
            deterministic rules and an integrated Random Forest behavioral model.
        </p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Launch Fraud Detection Switch →", type="primary", key="home_btn_launch"):
        navigate_to("Fraud Detection")
        st.rerun()

    st.markdown("<hr style='border:none; border-top:1px solid rgba(128,128,128,0.25); margin:36px 0;'>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="bento-card">
            <div style="font-size:1.8rem; margin-bottom:10px;">⚡</div>
            <div style="font-size:1.25rem; font-weight:800; margin-bottom:8px;">Sub-20ms Interception</div>
            <div style="font-size:0.95rem; opacity:0.85; line-height:1.6;">
                Executes complete telemetry parsing, kinematics check, and ML evaluation before dispatching debit instructions.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="bento-card">
            <div style="font-size:1.8rem; margin-bottom:10px;">🌲</div>
            <div style="font-size:1.25rem; font-weight:800; margin-bottom:8px;">Random Forest & Rules</div>
            <div style="font-size:0.95rem; opacity:0.85; line-height:1.6;">
                Dual-layer detection: Hard deterministic firewalls for scam keywords and velocity, backed by a trained Random Forest classifier.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="bento-card">
            <div style="font-size:1.8rem; margin-bottom:10px;">🔒</div>
            <div style="font-size:1.25rem; font-weight:800; margin-bottom:8px;">Smart Pre-Debit Friction</div>
            <div style="font-size:0.95rem; opacity:0.85; line-height:1.6;">
                Three-tier enforcement: Instant settlement, pre-debit OTP holding freeze, or outright transaction block.
            </div>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# VIEW 2: DASHBOARD & ANALYTICS
# =============================================================================
elif st.session_state["active_nav"] == "Dashboard":
    st.markdown("## 📊 Dashboard & Operational Analytics")
    st.caption("Live operational metrics derived directly from the active SQLite ledger.")

    tab_ops, tab_mod, tab_data, tab_arch = st.tabs([
        "Live Operations", "Model Specifications", "Dataset / Training Data", "How It Works"
    ])

    with tab_ops:
        conn = engine.get_db_connection()
        df_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
        conn.close()

        if df_tx.empty:
            st.info("No transactions logged in the ledger yet. Perform a checkout in the 'Fraud Detection' tab to populate metrics.")
        else:
            total_cnt = len(df_tx)
            settled_df = df_tx[df_tx["status"] == "SUCCESS"]
            blocked_df = df_tx[df_tx["status"] == "BLOCKED"]
            val_settled = settled_df["amount"].sum()
            val_stopped = blocked_df["amount"].sum()
            avg_lat = df_tx["latency_ms"].mean()
            p95_lat = df_tx["latency_ms"].quantile(0.95)

            st.markdown(f"""
            <div class="metric-grid">
                <div class="metric-tile">
                    <div class="tile-lbl">Total Screened</div>
                    <div class="tile-val">{total_cnt}</div>
                </div>
                <div class="metric-tile">
                    <div class="tile-lbl">Settled Value</div>
                    <div class="tile-val">₹{val_settled:,.0f}</div>
                </div>
                <div class="metric-tile">
                    <div class="tile-lbl">Value Blocked</div>
                    <div class="tile-val" style="color:#EF4444;">₹{val_stopped:,.0f}</div>
                </div>
                <div class="metric-tile">
                    <div class="tile-lbl">Avg / P95 Latency</div>
                    <div class="tile-val">{avg_lat:.1f} <span style="font-size:1rem;">/ {p95_lat:.1f}ms</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            col_chart, col_signals = st.columns([1, 1])

            with col_chart:
                st.markdown("#### Decisions Distribution")
                status_counts = df_tx["status"].value_counts()
                chart_rows = ""
                for st_lbl, count in status_counts.items():
                    pct = (count / total_cnt) * 100
                    bar_color = "#EF4444" if st_lbl == "BLOCKED" else ("#10B981" if st_lbl == "SUCCESS" else "#F59E0B")
                    chart_rows += f"""
                    <div style="margin-bottom: 12px;">
                        <div style="display:flex; justify-content:space-between; font-weight:700; font-size:0.9rem; margin-bottom:4px; color:var(--text-color);">
                            <span>{html.escape(st_lbl)}</span>
                            <span>{count} ({pct:.1f}%)</span>
                        </div>
                        <div style="width:100%; height:12px; background:rgba(128,128,128,0.2); border-radius:6px; overflow:hidden;">
                            <div style="width:{pct}%; height:100%; background:{bar_color};"></div>
                        </div>
                    </div>
                    """
                st.markdown(f'<div class="bento-card">{chart_rows}</div>', unsafe_allow_html=True)

            with col_signals:
                st.markdown("#### Top Flagged Anomaly Signals")
                all_flags = []
                for f_str in df_tx["flags"].dropna():
                    if f_str.strip():
                        all_flags.extend([f.strip() for f in f_str.split(",") if f.strip()])
                
                if all_flags:
                    flag_series = pd.Series(all_flags).value_counts().head(5)
                    flag_rows = ""
                    for flg, cnt in flag_series.items():
                        flag_rows += f"<tr><td><strong>{html.escape(flg)}</strong></td><td>{cnt} occurrences</td></tr>"
                    st.markdown(f"""
                    <div class="bento-card">
                        <table class="themed-table">
                            <thead><tr><th>Anomaly Trigger</th><th>Count</th></tr></thead>
                            <tbody>{flag_rows}</tbody>
                        </table>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown('<div class="bento-card">No anomaly signals recorded yet.</div>', unsafe_allow_html=True)

    with tab_mod:
        st.markdown("#### Active Machine Learning Specifications")
        if rf_model is not None:
            n_trees = getattr(rf_model, "n_estimators", "N/A")
            max_d = getattr(rf_model, "max_depth", "None")
            criterion = getattr(rf_model, "criterion", "gini")
            
            st.markdown(f"""
            <div class="bento-card">
                <table class="themed-table">
                    <tr><td><strong>Classifier Type</strong></td><td>Random Forest Classifier (scikit-learn)</td></tr>
                    <tr><td><strong>Estimator Trees</strong></td><td>{n_trees}</td></tr>
                    <tr><td><strong>Max Depth</strong></td><td>{max_d}</td></tr>
                    <tr><td><strong>Splitting Criterion</strong></td><td>{criterion}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            if hasattr(rf_model, "feature_importances_"):
                st.markdown("##### Feature Importances")
                feat_names = ["amount", "amount_to_avg", "drain_ratio", "hour_24", "tx_count", "is_new_device", "speed_kmh", "gap_sec"]
                if len(rf_model.feature_importances_) == 9:
                    feat_names.insert(6, "dist_km")
                
                fi_df = pd.DataFrame({"Feature": feat_names[:len(rf_model.feature_importances_)], "Importance": rf_model.feature_importances_})
                fi_df = fi_df.sort_values(by="Importance", ascending=False)
                
                fi_rows = ""
                for _, r in fi_df.iterrows():
                    pct = r['Importance'] * 100
                    fi_rows += f"""
                    <div style="margin-bottom: 8px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.85rem; font-weight:700; color:var(--text-color);">
                            <span>{html.escape(r['Feature'])}</span>
                            <span>{pct:.1f}%</span>
                        </div>
                        <div style="width:100%; height:8px; background:rgba(128,128,128,0.2); border-radius:4px; overflow:hidden;">
                            <div style="width:{pct}%; height:100%; background:#E11D48;"></div>
                        </div>
                    </div>
                    """
                st.markdown(f'<div class="bento-card">{fi_rows}</div>', unsafe_allow_html=True)
        else:
            st.warning("Model pickle artifacts were not located. The system is operating safely on transparent rule firewalls.")

    with tab_data:
        st.markdown("#### Dataset & Distribution Explorer")
        uploaded_csv = st.file_uploader("Upload Transaction Dataset (CSV) for Distribution Review", type=["csv"], key="dash_csv_up")
        
        target_df = None
        if uploaded_csv is not None:
            target_df = pd.read_csv(uploaded_csv)
            st.success(f"Loaded uploaded file ({len(target_df):,} rows).")
        elif os.path.exists("upi_fraud_dataset.csv"):
            target_df = pd.read_csv("upi_fraud_dataset.csv")
            st.info(f"Auto-detected local dataset: `upi_fraud_dataset.csv` ({len(target_df):,} rows).")

        if target_df is not None:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### Feature Statistics")
                num_cols = target_df.select_dtypes(include=["float64", "int64"]).columns[:5]
                st.markdown(f"""
                <div class="bento-card">
                    <table class="themed-table">
                        <thead><tr><th>Feature</th><th>Mean</th><th>Max</th></tr></thead>
                        <tbody>
                            {''.join([f"<tr><td>{html.escape(c)}</td><td>{target_df[c].mean():.2f}</td><td>{target_df[c].max():.2f}</td></tr>" for c in num_cols])}
                        </tbody>
                    </table>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown("##### Label Distribution")
                label_candidates = [c for c in target_df.columns if "fraud" in c.lower() or "is_fraud" in c.lower() or "label" in c.lower()]
                if label_candidates:
                    lbl = label_candidates[0]
                    vc = target_df[lbl].value_counts()
                    st.markdown(f"""
                    <div class="bento-card">
                        <table class="themed-table">
                            <thead><tr><th>Class</th><th>Count</th><th>Ratio</th></tr></thead>
                            <tbody>
                                {''.join([f"<tr><td>{html.escape(str(k))}</td><td>{v:,}</td><td>{(v/len(target_df))*100:.2f}%</td></tr>" for k, v in vc.items()])}
                            </tbody>
                        </table>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown('<div class="bento-card">No explicit binary fraud label column detected.</div>', unsafe_allow_html=True)
        else:
            st.info("No CSV file uploaded or found locally on server. Upload one to examine feature baselines.")

    with tab_arch:
        st.markdown("#### Operational Logic & Architecture")
        st.markdown("""
        <div class="bento-card" style="line-height:1.8;">
            <strong>1. Telemetry Capture:</strong> Extracts sender, receiver, amount, city displacement, time, and device token.<br>
            <strong>2. Hard Rule Firewall:</strong> Immediately triggers on active liens, known scam patterns in VPAs, and kinematic travel violations (&gt;300 km/h).<br>
            <strong>3. Behavioral Random Forest:</strong> Evaluates subtle non-linear dependencies (burst velocity, account drain percentage, spending spike).
