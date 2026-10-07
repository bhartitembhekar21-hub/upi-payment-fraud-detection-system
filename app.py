import streamlit as st
import os
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
# Device ID & Theme Persistence via Query Parameters
# -----------------------------------------------------------------------------
if "did" not in st.query_params or not st.query_params["did"]:
    st.query_params["did"] = f"DEV-{engine.secrets.token_hex(4).upper()}"
device_id = st.query_params["did"]

if "theme" not in st.query_params or st.query_params["theme"] not in ["light", "dark"]:
    st.query_params["theme"] = "light"
current_theme = st.query_params["theme"]

# -----------------------------------------------------------------------------
# Dynamic CSS Palette Injections (Light / Dark Mode Support)
# -----------------------------------------------------------------------------
if current_theme == "dark":
    css_vars = """
    :root {
        --bg-main: #0B0F17;
        --bg-card: #151D2A;
        --bg-card-sub: #1E293B;
        --border-color: #334155;
        --text-primary: #F8FAFC;
        --text-secondary: #94A3B8;
        --accent: #E11D48;
        --accent-hover: #BE123C;
        --table-row-even: #111827;
        --table-row-odd: #1F2937;
        --status-pass-bg: #064E3B;
        --status-pass-txt: #6EE7B7;
        --status-hold-bg: #78350F;
        --status-hold-txt: #FCD34D;
        --status-block-bg: #7F1D1D;
        --status-block-txt: #FCA5A5;
    }
    """
else:
    css_vars = """
    :root {
        --bg-main: #F8FAFC;
        --bg-card: #FFFFFF;
        --bg-card-sub: #F1F5F9;
        --border-color: #CBD5E1;
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --accent: #E11D48;
        --accent-hover: #BE123C;
        --table-row-even: #FFFFFF;
        --table-row-odd: #F8FAFC;
        --status-pass-bg: #DCFCE7;
        --status-pass-txt: #166534;
        --status-hold-bg: #FEF3C7;
        --status-hold-txt: #92400E;
        --status-block-bg: #FEE2E2;
        --status-block-txt: #991B1B;
    }
    """

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap');
    {css_vars}
    
    html, body, [class*="css"], .stApp {{
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        background-color: var(--bg-main) !important;
        color: var(--text-primary) !important;
    }}
    
    section[data-testid="stSidebar"] {{
        background-color: var(--bg-card) !important;
        border-right: 1px solid var(--border-color) !important;
    }}

    .bento-card {{
        background: var(--bg-card);
        border-radius: 16px;
        border: 1px solid var(--border-color);
        padding: 22px;
        margin-bottom: 20px;
    }}
    
    .bento-card-title {{
        font-weight: 800;
        font-size: 1.35rem;
        color: var(--text-primary);
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 10px;
    }}

    .metric-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
        margin-top: 12px;
    }}
    
    .metric-tile {{
        border-radius: 14px;
        padding: 16px;
        background: var(--bg-card-sub);
        border: 1px solid var(--border-color);
    }}
    
    .tile-lbl {{
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        color: var(--text-secondary);
        margin-bottom: 4px;
    }}
    
    .tile-val {{
        font-size: 1.8rem;
        font-weight: 900;
        color: var(--text-primary);
    }}

    .themed-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
        margin-top: 8px;
    }}
    
    .themed-table th {{
        background-color: var(--bg-card-sub);
        color: var(--text-primary);
        padding: 12px;
        text-align: left;
        border-bottom: 2px solid var(--border-color);
    }}
    
    .themed-table td {{
        padding: 10px 12px;
        border-bottom: 1px solid var(--border-color);
        color: var(--text-primary);
    }}
    
    .themed-table tr:nth-child(even) {{
        background-color: var(--table-row-even);
    }}
    
    .themed-table tr:nth-child(odd) {{
        background-color: var(--table-row-odd);
    }}

    .step-item {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 16px;
        border-radius: 12px;
        margin-bottom: 10px;
        background: var(--bg-card-sub);
        border: 1px solid var(--border-color);
    }}
    
    .step-title {{
        font-weight: 700;
        font-size: 1.05rem;
        color: var(--text-primary);
    }}
    
    .step-sub {{
        font-size: 0.9rem;
        font-weight: 500;
        color: var(--text-secondary);
    }}
    
    .badge-pass {{
        background: var(--status-pass-bg);
        color: var(--status-pass-txt);
        padding: 4px 12px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
    }}
    
    .badge-hold {{
        background: var(--status-hold-bg);
        color: var(--status-hold-txt);
        padding: 4px 12px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
    }}
    
    .badge-block {{
        background: var(--status-block-bg);
        color: var(--status-block-txt);
        padding: 4px 12px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.85rem;
    }}
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
# Navigation State Management
# -----------------------------------------------------------------------------
if "active_nav" not in st.session_state:
    st.session_state["active_nav"] = "Home"

def set_page(name):
    st.session_state["active_nav"] = name

# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🛡️ UPI Shield")
    st.caption("Intelligent Fraud Mitigation Gateway")
    
    pages = ["Home", "Dashboard", "Fraud Detection", "Settings"]
    cur_idx = pages.index(st.session_state["active_nav"]) if st.session_state["active_nav"] in pages else 0
    selected_page = st.radio("Navigation", pages, index=cur_idx, key="sidebar_nav_radio")
    if selected_page != st.session_state["active_nav"]:
        st.session_state["active_nav"] = selected_page
        st.rerun()

    st.markdown("---")
    
    # Theme Toggle
    is_dark = (current_theme == "dark")
    toggle_theme = st.checkbox("🌙 Enable Dark Mode", value=is_dark, key="chk_theme_toggle")
    new_theme = "dark" if toggle_theme else "light"
    if new_theme != current_theme:
        st.query_params["theme"] = new_theme
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
                <circle cx="50" cy="50" r="45" fill="none" stroke="var(--border-color)" stroke-width="10"/>
                <circle cx="50" cy="50" r="45" fill="none" stroke="{fill_color}" stroke-width="10"
                        stroke-dasharray="283" stroke-dashoffset="{283 - dash_val}" stroke-linecap="round"/>
            </svg>
            <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); text-align:center;">
                <div style="font-size:2.1rem; font-weight:900; color:{fill_color}; line-height:1;">{pct}%</div>
                <div style="font-size:0.85rem; font-weight:800; color:var(--text-secondary); margin-top:2px;">{status_label}</div>
            </div>
        </div>
        <div>
            <div style="font-size:0.95rem; font-weight:800; color:var(--text-secondary); text-transform:uppercase;">Composite Risk</div>
            <div style="font-size:2.0rem; font-weight:900; color:{fill_color}; margin-bottom:6px;">{status_label}</div>
            <div style="font-size:1.1rem; font-weight:800; color:var(--text-primary);">Clear Margin: <strong>{round(100 - pct, 1)}%</strong></div>
        </div>
    </div>
    """

# =============================================================================
# VIEW 1: HOME PAGE
# =============================================================================
if st.session_state["active_nav"] == "Home":
    st.markdown("""
    <div style="padding: 20px 0 30px 0;">
        <h1 style="font-size: 3.2rem; font-weight: 900; margin-bottom: 8px;">🛡️ UPI Shield</h1>
        <p style="font-size: 1.4rem; font-weight: 700; color: var(--text-secondary); margin-bottom: 20px;">
            Intelligent Pre-Debit Fraud Mitigation Gateway
        </p>
        <p style="font-size: 1.15rem; line-height: 1.7; max-width: 850px; color: var(--text-primary);">
            UPI payments are frequently targeted by scam operations including fake refund requests, digital arrest extortion, 
            and token-takeover attacks. <strong>UPI Shield</strong> acts as an inline defensive barrier situated directly between the consumer 
            PSP application and bank debit settlement. Transactions undergo instantaneous multi-vector telemetry inspection using transparent 
            deterministic rules and an integrated Random Forest behavioral model.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.button("Launch Fraud Detection Switch →", type="primary", on_click=set_page, args=("Fraud Detection",), key="home_btn_launch")

    st.markdown("<hr style='border:none; border-top:1px solid var(--border-color); margin:40px 0;'>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="bento-card">
            <div style="font-size:1.8rem; margin-bottom:10px;">⚡</div>
            <div style="font-size:1.25rem; font-weight:800; margin-bottom:8px;">Sub-20ms Interception</div>
            <div style="font-size:0.95rem; color:var(--text-secondary); line-height:1.6;">
                Executes complete telemetry parsing, kinematics check, and ML evaluation before dispatching debit instructions.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="bento-card">
            <div style="font-size:1.8rem; margin-bottom:10px;">🌲</div>
            <div style="font-size:1.25rem; font-weight:800; margin-bottom:8px;">Random Forest & Rules</div>
            <div style="font-size:0.95rem; color:var(--text-secondary); line-height:1.6;">
                Dual-layer detection: Hard deterministic firewalls for scam keywords and velocity, backed by a trained Random Forest classifier.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="bento-card">
            <div style="font-size:1.8rem; margin-bottom:10px;">🔒</div>
            <div style="font-size:1.25rem; font-weight:800; margin-bottom:8px;">Smart Pre-Debit Friction</div>
            <div style="font-size:0.95rem; color:var(--text-secondary); line-height:1.6;">
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
                    <div class="tile-val" style="color:var(--status-block-txt);">₹{val_stopped:,.0f}</div>
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
                    bar_color = "var(--accent)" if st_lbl == "BLOCKED" else ("#10B981" if st_lbl == "SUCCESS" else "#F59E0B")
                    chart_rows += f"""
                    <div style="margin-bottom: 12px;">
                        <div style="display:flex; justify-content:space-between; font-weight:700; font-size:0.9rem; margin-bottom:4px;">
                            <span>{html.escape(st_lbl)}</span>
                            <span>{count} ({pct:.1f}%)</span>
                        </div>
                        <div style="width:100%; height:12px; background:var(--bg-card-sub); border-radius:6px; overflow:hidden;">
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
                        <div style="display:flex; justify-content:space-between; font-size:0.85rem; font-weight:700;">
                            <span>{html.escape(r['Feature'])}</span>
                            <span>{pct:.1f}%</span>
                        </div>
                        <div style="width:100%; height:8px; background:var(--bg-card-sub); border-radius:4px; overflow:hidden;">
                            <div style="width:{pct}%; height:100%; background:var(--accent);"></div>
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
            <strong>3. Behavioral Random Forest:</strong> Evaluates subtle non-linear dependencies (burst velocity, account drain percentage, spending spike).<br>
            <strong>4. Composite Multi-Tier Decision:</strong>
            <ul>
                <li><strong>CLEARED:</strong> All safety margins verified. Direct instant debit.</li>
                <li><strong>PENDING_OTP:</strong> Pre-debit hold engaged. Funds reserved; authorization requires step-up OTP challenge.</li>
                <li><strong>BLOCKED:</strong> High risk anomaly threshold violated. Dropped before debit occurs.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# VIEW 3: FRAUD DETECTION GATEWAY
# =============================================================================
elif st.session_state["active_nav"] == "Fraud Detection":
    st.markdown("## 🛡️ Fraud Detection Gateway")
    st.caption("Perform real-time payments, inspect transactions, or stress-test scenarios.")

    tab_checkout, tab_stress, tab_ledger = st.tabs([
        "⚡ Merchant Checkout", "📋 Manual Analysis & Stress-Testing", "📑 Ledger & Remediation"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Merchant Checkout
    # -------------------------------------------------------------------------
    with tab_checkout:
        col_pay_form, col_telemetry = st.columns([1.1, 1])

        with col_pay_form:
            st.markdown('<div class="bento-card">', unsafe_allow_html=True)
            st.markdown('<div class="bento-card-title">💳 Client Payment Terminal</div>', unsafe_allow_html=True)

            # Account Selector
            conn = engine.get_db_connection()
            accounts = conn.execute("SELECT * FROM accounts WHERE is_merchant = 0").fetchall()
            conn.close()

            acc_map = {f"{r['name']} ({r['persona']})": r['vpa'] for r in accounts}
            sel_acc_label = st.selectbox("Debit From Account:", list(acc_map.keys()), key="chk_acc_sel")
            active_sender_vpa = acc_map[sel_acc_label]

            # Fetch Balances
            conn = engine.get_db_connection()
            s_acc = conn.execute("SELECT * FROM accounts WHERE vpa = ?", (active_sender_vpa,)).fetchone()
            c_res = conn.execute("SELECT SUM(amount) as reserved FROM transactions WHERE sender_vpa = ? AND status = 'PENDING_OTP'", (active_sender_vpa,)).fetchone()
            reserved = c_res["reserved"] if c_res and c_res["reserved"] else 0.0
            avail_balance = s_acc["balance"] - reserved

            # Trust Device Check
            c_dev = conn.execute("SELECT * FROM devices WHERE account_vpa = ? AND device_id = ?", (active_sender_vpa, device_id)).fetchone()
            conn.close()

            dev_trusted = (c_dev is not None)
            st.markdown(f"""
            <div style="font-size:0.95rem; margin: 8px 0 16px 0; color:var(--text-secondary);">
                Ledger Balance: <strong>₹{s_acc['balance']:,.2f}</strong> &nbsp;|&nbsp; 
                Available: <strong>₹{avail_balance:,.2f}</strong> &nbsp;|&nbsp; 
                Device Trust: <strong>{'🟢 Trusted' if dev_trusted else '⚠️ New / Unknown'}</strong>
            </div>
            """, unsafe_allow_html=True)

            if not dev_trusted:
                if st.button("Register & Trust This Device", key="btn_trust_dev"):
                    conn = engine.get_db_connection()
                    conn.execute("INSERT OR IGNORE INTO devices (account_vpa, device_id) VALUES (?, ?)", (active_sender_vpa, device_id))
                    conn.commit()
                    conn.close()
                    st.success("Current device added to trusted list.")
                    st.rerun()

            # Method Selector
            pay_method = st.radio("Payment Method", ["UPI ID / VPA", "Scan / Upload QR", "UPI Deep Link"], horizontal=True, key="chk_method_radio")

            target_payee = ""
            target_amount = 0.0

            if pay_method == "UPI ID / VPA":
                target_payee = st.text_input("Beneficiary UPI ID:", "chai_point@upi", key="chk_vpa_input")
                target_amount = st.number_input("Amount (₹):", min_value=1.0, value=50.0, step=10.0, key="chk_amt_input")

            elif pay_method == "Scan / Upload QR":
                qr_file = st.file_uploader("Upload QR Code Image:", type=["png", "jpg", "jpeg"], key="chk_qr_file")
                if qr_file is not None:
                    raw_bytes = qr_file.read()
                    data, err = engine.decode_qr_image(raw_bytes)
                    if data:
                        valid, parsed, msg = engine.parse_upi_uri(data)
                        if valid:
                            st.success(f"Decoded Payee: {parsed['receiver_vpa']} (₹{parsed['amount']})")
                            target_payee = parsed["receiver_vpa"]
                            target_amount = parsed["amount"] if parsed["amount"] > 0 else st.number_input("Enter Amount (₹):", min_value=1.0, value=100.0, key="chk_qr_amt_fix")
                        else:
                            st.error(msg)
                    else:
                        st.error(err)

            else:
                raw_uri = st.text_input("Paste UPI Deep Link (upi://pay?...):", "", key="chk_raw_uri")
                if raw_uri:
                    valid, parsed, msg = engine.parse_upi_uri(raw_uri)
                    if valid:
                        st.success(f"Validated: {parsed['receiver_vpa']} | INR {parsed['amount']}")
                        target_payee = parsed["receiver_vpa"]
                        target_amount = parsed["amount"] if parsed["amount"] > 0 else st.number_input("Enter Amount (₹):", min_value=1.0, value=100.0, key="chk_uri_amt_fix")
                    else:
                        st.error(msg)

            # City Selector
            selected_city = st.selectbox("Current Transaction City:", list(engine.INDIAN_CITIES.keys()), index=0, key="chk_city_sel")

            # Scam Flags
            col_scam1, col_scam2 = st.columns(2)
            with col_scam1:
                chk_call = st.checkbox("📞 Active Unknown Call", key="chk_call_flag")
            with col_scam2:
                chk_link = st.checkbox("🔗 External Link Source", key="chk_link_flag")

            can_proceed = True
            if chk_call or chk_link:
                st.error("⚠️ **CRITICAL PRE-PAYMENT WARNING:** Never send money over voice calls or unsolicited messages.")
                can_proceed = st.checkbox("I verify this recipient and authorize under personal discretion.", key="chk_scam_override")

            pay_submitted = st.button("🚀 Authorize & Pay", type="primary", disabled=not can_proceed, key="btn_submit_pay")
            st.markdown("</div>", unsafe_allow_html=True)

            # QR Generator Tool
            with st.expander("🛠️ Merchant QR Code Generator Tool", expanded=False):
                g_vpa = st.text_input("Generator VPA:", "chai_point@upi", key="gen_vpa")
                g_name = st.text_input("Payee Name:", "Chai Point Counter", key="gen_name")
                g_amt = st.number_input("Preset Amount (₹):", min_value=0.0, value=120.0, key="gen_amt")
                if st.button("Generate QR Code", key="btn_gen_qr"):
                    qr_img, qr_link = engine.generate_upi_qr(g_vpa, g_name, g_amt)
                    buf = io.BytesIO()
                    qr_img.save(buf, format="PNG")
                    st.image(buf.getvalue(), caption=f"QR for {g_vpa}", width=200)
                    st.code(qr_link, language="text")

        # Telemetry & Switch Execution Result
        with col_telemetry:
            if pay_submitted and target_payee:
                inv = engine.investigate(
                    amount=target_amount,
                    sender_vpa=active_sender_vpa,
                    receiver_vpa=target_payee,
                    city=selected_city,
                    device_id=device_id,
                    active_call=chk_call,
                    external_link=chk_link,
                    model=rf_model,
                    scaler=rf_scaler
                )
                
                utr, status = engine.record_transaction(
                    sender_vpa=active_sender_vpa,
                    receiver_vpa=target_payee,
                    amount=target_amount,
                    city=selected_city,
                    device_id=device_id,
                    inv_result=inv
                )

                st.session_state["active_tx"] = {
                    "utr": utr,
                    "status": status,
                    "inv": inv,
                    "amount": target_amount,
                    "receiver": target_payee,
                    "sender": active_sender_vpa
                }

                if status == "PENDING_OTP":
                    engine.create_otp_challenge(utr, device_id, active_sender_vpa)

            # Render Active Transaction Telemetry Panel
            if "active_tx" in st.session_state:
                tx_info = st.session_state["active_tx"]
                inv = tx_info["inv"]
                st.markdown('<div class="bento-card">', unsafe_allow_html=True)
                st.markdown(f'<div class="bento-card-title">⚙️ Switch Interception: UTR {tx_info["utr"]}</div>', unsafe_allow_html=True)
                
                # Donut Risk Gauge
                st.markdown(render_donut_gauge(inv["score"], inv["tier"]), unsafe_allow_html=True)

                # Metric Tiles
                m = inv["metrics"]
                st.markdown(f"""
                <div class="metric-grid">
                    <div class="metric-tile">
                        <div class="tile-lbl">Drain Ratio</div>
                        <div class="tile-val">{m['drain_ratio']*100:.1f}%</div>
                    </div>
                    <div class="metric-tile">
                        <div class="tile-lbl">Spend Surge</div>
                        <div class="tile-val">{m['amount_to_avg']:.1f}x</div>
                    </div>
                    <div class="metric-tile">
                        <div class="tile-lbl">Speed</div>
                        <div class="tile-val">{m['speed_kmh']:,.0f} <span style="font-size:0.9rem;">km/h</span></div>
                    </div>
                    <div class="metric-tile">
                        <div class="tile-lbl">Latency</div>
                        <div class="tile-val">{inv['latency_ms']:.1f} <span style="font-size:0.9rem;">ms</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # Decision Verdict
                if inv["tier"] == "CLEARED":
                    st.success(f"✅ **Payment Settled!** UTR: `{tx_info['utr']}`")
                elif inv["tier"] == "PENDING_OTP":
                    st.warning(f"⏸️ **Pre-Debit Security Freeze Engaged:** Unusual behavioral signals detected.")
                    st.markdown(f"*{html.escape(inv['reason'])}*")
                    
                    # OTP Input Box
                    c_otp1, c_otp2 = st.columns([1.5, 1])
                    with c_otp1:
                        entered_otp = st.text_input("Enter 4-Digit Security OTP:", max_chars=4, key="chk_otp_val")
                        if st.button("Unlock & Release Debit", type="primary", key="btn_verify_otp"):
                            success, msg = engine.verify_otp_challenge(tx_info["utr"], entered_otp)
                            if success:
                                st.success(msg)
                                st.session_state["active_tx"]["status"] = "SUCCESS"
                                st.session_state["active_tx"]["inv"]["tier"] = "CLEARED"
                                st.rerun()
                            else:
                                st.error(msg)
                    with c_otp2:
                        st.write("")
                        st.write("")
                        if st.button("Resend OTP", key="btn_resend_otp"):
                            r_ok, r_msg = engine.resend_otp_challenge(tx_info["utr"], device_id, tx_info["sender"])
                            if r_ok:
                                st.info(r_msg)
                            else:
                                st.error(r_msg)
                else:
                    st.error(f"🚫 **Payment Terminated by Switch:** {inv['reason']}")

                # Explainable AI Audit Log
                with st.expander("🔍 Explainable AI (XAI) Audit Checklist", expanded=False):
                    for name, detail, state in inv["log"]:
                        b_cls = "badge-pass" if state == "OK" else "badge-block"
                        sym = "✓" if state == "OK" else "⚠️"
                        st.markdown(f"""
                        <div class="step-item">
                            <div>
                                <div class="step-title">{html.escape(name)}</div>
                                <div class="step-sub">{html.escape(detail)}</div>
                            </div>
                            <span class="{b_cls}">{sym} {html.escape(state)}</span>
                        </div>
                        """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

            # Simulated Phone SMS Inbox View
            with st.expander("📱 Simulated Phone SMS Inbox", expanded=False):
                conn = engine.get_db_connection()
                sms_list = conn.execute("SELECT * FROM sms_inbox WHERE device_id = ? ORDER BY id DESC LIMIT 3", (device_id,)).fetchall()
                conn.close()
                if sms_list:
                    for s in sms_list:
                        st.markdown(f"**[{s['timestamp']}]** `{html.escape(s['message'])}`")
                else:
                    st.caption("No SMS messages dispatched to this device.")

    # -------------------------------------------------------------------------
    # TAB 2: Manual Analysis & Stress-Testing
    # -------------------------------------------------------------------------
    with tab_stress:
        st.markdown('<div class="bento-card">', unsafe_allow_html=True)
        st.markdown('<div class="bento-card-title">🧪 What-If Stress-Testing Simulator</div>', unsafe_allow_html=True)
        st.caption("Perform parameter permutations without writing records to the persistent ledger.")

        p_col1, p_col2 = st.columns(2)
        with p_col1:
            st_amt = st.number_input("Amount (₹):", min_value=1.0, value=25000.0, step=500.0, key="st_amt")
            st_bal = st.number_input("Account Balance (₹):", min_value=0.0, value=30000.0, step=1000.0, key="st_bal")
            st_avg = st.number_input("Habitual Daily Average (₹):", min_value=1.0, value=1500.0, step=100.0, key="st_avg")
            st_vpa = st.text_input("Beneficiary VPA:", "claim-refund@fakebank", key="st_vpa")
        with p_col2:
            st_dist = st.number_input("Displacement (km):", min_value=0.0, value=850.0, step=50.0, key="st_dist")
            st_gap = st.number_input("Time Elapsed (seconds):", min_value=1.0, value=600.0, step=60.0, key="st_gap")
            st_tx_cnt = st.number_input("10-Min Payment Burst Count:", min_value=0, value=4, key="st_tx_cnt")
            st_new_dev = st.checkbox("Simulate New Device Token", value=True, key="st_new_dev")

        if st.button("Run Simulation Inspection", type="primary", key="btn_run_stress"):
            drain = st_amt / (st_bal + 1e-5)
            surge = st_amt / (st_avg + 1e-5)
            speed = st_dist / max(st_gap / 3600.0, 0.0001)

            st_flags = []
            st_log = []

            if re.search(r"(refund|cashback|lottery|winner|kyc|support)", st_vpa.lower()):
                st_flags.append("SUSPICIOUS_VPA")
                st_log.append(("Scam Pattern", "VPA string contains malicious keywords.", "ALERT"))
            if speed > 300.0 and st_dist > 20.0:
                st_flags.append("IMPOSSIBLE_SPEED")
                st_log.append(("Kinematic Velocity", f"Violated physical transit speed ({speed:,.0f} km/h).", "ALERT"))
            if drain > 0.65:
                st_flags.append("HIGH_DRAIN")
                st_log.append(("Account Drain", f"Elevated balance drain ({drain*100:.1f}%).", "ALERT"))
            if surge > 3.5:
                st_flags.append("SPENDING_SPIKE")
                st_log.append(("Spending Spike", f"Surge of {surge:.1f}x historical baseline.", "ALERT"))

            score = 0.99 if any(f in ["SUSPICIOUS_VPA", "IMPOSSIBLE_SPEED"] for f in st_flags) else (0.52 if st_flags else 0.12)
            sim_tier = "BLOCKED" if score >= 0.90 else ("PENDING_OTP" if score >= 0.35 else "CLEARED")

            st.markdown("---")
            st.markdown(render_donut_gauge(score, sim_tier), unsafe_allow_html=True)
            st.markdown(f"**Simulated Flags:** `{', '.join(st_flags) if st_flags else 'None'}`")

        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # TAB 3: Ledger & Remediation
    # -------------------------------------------------------------------------
    with tab_ledger:
        st.markdown('<div class="bento-card">', unsafe_allow_html=True)
        st.markdown('<div class="bento-card-title">📑 Transaction Ledger Audit</div>', unsafe_allow_html=True)

        conn = engine.get_db_connection()
        df_ledger = pd.read_sql_query("SELECT id, utr, sender_vpa, receiver_vpa, amount, status, risk_score, latency_ms, timestamp FROM transactions ORDER BY id DESC LIMIT 50", conn)
        conn.close()

        if not df_ledger.empty:
            st.dataframe(df_ledger)
            csv_buf = df_ledger.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Export Ledger Audit (CSV)", data=csv_buf, file_name="upi_shield_ledger.csv", mime="text/csv", key="btn_export_csv")
        else:
            st.caption("Ledger is currently empty.")

        st.markdown("---")
        st.markdown('<div class="bento-card-title">🚨 Active Beneficiary Liens & Regulatory Escalation</div>', unsafe_allow_html=True)
        
        col_lien1, col_lien2 = st.columns(2)
        with col_lien1:
            st.markdown("##### Place Legal Lien on VPA")
            l_vpa = st.text_input("Payee VPA:", "claim-refund@fakebank", key="lien_in_vpa")
            l_reason = st.text_input("Lien Cause:", "Digital Arrest Extortion Pattern", key="lien_in_reason")
            if st.button("Enforce Regulatory Lien", type="primary", key="btn_place_lien"):
                engine.place_beneficiary_lien(l_vpa, l_reason)
                st.success(f"Lien successfully enforced against '{l_vpa}'. All future transfers will be blocked.")
                st.rerun()

        with col_lien2:
            st.markdown("##### Active Liens")
            conn = engine.get_db_connection()
            liens = conn.execute("SELECT * FROM liens ORDER BY id DESC").fetchall()
            conn.close()
            if liens:
                for ln in liens:
                    st.markdown(f"**{ln['receiver_vpa']}** — *{ln['reason']}*")
                    if st.button(f"Release Lien: {ln['receiver_vpa']}", key=f"btn_rel_{ln['id']}"):
                        engine.remove_beneficiary_lien(ln['receiver_vpa'])
                        st.info("Lien removed.")
                        st.rerun()
            else:
                st.caption("No active liens currently recorded.")

        st.markdown("---")
        st.markdown("##### 📄 Generate Statutory Bank Dispute Dossier")
        dossier_utr = st.text_input("Enter Transaction UTR Reference:", key="txt_dossier_utr")
        if st.button("Generate Official Legal Dossier", key="btn_gen_dossier"):
            dossier_txt = engine.generate_dispute_dossier(dossier_utr)
            st.text_area("Legal Dossier Output", dossier_txt, height=220)
            st.download_button("📥 Download Dossier (.txt)", data=dossier_txt, file_name=f"Dispute_{dossier_utr}.txt", key="btn_dl_dossier")

        st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# VIEW 4: SETTINGS & CONFIGURATION
# =============================================================================
elif st.session_state["active_nav"] == "Settings":
    st.markdown("## ⚙️ System Settings & Policies")
    st.caption("Adjust policy thresholds and inspect registered devices.")

    st.markdown('<div class="bento-card">', unsafe_allow_html=True)
    st.markdown('<div class="bento-card-title">Threshold Policies</div>', unsafe_allow_html=True)

    curr_cfg = engine.get_settings()
    rev_val = st.slider("Pre-Debit OTP Review Threshold:", 0.10, 0.80, float(curr_cfg["review_threshold"]), 0.05, key="set_rev")
    blk_val = st.slider("Definitive Block Threshold:", 0.50, 0.99, float(curr_cfg["block_threshold"]), 0.05, key="set_blk")
    drain_limit = st.slider("Account Drain Limit Ratio:", 0.30, 0.95, float(curr_cfg["drain_ratio_limit"]), 0.05, key="set_drain")
    spike_limit = st.slider("Spending Surge Multiplier:", 1.5, 10.0, float(curr_cfg["spending_spike_multiplier"]), 0.5, key="set_spike")
    hold_soft = st.checkbox("Force Pre-Debit OTP Hold on Single Soft Flag (e.g. OFF_HOURS)", value=bool(curr_cfg["hold_on_single_soft_flag"]), key="set_soft")

    if rev_val >= blk_val:
        st.error("Validation Error: Review threshold must be strictly lower than Block threshold.")
    else:
        if st.button("Save Policy Settings", type="primary", key="btn_save_settings"):
            conn = engine.get_db_connection()
            conn.execute("UPDATE settings SET value = ? WHERE key = 'review_threshold'", (rev_val,))
            conn.execute("UPDATE settings SET value = ? WHERE key = 'block_threshold'", (blk_val,))
            conn.execute("UPDATE settings SET value = ? WHERE key = 'drain_ratio_limit'", (drain_limit,))
            conn.execute("UPDATE settings SET value = ? WHERE key = 'spending_spike_multiplier'", (spike_limit,))
            conn.execute("UPDATE settings SET value = ? WHERE key = 'hold_on_single_soft_flag'", (1.0 if hold_soft else 0.0,))
            conn.commit()
            conn.close()
            st.success("Policies updated successfully.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="bento-card">', unsafe_allow_html=True)
    st.markdown('<div class="bento-card-title">Danger Zone: Database Reset</div>', unsafe_allow_html=True)
    st.caption("Re-seeds all accounts to default balances, clears transaction history, and removes all enrolled devices.")
    confirm_reset = st.checkbox("I confirm that I want to wipe and re-initialize the database.", key="chk_wipe_confirm")
    if st.button("Reset Entire Database", type="secondary", disabled=not confirm_reset, key="btn_wipe_db"):
        engine.init_db(force_reset=True)
        st.success("Database restored to pristine factory baseline.")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
