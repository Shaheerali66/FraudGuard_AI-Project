import streamlit as st
import requests
import pandas as pd
import time
import os
import random
from datetime import datetime

st.set_page_config(
    page_title="FraudGuard Enterprise",
    page_icon=":material/account_balance:",
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
load_css()

API_BASE = "http://127.0.0.1:8000/api/v1"

# Demo API key — seeded into the database by backend/database.py on first run.
INTERNAL_API_KEY = "fg-demo-key-a1b2c3d4e5f6"
INTERNAL_HEADERS = {"X-API-Key": INTERNAL_API_KEY}

# ─── Session state init ────────────────────────────────────────────────────────
def _init_state():
    # Session Persistence: load from query params on reload
    is_logged_in = st.query_params.get("logged_in") == "true"
    defaults = {
        "route": "portal" if is_logged_in else "home",
        "page": st.query_params.get("page", "Dashboard"),
        "logged_in": is_logged_in,
        "username": st.query_params.get("username", ""),
        "login_error": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# Global logout helper
def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.route = "home"
    st.session_state.page = "Dashboard"
    st.query_params.clear()
    st.rerun()

# ─── Page Header Helper (portal pages) ────────────────────────────────────────
def page_header(icon_name, title, subtitle):
    st.markdown(f"""
    <div style="margin-bottom: 2rem;">
        <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.4rem;">
            <span class="material-symbols-outlined" style="font-size:2rem; color:var(--accent-blue); vertical-align:middle;">{icon_name}</span>
            <h1 style="margin:0; font-size:1.85rem; font-weight:800;
                       background: linear-gradient(135deg, #f1f5f9, #94a3b8);
                       -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                       vertical-align:middle; display:inline-block;">
                {title}
            </h1>
        </div>
        <p style="margin:0; color:#64748b; font-size:0.95rem; padding-left:2.8rem;">{subtitle}</p>
        <hr style="margin-top:1rem; border:none; border-top:1px solid rgba(148,163,184,0.12);">
    </div>
    """, unsafe_allow_html=True)

# ─── Verdict Badge Helper ─────────────────────────────────────────────────────
def verdict_badge(status, fraud_prob, tx_id):
    if status == "Approved":
        color, bg, icon, msg = "#34d399", "rgba(52,211,153,0.12)", "check_circle", "Transaction Approved"
        border = "#34d399"
    elif status in ["Pending Review", "Flagged"]:
        color, bg, icon, msg = "#fbbf24", "rgba(251,191,36,0.12)", "pending", "Under Review"
        border = "#fbbf24"
    else:
        color, bg, icon, msg = "#f87171", "rgba(248,113,113,0.12)", "cancel", "Transaction Blocked"
        border = "#f87171"

    bar_pct = int(fraud_prob * 100)
    bar_color = "#34d399" if fraud_prob < 0.30 else ("#fbbf24" if fraud_prob < 0.75 else "#f87171")

    st.markdown(f"""
    <div style="background:{bg}; border:1px solid {border}; border-left:4px solid {border};
                border-radius:12px; padding:1.5rem; margin-top:1rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <div style="display:flex; align-items:center; gap:0.5rem;">
                <span class="material-symbols-outlined" style="font-size:1.8rem; color:{color};">{icon}</span>
                <span style="font-size:1.3rem; font-weight:800; color:{color};">{msg}</span>
            </div>
            <span style="background:rgba(255,255,255,0.08); color:#94a3b8;
                         font-size:0.75rem; padding:4px 10px; border-radius:20px;
                         font-family:monospace;">{tx_id}</span>
        </div>
        <div style="margin-bottom:0.5rem;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span style="color:#94a3b8; font-size:0.8rem; font-weight:600;">FRAUD RISK SCORE</span>
                <span style="color:{bar_color}; font-weight:800; font-size:0.95rem;">{fraud_prob:.1%}</span>
            </div>
            <div style="background:rgba(255,255,255,0.08); border-radius:999px; height:8px; overflow:hidden;">
                <div style="width:{bar_pct}%; height:100%; background:{bar_color};
                             border-radius:999px; transition:width 0.8s ease;"></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─── Shared Checkout Logic ────────────────────────────────────────────────────
# This is used both on the public home page and the portal Merchant Checkout page.
def _checkout_form(form_key: str):
    """Renders the checkout form and result inline. form_key must be unique per page."""
    result_key = f"{form_key}_result"

    with st.form(form_key, clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            merchant_category = st.selectbox(
                "Merchant Category",
                ["shopping_net", "grocery_pos", "entertainment", "gas_transport", "misc_net"],
            )
        with col2:
            amt = st.number_input("Transaction Amount ($)", min_value=0.01, value=49.99, step=1.0)
        with col3:
            gender = st.selectbox("Cardholder Gender", ["M", "F"])

        submit = st.form_submit_button(
            "Complete Payment",
            icon=":material/lock:",
            type="primary",
            use_container_width=True
        )

    if submit:
        with st.spinner("Analysing transaction for fraud signals…"):
            simulated_city_pop = random.randint(50000, 1000000)
            simulated_distance = round(random.uniform(1.0, 20.0), 2)
            current_hour = datetime.now().hour
            is_night = 1 if (current_hour >= 22 or current_hour < 5) else 0
            is_weekend = 1 if datetime.now().weekday() in [5, 6] else 0

            payload = {
                "merchant": "Online Store",
                "merchant_category": merchant_category,
                "amt": amt,
                "gender": gender,
                "city": "Sample City",
                "state": "ST",
                "city_pop": simulated_city_pop,
                "distance_from_home": simulated_distance,
                "is_night_transaction": is_night,
                "transaction_hour": current_hour,
                "weekend_transaction": is_weekend
            }
            try:
                response = requests.post(
                    f"{API_BASE}/transactions",
                    json=payload,
                    headers=INTERNAL_HEADERS,
                    timeout=10
                )
                response.raise_for_status()
                st.session_state[result_key] = (response.json(), amt, merchant_category)
                st.rerun()  # Real-time refresh for Dashboard stats & Recent Transactions
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to backend. Make sure the API server is running on port 8000.", icon=":material/cancel:")
                st.session_state.pop(result_key, None)
            except Exception as e:
                st.error(f"Payment gateway error: {e}", icon=":material/cancel:")
                st.session_state.pop(result_key, None)

    if result_key in st.session_state:
        data, amt_val, cat_val = st.session_state[result_key]
        fraud_prob = data.get("fraud_probability", 0)
        tx_id      = data.get("transaction_id", "—")
        status     = data.get("status", "—")
        verdict    = data.get("verdict", "—")
        risk_tier  = data.get("risk_tier", "—")

        verdict_badge(status, fraud_prob, tx_id)

        st.markdown("<br>", unsafe_allow_html=True)
        summary_df = pd.DataFrame({
            "Field": ["Transaction ID", "Amount", "Category", "Fraud Probability", "Risk Tier", "Status", "Verdict"],
            "Value": [tx_id, f"${amt_val:.2f}", cat_val, f"{fraud_prob:.1%}", risk_tier, status, verdict]
        })
        st.table(summary_df)

        top_factors = data.get("top_factors", [])
        if top_factors:
            st.markdown("<br><h4><span class='material-symbols-outlined' style='color:var(--accent-blue); font-size:24px; vertical-align:middle; margin-right:6px;'>search</span><span style='vertical-align:middle;'>Why this decision?</span></h4>", unsafe_allow_html=True)
            st.markdown("<p style='color:#94a3b8; font-size:0.88rem; margin-bottom:1rem;'>Key risk drivers identified by the model:</p>", unsafe_allow_html=True)
            total_impact = sum(abs(f.get("impact", 0.0)) for f in top_factors)
            for factor in top_factors:
                feat_name = factor.get("feature", "Unknown")
                impact = factor.get("impact", 0.0)
                direction = factor.get("direction", "increases_risk")
                icon = "trending_up"
                color = "#f87171"
                text_desc = "Increased Risk"
                if direction != "increases_risk":
                    icon = "trending_down"
                    color = "#34d399"
                    text_desc = "Decreased Risk"
                percentage = (impact / total_impact * 100) if total_impact > 0 else 0
                st.markdown(f"""
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.6rem; padding: 0.4rem 0.8rem; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
                        <span class="material-symbols-outlined" style="font-size: 1.2rem; color: {color};">{icon}</span>
                        <span style="font-weight: 600; color: #cbd5e1; font-size: 0.88rem;">{feat_name}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.75rem; width: 140px; justify-content: flex-end;">
                        <div style="background: rgba(255,255,255,0.08); border-radius: 999px; height: 6px; flex: 1; overflow: hidden;">
                            <div style="width: {percentage:.0f}%; height: 100%; background: {color}; border-radius: 999px;"></div>
                        </div>
                        <span style="color: #94a3b8; font-size: 0.78rem; font-family: monospace; font-weight: 700; width: 45px; text-align: right;">{percentage:.0f}%</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# ─── Public Home Page ─────────────────────────────────────────────────────────
def render_home():
    # Hide sidebar on the public home page
    st.markdown("""
    <style>
    [data-testid="stSidebar"], [data-testid="collapsedSidebarMenu"] { display: none !important; }
    .block-container { padding-top: 0 !important; padding-left: 0 !important;
                        padding-right: 0 !important; max-width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

    # ── Top Navigation Bar ─────────────────────────────────────────────────────
    # Strategy: use an invisible anchor div + CSS :has() + sibling combinator to
    # style the immediately-following stHorizontalBlock as a proper flex navbar.
    # This is the only reliable way to keep a real st.button in a custom header
    # row — if we use st.markdown HTML for the whole row, the button ends up in
    # a separate Streamlit block below it.
    st.markdown("""
    <style>
    /* The anchor div itself is invisible */
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) {
        display: none !important;
        margin: 0 !important; padding: 0 !important; height: 0 !important;
    }

    /* The immediate next sibling: the stHorizontalBlock wrapper div */
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) + div {
        background: rgba(15,23,42,0.98) !important;
        border-bottom: 1px solid rgba(148,163,184,0.18) !important;
        box-shadow: 0 2px 20px rgba(0,0,0,0.4) !important;
        padding: 0 2.5rem !important;
        margin: 0 !important;
        position: relative;
        z-index: 50;
    }

    /* The inner stHorizontalBlock: full height, items centered */
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) + div [data-testid="stHorizontalBlock"] {
        min-height: 72px !important;
        align-items: center !important;
        gap: 0 !important;
        flex-wrap: nowrap !important;
    }

    /* Every column in the navbar: stretch to full height, center content */
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) + div [data-testid="column"] {
        display: flex !important;
        align-items: center !important;
        min-height: 72px !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }

    /* Last column (button side): align right */
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) + div [data-testid="column"]:last-child {
        justify-content: flex-end !important;
    }

    /* Remove margin/padding from button wrapper and button itself inside navbar */
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) + div .stButton,
    [data-testid="stVerticalBlock"] > div:has(.fg-navbar-anchor) + div .stButton > button {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
    </style>
    <div class="fg-navbar-anchor"></div>
    """, unsafe_allow_html=True)

    # Logo (left) + Login button (right) — both in the SAME columns call
    # so Streamlit renders them as siblings in a single horizontal block.
    logo_col, btn_col = st.columns([5, 1])

    with logo_col:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:0.65rem; height:72px;">
            <span class="material-symbols-outlined" style="font-size:1.9rem; color:#38bdf8; line-height:1; flex-shrink:0;">account_balance</span>
            <div style="line-height:1.15; flex-shrink:0;">
                <div style="font-size:1.15rem; font-weight:800; color:#f1f5f9; letter-spacing:-0.01em;">FraudGuard</div>
            </div>
            <div style="margin-left:0.6rem; background:rgba(52,211,153,0.1); border:1px solid rgba(52,211,153,0.25);
                        border-radius:20px; padding:2px 10px; display:inline-flex; align-items:center; flex-shrink:0;">
                <span style="color:#34d399; font-size:0.67rem; font-weight:700;">● LIVE</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with btn_col:
        if st.button("Officer Login", icon=":material/lock_person:", type="secondary", key="header_login_btn"):
            st.session_state.route = "login"
            st.rerun()


    # ── Hero Section ───────────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero-section">
        <div class="hero-eyebrow">
            <span class="material-symbols-outlined" style="font-size:0.9rem;">verified_user</span>
            Real-Time AI Fraud Protection
        </div>
        <div class="hero-headline">
            Stop Fraud <span class="hero-gradient-text">Before It Happens</span>
        </div>
        <div class="hero-subtext">
            FraudGuard analyses every transaction in milliseconds using an XGBoost model trained on 1.3M+ transactions — delivering an instant verdict at checkout.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Embedded Checkout Card ─────────────────────────────────────────────────
    # Use columns to center the card
    _, center_col, _ = st.columns([1, 3, 1])
    with center_col:
        st.markdown("""
        <div class="checkout-hero-card">
            <div class="checkout-hero-label">
                <span class="material-symbols-outlined" style="font-size:0.9rem;">shopping_cart</span>
                Secure Merchant Checkout — Try It Live
            </div>
        </div>
        """, unsafe_allow_html=True)
        _checkout_form("checkout_home")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── How It Works Section ───────────────────────────────────────────────────
    st.markdown("""
    <div style="padding: 1rem 0 0.5rem; text-align: center;">
        <div style="font-size:1.5rem; font-weight:800; color:#f1f5f9; margin-bottom:0.3rem;">How It Works</div>
        <div style="color:#64748b; font-size:0.92rem; margin-bottom:2rem;">
            Four steps from transaction to decision — in under 200ms
        </div>
    </div>
    """, unsafe_allow_html=True)

    steps = [
        ("send", "#38bdf8", "Submit Transaction", "Merchant or customer initiates a payment request with transaction details."),
        ("psychology", "#a78bfa", "ML Model Scores", "XGBoost model analyses 15+ features — amount, time, location, behaviour patterns."),
        ("fact_check", "#34d399", "Instant Verdict", "Approved, Under Review, or Blocked in milliseconds. No manual step needed."),
        ("manage_accounts", "#fbbf24", "Officer Review", "Flagged transactions enter the bank officer queue for manual investigation."),
    ]
    step_cols = st.columns(4)
    for i, (icon, color, title, desc) in enumerate(steps):
        with step_cols[i]:
            st.markdown(f"""
            <div class="step-card">
                <div class="step-number">{i+1}</div>
                <span class="material-symbols-outlined" style="font-size:2rem; color:{color}; margin-bottom:0.75rem; display:block;">{icon}</span>
                <div style="font-size:0.92rem; font-weight:700; color:#f1f5f9; margin-bottom:0.4rem;">{title}</div>
                <div style="font-size:0.8rem; color:#64748b; line-height:1.6;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Trust / Stats Strip ────────────────────────────────────────────────────
    st.markdown("""
    <div class="stats-section">
        <div style="text-align:center; font-size:0.7rem; font-weight:700; text-transform:uppercase;
                    letter-spacing:0.12em; color:#475569; margin-bottom:2rem;">
            Trusted by merchants and banks
        </div>
    </div>
    """, unsafe_allow_html=True)

    stats_cols = st.columns(3)
    stats_data = [
        ("98.7%", "Model ROC-AUC", "Across 5-fold cross-validation"),
        ("<200ms", "Avg Response Time", "Per transaction prediction"),
        ("1.3M+", "Transactions Trained", "Balanced fraud/non-fraud dataset"),
    ]
    for col, (num, label, sub) in zip(stats_cols, stats_data):
        with col:
            st.markdown(f"""
            <div style="text-align:center; padding:1rem;">
                <div class="stat-number">{num}</div>
                <div class="stat-label">{label}</div>
                <div class="stat-sublabel">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<hr style='border:none; border-top:1px solid rgba(148,163,184,0.1); margin:1.5rem 0;'>", unsafe_allow_html=True)

    # ── For Banks & Merchants CTA ──────────────────────────────────────────────
    cta_left, cta_right = st.columns([3, 2])
    with cta_left:
        st.markdown("""
        <div style="padding: 2rem 1rem;">
            <div style="font-size:1.4rem; font-weight:800; color:#f1f5f9; margin-bottom:0.6rem;">
                Built for Bank Officers & Risk Teams
            </div>
            <div style="color:#94a3b8; font-size:0.92rem; line-height:1.7; margin-bottom:1.5rem;">
                The Officer Portal gives your team a real-time command centre — review flagged transactions, manage pending queues, analyse trends via dashboard, and integrate with your own systems via REST API.
            </div>
            <div>
                <span class="feature-pill" style="display:inline-flex; align-items:center; gap:5px; background:#1e293b; border:1px solid rgba(148,163,184,0.12); border-radius:20px; padding:5px 12px; font-size:0.78rem; color:#94a3b8; margin:3px;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem; color:#38bdf8;">dashboard</span> Live Dashboard
                </span>
                <span class="feature-pill" style="display:inline-flex; align-items:center; gap:5px; background:#1e293b; border:1px solid rgba(148,163,184,0.12); border-radius:20px; padding:5px 12px; font-size:0.78rem; color:#94a3b8; margin:3px;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem; color:#a78bfa;">fact_check</span> Manual Review Queue
                </span>
                <span class="feature-pill" style="display:inline-flex; align-items:center; gap:5px; background:#1e293b; border:1px solid rgba(148,163,184,0.12); border-radius:20px; padding:5px 12px; font-size:0.78rem; color:#94a3b8; margin:3px;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem; color:#34d399;">api</span> REST API
                </span>
                <span class="feature-pill" style="display:inline-flex; align-items:center; gap:5px; background:#1e293b; border:1px solid rgba(148,163,184,0.12); border-radius:20px; padding:5px 12px; font-size:0.78rem; color:#94a3b8; margin:3px;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem; color:#fbbf24;">upload_file</span> CSV Batch Upload
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with cta_right:
        st.markdown("""
        <div style="display:flex; align-items:center; justify-content:center; height:100%; padding:2rem 1rem;">
            <div style="background:#1e293b; border:1px solid rgba(148,163,184,0.12); border-radius:16px;
                        padding:2rem; text-align:center; width:100%;">
                <span class="material-symbols-outlined" style="font-size:2.5rem; color:#38bdf8; margin-bottom:0.75rem; display:block;">security</span>
                <div style="font-size:0.95rem; font-weight:700; color:#f1f5f9; margin-bottom:0.4rem;">
                    Officer / Admin Login
                </div>
                <div style="font-size:0.8rem; color:#64748b; margin-bottom:1.25rem; line-height:1.5;">
                    Access the full bank officer portal — dashboard, review queue, history, and API docs.
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Access Officer Portal", icon=":material/lock_person:", type="primary", key="cta_login_btn", use_container_width=True):
            st.session_state.route = "login"
            st.rerun()

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <hr style="border:none; border-top:1px solid rgba(148,163,184,0.08); margin-top:2rem;">
    <div style="text-align:center; padding:1.5rem 0; color:#334155; font-size:0.78rem;">
        <span style="color:#475569;">
            <span class="material-symbols-outlined" style="font-size:0.9rem; color:#38bdf8; vertical-align:middle;">account_balance</span>
            FraudGuard v2.0
        </span>
        &nbsp;&nbsp;·&nbsp;&nbsp;Powered by FastAPI + XGBoost + SHAP
        &nbsp;&nbsp;·&nbsp;&nbsp;<span style="color:#1e3a5f;">All transactions are processed server-side</span>
    </div>
    """, unsafe_allow_html=True)


# ─── Login Page ───────────────────────────────────────────────────────────────
def render_login():
    # Hide sidebar on login page
    st.markdown("""
    <style>
    [data-testid="stSidebar"], [data-testid="collapsedSidebarMenu"] { display: none !important; }
    .block-container { padding-top: 2rem !important; }
    </style>
    """, unsafe_allow_html=True)

    # Back to home link
    if st.button("← Back to Home", icon=":material/arrow_back:", key="back_home"):
        st.session_state.route = "home"
        st.session_state.login_error = False
        st.rerun()

    # Centered login card via columns
    _, card_col, _ = st.columns([1, 2, 1])
    with card_col:
        st.markdown("""
        <div class="login-card">
            <div style="text-align:center; margin-bottom:1.75rem;">
                <span class="material-symbols-outlined" style="font-size:2.8rem; color:#38bdf8; display:block; margin-bottom:0.6rem;">security</span>
                <div style="font-size:1.25rem; font-weight:800; color:#f1f5f9; margin-bottom:0.25rem;">Officer Portal</div>
                <div style="font-size:0.82rem; color:#64748b; margin-bottom:1rem;">Bank Officer / Admin Login</div>
                <div style="display:inline-flex; align-items:center; gap:5px; background:rgba(56,189,248,0.08);
                            border:1px solid rgba(56,189,248,0.2); border-radius:12px; padding:3px 10px;
                            font-size:0.7rem; font-weight:600; color:#38bdf8; text-transform:uppercase; letter-spacing:0.08em;">
                    <span class="material-symbols-outlined" style="font-size:0.85rem;">verified_user</span>
                    Restricted Access
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.login_error:
            st.markdown("""
            <div style="background:rgba(248,113,113,0.1); border:1px solid rgba(248,113,113,0.25);
                        border-left:3px solid #f87171; border-radius:8px; padding:0.75rem 1rem;
                        color:#f87171; font-size:0.85rem; margin-bottom:1rem; display:flex; align-items:center; gap:6px;">
                <span class="material-symbols-outlined" style="font-size:1rem;">cancel</span>
                Invalid username or password. Please try again.
            </div>
            """, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            login_btn = st.form_submit_button(
                "Sign In to Officer Portal",
                icon=":material/login:",
                type="primary",
                use_container_width=True
            )

        if login_btn:
            if username == "admin" and password == "admin123":
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.route = "portal"
                st.session_state.page = "Dashboard"
                st.session_state.login_error = False
                
                # Write to query params to persist session across reload
                st.query_params["logged_in"] = "true"
                st.query_params["username"] = "admin"
                st.query_params["page"] = "Dashboard"
                st.rerun()
            else:
                st.session_state.login_error = True
                st.rerun()

        st.markdown("""
        <div style="text-align:center; margin-top:1.5rem; color:#334155; font-size:0.75rem;">
            For demo: <code style="background:#1e293b; padding:2px 6px; border-radius:4px; color:#94a3b8;">admin</code>
            /
            <code style="background:#1e293b; padding:2px 6px; border-radius:4px; color:#94a3b8;">admin123</code>
        </div>
        """, unsafe_allow_html=True)


# ─── Portal: Checkout Page ────────────────────────────────────────────────────
def render_checkout():
    page_header("shopping_cart", "E-Commerce Checkout", "Submit a transaction and get instant fraud detection results.")
    _checkout_form("checkout_portal")


# ─── Portal: Dashboard ────────────────────────────────────────────────────────
def render_dashboard():
    page_header("dashboard", "Risk Command Center", "Real-time overview of fraud detection metrics.")

    try:
        response = requests.get(f"{API_BASE}/dashboard/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()

            total   = stats.get("total_transactions", 0)
            approved = stats.get("approved", 0)
            pending  = stats.get("pending", 0)
            flagged  = stats.get("flagged", 0)
            blocked  = stats.get("blocked", 0)
            avg_score = stats.get("avg_fraud_score", 0)
            approval_rate = (approved / total * 100) if total > 0 else 0

            # ── Quick Fraud Check widget (always open/expanded) ────────────────
            with st.container():
                st.markdown("""
                <div class="quick-check-card">
                    <div style="font-size:0.7rem; font-weight:700; text-transform:uppercase;
                                letter-spacing:0.1em; color:#38bdf8; margin-bottom:0.5rem;
                                display:flex; align-items:center; gap:5px;">
                        <span class="material-symbols-outlined" style="font-size:0.9rem;">bolt</span>
                        Officer Quick Check — submit a test transaction and see the ML verdict instantly
                    </div>
                </div>
                """, unsafe_allow_html=True)
                _checkout_form("checkout_dashboard")

            st.markdown("<br>", unsafe_allow_html=True)

            k1, k2, k3, k4 = st.columns(4)

            k1.markdown(f"""
            <div class="metric-kpi-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">
                    <div class="metric-kpi-label">Total Transactions</div>
                    <div class="metric-kpi-icon" style="background:rgba(56,189,248,0.1);">
                        <span class="material-symbols-outlined" style="color:#38bdf8;">receipt_long</span>
                    </div>
                </div>
                <div class="metric-kpi-value">{total:,}</div>
                <div class="metric-kpi-trend" style="color:#64748b;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem;">bar_chart</span> All time
                </div>
            </div>""", unsafe_allow_html=True)

            k2.markdown(f"""
            <div class="metric-kpi-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">
                    <div class="metric-kpi-label">Approval Rate</div>
                    <div class="metric-kpi-icon" style="background:rgba(52,211,153,0.1);">
                        <span class="material-symbols-outlined" style="color:#34d399;">check_circle</span>
                    </div>
                </div>
                <div class="metric-kpi-value" style="color:#34d399;">{approval_rate:.1f}%</div>
                <div class="metric-kpi-trend" style="color:#34d399;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem;">trending_up</span> {approved:,} approved
                </div>
            </div>""", unsafe_allow_html=True)

            k3.markdown(f"""
            <div class="metric-kpi-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">
                    <div class="metric-kpi-label">Pending / Flagged</div>
                    <div class="metric-kpi-icon" style="background:rgba(251,191,36,0.1);">
                        <span class="material-symbols-outlined" style="color:#fbbf24;">pending</span>
                    </div>
                </div>
                <div class="metric-kpi-value" style="color:#fbbf24;">{pending + flagged:,}</div>
                <div class="metric-kpi-trend" style="color:#fbbf24;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem;">warning</span> Needs review
                </div>
            </div>""", unsafe_allow_html=True)

            k4.markdown(f"""
            <div class="metric-kpi-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">
                    <div class="metric-kpi-label">Avg Fraud Score</div>
                    <div class="metric-kpi-icon" style="background:rgba(248,113,113,0.1);">
                        <span class="material-symbols-outlined" style="color:#f87171;">gpp_bad</span>
                    </div>
                </div>
                <div class="metric-kpi-value" style="color:#f87171;">{avg_score:.1%}</div>
                <div class="metric-kpi-trend" style="color:#64748b;">
                    <span class="material-symbols-outlined" style="font-size:0.9rem;">analytics</span> Across all transactions
                </div>
            </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Row 2: Charts ──────────────────────────────────────────────────
            chart_left, chart_right = st.columns(2)

            with chart_left:
                st.markdown("#### :material/pie_chart: Transaction Status Breakdown")
                status_df = pd.DataFrame({
                    "Status": ["Approved", "Pending", "Flagged", "Blocked"],
                    "Count":  [approved, pending, flagged, blocked],
                })
                status_df = status_df[status_df["Count"] > 0]
                if not status_df.empty:
                    st.bar_chart(
                        status_df.set_index("Status"),
                        color="#38bdf8",
                        use_container_width=True,
                        height=250
                    )
                else:
                    st.info("No data to display yet.", icon=":material/info:")

            with chart_right:
                st.markdown("#### :material/history: Recent Transactions")
                try:
                    hist_resp = requests.get(f"{API_BASE}/transactions/history", timeout=5)
                    if hist_resp.status_code == 200:
                        txns = hist_resp.json()[:20]  # last 20, scrollable
                        if txns:
                            # Build all rows as a single HTML string, then wrap
                            # in a fixed-height scrollable container in one markdown call.
                            rows_html = ""
                            for tx in txns:
                                s = tx.get("status", "")
                                pill_class = (
                                    "pill-approved" if s == "Approved" else
                                    "pill-flagged"  if s == "Flagged" else
                                    "pill-blocked"  if s == "Blocked" else
                                    "pill-pending"
                                )
                                rows_html += f"""
                                <div style="display:flex; align-items:center; justify-content:space-between;
                                            padding:0.55rem 0.9rem; border-radius:8px;
                                            border:1px solid rgba(148,163,184,0.1);
                                            background:#1e293b; margin-bottom:0.3rem;">
                                    <div>
                                        <div style="font-family:monospace; font-size:0.72rem; color:#64748b;">{tx.get('transaction_id','—')}</div>
                                        <div style="font-size:0.8rem; color:#94a3b8;">{tx.get('merchant_category','—')}</div>
                                    </div>
                                    <div style="text-align:right;">
                                        <div style="font-weight:700; font-size:0.9rem; color:#f1f5f9;">${tx.get('amount',0):.2f}</div>
                                        <span class="status-pill {pill_class}">{s}</span>
                                    </div>
                                </div>"""
                            st.markdown(
                                f'<div class="recent-tx-scroll">{rows_html}</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.info("No transactions yet.", icon=":material/info:")
                except Exception:
                    st.warning("Could not load recent transactions.", icon=":material/warning:")


        else:
            st.warning("Could not fetch dashboard stats.", icon=":material/warning:")
    except Exception as e:
        st.error(f"API Error: {e}", icon=":material/cancel:")


# ─── Portal: Pending Review ───────────────────────────────────────────────────
def render_pending_review():
    page_header("fact_check", "Pending Review Queue", "Transactions requiring manual officer intervention.")

    try:
        response = requests.get(f"{API_BASE}/transactions/pending", timeout=5)
        if response.status_code == 200:
            transactions = response.json()
            if not transactions:
                st.info("No transactions pending review. All clear!", icon=":material/check_circle:")
            else:
                st.markdown(f"**{len(transactions)} transaction(s) awaiting review**")
                st.markdown("<br>", unsafe_allow_html=True)
                for tx in transactions:
                    border_color = "var(--accent-red)" if tx['status'] == "Flagged" else "var(--accent-amber)"
                    badge_bg     = "rgba(248,113,113,0.12)" if tx['status'] == "Flagged" else "rgba(251,191,36,0.12)"
                    st.markdown(f"""
                    <div class='custom-card' style='border-left: 4px solid {border_color}'>
                        <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                            <div>
                                <span style='font-family:monospace; font-size:0.8rem; color:#94a3b8;'>{tx['created_at']}</span>
                                <h4 style='margin:4px 0;'>{tx['transaction_id']}</h4>
                                <span style='color:#64748b; font-size:0.9rem;'>{tx['merchant_category']}</span>
                                {f"<div style='color:#fbbf24; font-size:0.82rem; margin-top:6px; display:flex; align-items:center; gap:4px;'><span class='material-symbols-outlined' style='font-size:16px; color:#fbbf24;'>lightbulb</span><b>Risk Drivers:</b> {tx['top_factor_1']}{' / ' + tx['top_factor_2'] if tx.get('top_factor_2') else ''}</div>" if tx.get('top_factor_1') else ""}
                            </div>
                            <div style='text-align:right;'>
                                <div style='font-size:1.5rem; font-weight:800;'>${tx['amount']:.2f}</div>
                                <span style='background:{badge_bg}; color:{border_color}; padding:3px 10px; border-radius:20px; font-weight:700; font-size:0.75rem;'>
                                    {tx['status'].upper()}
                                </span>
                            </div>
                        </div>
                        <hr style='border:none; border-top:1px solid rgba(148,163,184,0.1); margin:0.75rem 0;'>
                        <div style='display:flex; gap:2rem; font-size:0.88rem;'>
                            <span><b style='color:#94a3b8;'>Fraud Score</b><br>
                                  <b style='color:{border_color};'>{tx['fraud_probability']:.1%}</b></span>
                            <span><b style='color:#94a3b8;'>Risk Tier</b><br>
                                  <b>{tx['risk_tier']}</b></span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    col1, col2, _ = st.columns([1, 1, 4])
                    if col1.button("Approve", icon=":material/check:", key=f"app_{tx['transaction_id']}", use_container_width=True):
                        req = requests.put(f"{API_BASE}/transactions/{tx['transaction_id']}/approve")
                        if req.status_code == 200:
                            st.success(f"Approved {tx['transaction_id']}", icon=":material/check_circle:")
                            time.sleep(0.8)
                            st.rerun()
                    if col2.button("Block", icon=":material/block:", key=f"blk_{tx['transaction_id']}", type="primary", use_container_width=True):
                        req = requests.put(f"{API_BASE}/transactions/{tx['transaction_id']}/block")
                        if req.status_code == 200:
                            st.error(f"Blocked {tx['transaction_id']}", icon=":material/block:")
                            time.sleep(0.8)
                            st.rerun()
                    st.write("")
        else:
            st.error("Failed to load pending transactions.", icon=":material/cancel:")
    except Exception as e:
        st.error(f"API Error: {e}", icon=":material/cancel:")


# ─── Portal: History ──────────────────────────────────────────────────────────
def render_history():
    page_header("history", "Transaction History", "Complete log of all processed transactions.")

    try:
        response = requests.get(f"{API_BASE}/transactions/history", timeout=5)
        if response.status_code == 200:
            transactions = response.json()
            if not transactions:
                st.info("No transaction history yet. Run some checkout transactions first.", icon=":material/info:")
            else:
                df = pd.DataFrame(transactions)
                for col in ['top_factor_1', 'top_factor_2']:
                    if col not in df.columns:
                        df[col] = None

                display_df = df[[
                    'transaction_id', 'created_at', 'merchant_category',
                    'amount', 'fraud_probability', 'risk_tier', 'status', 'reviewed_at',
                    'top_factor_1', 'top_factor_2'
                ]].copy()

                display_df.columns = [
                    'Transaction ID', 'Created At', 'Category',
                    'Amount', 'Fraud Score', 'Risk Tier', 'Status', 'Reviewed At',
                    'Primary Risk Factor', 'Secondary Risk Factor'
                ]
                display_df['Amount']      = display_df['Amount'].apply(lambda x: f"${x:.2f}")
                display_df['Fraud Score'] = display_df['Fraud Score'].apply(lambda x: f"{x:.1%}")

                def highlight_status(val):
                    if val == 'Approved':
                        return 'background-color: rgba(52,211,153,0.15); color: #34d399'
                    elif val == 'Blocked':
                        return 'background-color: rgba(248,113,113,0.15); color: #f87171'
                    return ''

                st.dataframe(
                    display_df.style.map(highlight_status, subset=['Status']),
                    use_container_width=True,
                    height=550
                )
        else:
            st.error("Failed to load history.", icon=":material/cancel:")
    except Exception as e:
        st.error(f"API Error: {e}", icon=":material/cancel:")


# ─── Portal: CSV Batch Upload ─────────────────────────────────────────────────
def render_csv_upload():
    page_header("upload_file", "CSV Batch Upload", "Upload a CSV file to run fraud detection on multiple transactions at once.")

    st.markdown("#### :material/download: Step 1 — Download the Template")
    st.markdown("<p style='color:#94a3b8; font-size:0.9rem;'>Not sure about the format? Download the sample CSV template and fill in your transactions.</p>", unsafe_allow_html=True)
    if st.button("Download Sample CSV Template", icon=":material/download:", key="download_template"):
        try:
            resp = requests.get(f"{API_BASE}/transactions/batch/template", timeout=10)
            resp.raise_for_status()
            st.download_button(
                label="Save Template File",
                icon=":material/save:",
                data=resp.content,
                file_name="fraud_detection_template.csv",
                mime="text/csv",
                key="save_template"
            )
        except Exception as e:
            st.error(f"Could not fetch template: {e}", icon=":material/cancel:")

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("#### :material/upload: Step 2 — Upload Your CSV")
    st.markdown("<p style='color:#94a3b8; font-size:0.9rem;'>Required columns: <code>merchant, merchant_category, amt, gender, city, state</code>. Optional columns are auto-filled if omitted.</p>", unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Choose a CSV file (max 5,000 rows)", type=["csv"], key="batch_csv_uploader")

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        if len(file_bytes) == 0:
            st.error("The uploaded file is empty. Please choose a valid CSV.", icon=":material/cancel:")
            return

        try:
            preview_df = pd.read_csv(pd.io.common.BytesIO(file_bytes))
            st.markdown(
                f"<p style='color:#34d399; font-size:0.9rem; margin-top:0.5rem; display:flex; align-items:center; gap:4px;'>"
                f"<span class='material-symbols-outlined' style='font-size:18px; color:#34d399;'>check_circle</span>"
                f"File loaded: <b>{uploaded_file.name}</b> — "
                f"{len(preview_df):,} row(s), {len(preview_df.columns)} column(s)</p>",
                unsafe_allow_html=True
            )
            with st.expander("Preview first 5 rows"):
                st.dataframe(preview_df.head(5), use_container_width=True)
        except Exception as e:
            st.error(f"Could not read the CSV: {e}", icon=":material/cancel:")
            return

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### :material/settings: Step 3 — Run Batch Analysis")

        if st.button("Process Batch", icon=":material/rocket_launch:", type="primary", key="run_batch"):
            with st.spinner(f"Analysing {len(preview_df):,} transaction(s)… this may take a moment."):
                try:
                    resp = requests.post(
                        f"{API_BASE}/transactions/batch",
                        files={"file": (uploaded_file.name, file_bytes, "text/csv")},
                        timeout=120
                    )
                    if resp.status_code == 400:
                        st.error(f"Validation error: {resp.json().get('detail', resp.text)}", icon=":material/cancel:")
                        return
                    resp.raise_for_status()
                    st.session_state["batch_result"] = resp.json()
                    st.rerun()  # Real-time refresh for Dashboard stats & Recent Transactions
                except requests.exceptions.ConnectionError:
                    st.error("Cannot connect to the backend. Make sure the API server is running on port 8000.", icon=":material/cancel:")
                    return
                except Exception as e:
                    st.error(f"Batch processing error: {e}", icon=":material/cancel:")
                    return

    if "batch_result" in st.session_state:
        data = st.session_state["batch_result"]
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### :material/bar_chart: Batch Results Summary")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(f"<div class='custom-card'><h3>Total Rows</h3><div class='metric-value'>{data['total_rows']}</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='custom-card'><h3>Processed</h3><div class='metric-value' style='color:var(--accent-blue)'>{data['processed']}</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='custom-card'><h3>Approved</h3><div class='metric-value' style='color:var(--accent-green)'>{data['approved']}</div></div>", unsafe_allow_html=True)
        c4.markdown(f"<div class='custom-card'><h3>Pending</h3><div class='metric-value' style='color:var(--accent-amber)'>{data['pending']}</div></div>", unsafe_allow_html=True)
        c5.markdown(f"<div class='custom-card'><h3>Flagged</h3><div class='metric-value' style='color:var(--accent-red)'>{data['flagged']}</div></div>", unsafe_allow_html=True)

        if data.get("failed", 0) > 0:
            st.warning(f"{data['failed']} row(s) failed to process — see the 'error' column below.", icon=":material/warning:")

        results = data.get("results", [])
        if results:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### :material/fact_check: Per-Row Results")
            results_df = pd.DataFrame(results)
            col_map = {
                "row_number": "Row #", "transaction_id": "Transaction ID",
                "merchant": "Merchant", "amt": "Amount",
                "fraud_probability": "Fraud Score", "risk_tier": "Risk Tier",
                "status": "Status", "error": "Error",
            }
            display_cols = [c for c in col_map if c in results_df.columns]
            results_df = results_df[display_cols].rename(columns=col_map)
            if "Amount" in results_df.columns:
                results_df["Amount"] = results_df["Amount"].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "—")
            if "Fraud Score" in results_df.columns:
                results_df["Fraud Score"] = results_df["Fraud Score"].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "—")

            def color_status(val):
                if val == "Approved":   return "background-color: rgba(52,211,153,0.15); color:#34d399"
                elif val == "Flagged":  return "background-color: rgba(248,113,113,0.15); color:#f87171"
                elif val == "Pending Review": return "background-color: rgba(251,191,36,0.15); color:#fbbf24"
                return ""

            styled = results_df.style.map(color_status, subset=["Status"] if "Status" in results_df.columns else [])
            st.dataframe(styled, use_container_width=True, height=450)

            st.markdown("<br>", unsafe_allow_html=True)
            csv_export = results_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Results as CSV",
                icon=":material/download:",
                data=csv_export,
                file_name="batch_fraud_results.csv",
                mime="text/csv",
                key="download_results"
            )

        if st.button("Clear Results", icon=":material/refresh:", key="clear_batch"):
            del st.session_state["batch_result"]
            st.rerun()


# ─── Portal: API Integration ──────────────────────────────────────────────────
SAMPLE_REQUEST = """{
  "merchant": "My Online Store",
  "merchant_category": "shopping_net",
  "amt": 149.99,
  "gender": "M",
  "city": "New York",
  "state": "NY",
  "city_pop": 500000,
  "distance_from_home": 5.2,
  "is_night_transaction": 0,
  "transaction_hour": 14,
  "weekend_transaction": 0
}"""

SAMPLE_RESPONSE = """{
  "transaction_id": "TRX-3A7F91BC",
  "fraud_probability": 0.042,
  "verdict": "APPROVED",
  "risk_tier": "Low",
  "status": "Approved",
  "top_factors": [
    {"feature": "Distance from Home", "impact": 0.12, "direction": "decreases_risk"},
    {"feature": "Transaction Amount", "impact": 0.05, "direction": "increases_risk"}
  ]
}"""


def render_api_integration():
    page_header("api", "API Integration Guide",
                "Connect your e-commerce or payment system to FraudGuard in minutes.")

    ENDPOINT_URL = f"{API_BASE}/transactions"
    REGISTER_URL = f"{API_BASE}/merchants/register"

    st.markdown("""
    <div style="background:rgba(56,189,248,0.08); border:1px solid rgba(56,189,248,0.25);
                border-left:4px solid #38bdf8; border-radius:12px; padding:1.25rem 1.5rem;
                margin-bottom:1.5rem;">
        <p style="margin:0; color:#cbd5e1; font-size:0.95rem; line-height:1.7; display:flex; align-items:center; gap:6px;">
            <span class="material-symbols-outlined" style="color:#38bdf8;">info</span>
            <span>E-commerce and payment systems can call this endpoint <b>in real time during checkout</b>
            to get an instant fraud verdict before approving a payment.</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### :material/language: Fraud Check Endpoint")
    col_url, col_method = st.columns([4, 1])
    with col_url:
        st.code(ENDPOINT_URL, language="text")
    with col_method:
        st.markdown("<div style='background:rgba(99,102,241,0.18); border:1px solid #6366f1; border-radius:8px; padding:0.55rem 0; text-align:center; color:#a5b4fc; font-weight:700; font-size:0.9rem; margin-top:0.3rem;'>POST</div>", unsafe_allow_html=True)
    st.caption("🔒 Requires header: `X-API-Key: <your_key>` • Rate limit: 100 req / 60 s per key")

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("#### :material/calendar_today: Register a New Merchant")
    st.markdown("<p style='color:#94a3b8; font-size:0.9rem;'>Get a unique API key instantly. Your key is shown only once — save it securely.</p>", unsafe_allow_html=True)

    with st.form("merchant_register_form"):
        reg_col1, reg_col2 = st.columns(2)
        with reg_col1:
            reg_name = st.text_input("Company / Store Name", placeholder="Acme Shop Inc.")
        with reg_col2:
            reg_email = st.text_input("Contact Email", placeholder="dev@acmeshop.com")
        reg_btn = st.form_submit_button("Register & Get API Key", icon=":material/rocket_launch:", type="primary")

    if reg_btn:
        if not reg_name.strip() or not reg_email.strip():
            st.error("Both fields are required.", icon=":material/cancel:")
        else:
            try:
                resp = requests.post(REGISTER_URL, json={"merchant_name": reg_name, "contact_email": reg_email}, timeout=10)
                if resp.status_code == 409:
                    st.error("This email is already registered.", icon=":material/cancel:")
                elif resp.status_code == 200:
                    st.session_state["new_merchant"] = resp.json()
                else:
                    st.error(f"Registration failed ({resp.status_code}): {resp.text}", icon=":material/cancel:")
            except Exception as e:
                st.error(f"Connection error: {e}", icon=":material/cancel:")

    if "new_merchant" in st.session_state:
        d = st.session_state["new_merchant"]
        st.markdown(f"""<div style="background:rgba(52,211,153,0.1); border:1px solid #34d399; border-left:4px solid #34d399; border-radius:12px; padding:1.25rem 1.5rem; margin-top:1rem;">
            <div style="font-size:1rem; font-weight:700; color:#34d399; margin-bottom:0.8rem; display:flex; align-items:center; gap:6px;">
                <span class="material-symbols-outlined" style="color:#34d399;">check_circle</span>
                <span>Merchant Registered: <span style='color:#f1f5f9'>{d['merchant_name']}</span></span>
                &nbsp;<span style='color:#64748b; font-size:0.8rem'>(ID #{d['merchant_id']})</span>
            </div>
            <div style="font-family:monospace; font-size:0.95rem; color:#f1f5f9; background:rgba(0,0,0,0.3); padding:0.75rem 1rem; border-radius:8px; word-break:break-all; margin-bottom:0.75rem;">{d['api_key']}</div>
            <div style="color:#fbbf24; font-size:0.82rem; display:flex; align-items:center; gap:6px;">
                <span class="material-symbols-outlined" style="color:#fbbf24; font-size:16px;">warning</span>
                <span>Copy and store this key securely — it will <b>not</b> be shown again.</span>
            </div>
        </div>""", unsafe_allow_html=True)
        st.download_button(
            label="Download API Key as .txt",
            icon=":material/download:",
            data=f"Merchant: {d['merchant_name']}\nEmail: {d['contact_email']}\nAPI Key: {d['api_key']}\n",
            file_name=f"fraudguard_api_key_{d['merchant_id']}.txt",
            mime="text/plain",
            key="dl_api_key"
        )
        if st.button("Dismiss", icon=":material/cancel:", key="dismiss_merchant"):
            del st.session_state["new_merchant"]
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### :material/code: Code Examples")
    st.markdown("<p style='color:#94a3b8; font-size:0.9rem;'>Replace <code>YOUR_API_KEY</code> with the key you received above.</p>", unsafe_allow_html=True)

    tab_curl, tab_py, tab_js = st.tabs(["  curl  ", "  Python  ", "  JavaScript  "])
    with tab_curl:
        st.code(f"curl -X POST {ENDPOINT_URL} \\\n  -H 'Content-Type: application/json' \\\n  -H 'X-API-Key: YOUR_API_KEY' \\\n  -d '{SAMPLE_REQUEST.strip()}'", language="bash")
    with tab_py:
        st.code(f"""import requests\n\nresponse = requests.post(\n    "{ENDPOINT_URL}",\n    headers={{"X-API-Key": "YOUR_API_KEY"}},\n    json={{\n        "merchant": "My Online Store",\n        "merchant_category": "shopping_net",\n        "amt": 149.99, "gender": "M",\n        "city": "New York", "state": "NY"\n    }}\n)\nprint(response.json()["verdict"])""", language="python")
    with tab_js:
        st.code(f"""const response = await fetch("{ENDPOINT_URL}", {{\n  method: "POST",\n  headers: {{\n    "Content-Type": "application/json",\n    "X-API-Key": "YOUR_API_KEY"\n  }},\n  body: JSON.stringify({{ merchant: "My Online Store", amt: 149.99, gender: "M", city: "New York", state: "NY" }})\n}});\nconst {{ verdict }} = await response.json();\nconsole.log(verdict);""", language="javascript")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### :material/comment: Sample Response")
    st.code(SAMPLE_RESPONSE, language="json")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### :material/menu_book: Response Field Reference")
    ref_data = {
        "Field": ["transaction_id", "fraud_probability", "verdict", "risk_tier", "status"],
        "Type":  ["string", "float (0–1)", "string", "string", "string"],
        "Description": [
            "Unique identifier for audit trail tracking",
            "ML model confidence score (fraud likelihood)",
            "Action: APPROVED / VERIFICATION_REQUIRED / REJECTED",
            "Risk band: Low / Warning / High",
            "DB status: Approved / Pending Review / Flagged",
        ],
        "Merchant Action": [
            "Log for reconciliation",
            "Use for your own risk scoring",
            "Allow | Hold + 3DS/OTP | Block payment",
            "Show warning UI or flag for review",
            "Store for records",
        ],
    }
    st.dataframe(pd.DataFrame(ref_data), use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<p style='color:#64748b; font-size:0.85rem;'>Need help? See the interactive API docs at <a href='http://127.0.0.1:8000/docs' target='_blank' style='color:#38bdf8;'>http://127.0.0.1:8000/docs</a></p>", unsafe_allow_html=True)


# ─── Authenticated Portal Shell ───────────────────────────────────────────────
def _portal_sidebar():
    """Renders the authenticated sidebar with branding, full nav, user info, and logout."""
    current_page = st.session_state.page

    # Branding
    st.sidebar.markdown("""
    <div style="padding: 0.5rem 0 1.25rem 0; text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%;">
        <div style="margin-bottom: 0.3rem;">
            <span class="material-symbols-outlined" style="font-size: 38px; color: #38bdf8;">account_balance</span>
        </div>
        <div style="font-size: 1.1rem; font-weight: 800; color: #f1f5f9; letter-spacing: -0.01em; line-height: 1.2;">FraudGuard</div>
        <div style="font-size: 0.65rem; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.12em;">Officer Portal</div>
        <div style="margin-top: 0.7rem; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.25); border-radius: 20px; padding: 2px 10px; display: inline-block;">
            <span style="color: #34d399; font-size: 0.68rem; font-weight: 700;">● LIVE</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Customer Portal ────────────────────────────────────────────────────────
    st.sidebar.markdown('<div style="font-size:0.68rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.1em; padding:0 0 0.35rem 0.5rem;">Customer Portal</div>', unsafe_allow_html=True)

    def nav_btn(label, icon_name, page_name):
        is_active = (current_page == page_name)
        wrapper_style = "background:rgba(56,189,248,0.08); border-left:3px solid #38bdf8; border-radius:6px; margin-bottom:2px;" if is_active else "margin-bottom:2px;"
        st.sidebar.markdown(f'<div style="{wrapper_style}">', unsafe_allow_html=True)
        if st.sidebar.button(label, icon=f":material/{icon_name}:", use_container_width=True, key=f"nav_{page_name}"):
            st.session_state.page = page_name
            st.query_params["page"] = page_name
            st.rerun()
        st.sidebar.markdown("</div>", unsafe_allow_html=True)

    nav_btn("Merchant Checkout", "storefront",  "Checkout")
    nav_btn("CSV Batch Upload",  "upload_file", "CSV Upload")

    st.sidebar.markdown('<div style="margin:0.6rem 0 0.35rem 0; border-top:1px solid rgba(148,163,184,0.08);"></div>', unsafe_allow_html=True)

    # ── Bank Officer Portal ────────────────────────────────────────────────────
    st.sidebar.markdown('<div style="font-size:0.68rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.1em; padding:0 0 0.35rem 0.5rem;">Bank Officer Portal</div>', unsafe_allow_html=True)

    nav_btn("Dashboard",           "dashboard",  "Dashboard")
    nav_btn("Pending Reviews",     "fact_check", "Pending Review")
    nav_btn("Transaction History", "history",    "History")
    nav_btn("API Integration",     "api",        "API Integration")

    st.sidebar.markdown('<div style="margin:0.5rem 0;"></div>', unsafe_allow_html=True)

    # ── User info block ────────────────────────────────────────────────────────
    username = st.session_state.get("username", "admin")
    initials = username[:2].upper()
    st.sidebar.markdown(f"""
    <div class="sidebar-user-info">
        <div class="sidebar-user-avatar">{initials}</div>
        <div>
            <div style="font-size:0.82rem; font-weight:600; color:#f1f5f9; line-height:1.2;">{username}</div>
            <div style="font-size:0.68rem; color:#38bdf8; font-weight:600; text-transform:uppercase; letter-spacing:0.06em;">Bank Officer</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("Log Out", icon=":material/logout:", use_container_width=True, key="sidebar_logout"):
        logout()

    # ── Footer (in normal document flow, never overlaps nav) ───────────────────
    st.sidebar.markdown("""
    <div style="margin-top: 1.5rem; padding-top: 0.75rem; border-top: 1px solid rgba(148,163,184,0.1); font-size: 0.72rem; color: #475569; line-height: 1.6;">
        Powered by FastAPI + XGBoost<br>
        <span style="color:#1e3a5f;">FraudGuard v2.0</span>
    </div>
    """, unsafe_allow_html=True)


def render_portal():
    """Renders the authenticated officer portal with top bar + sidebar + page content."""
    # Set custom portal block spacing/padding
    st.markdown("""
    <style>
    .block-container { padding-top: 1rem !important; max-width: 1200px !important; }
    </style>
    """, unsafe_allow_html=True)

    _portal_sidebar()

    # Top header bar using columns styled via CSS :has() sibling selector
    st.markdown("""
    <style>
    /* Portal topbar anchor */
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) {
        display: none !important;
        margin: 0 !important; padding: 0 !important; height: 0 !important;
    }
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) + div {
        background: var(--surface) !important;
        border-bottom: 1px solid var(--border) !important;
        padding: 0 1.5rem !important;
        margin: 0 0 1.5rem 0 !important;
        border-radius: var(--radius-sm) !important;
    }
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) + div [data-testid="stHorizontalBlock"] {
        min-height: 56px !important;
        align-items: center !important;
        gap: 0 !important;
    }
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) + div [data-testid="column"] {
        display: flex !important;
        align-items: center !important;
        min-height: 56px !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) + div [data-testid="column"]:last-child {
        justify-content: flex-end !important;
        gap: 1rem !important;
    }
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) + div .stButton,
    [data-testid="stVerticalBlock"] > div:has(.fg-portal-topbar-anchor) + div .stButton > button {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
    </style>
    <div class="fg-portal-topbar-anchor"></div>
    """, unsafe_allow_html=True)

    header_col1, header_col2 = st.columns([2, 1])
    with header_col1:
        st.markdown(f"""
        <div class="portal-topbar-brand">
            <span class="material-symbols-outlined" style="color:#38bdf8; font-size:1.25rem; margin-right:6px;">account_balance</span>
            FraudGuard &nbsp;<span style="color:#475569;">—</span>&nbsp; Officer Portal
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.markdown(f"""
        <div class="portal-user-chip">
            <span class="material-symbols-outlined" style="font-size:1rem; color:#38bdf8;">manage_accounts</span>
            Logged in as <b style="color:#f1f5f9; margin-left:3px;">{st.session_state.get('username','admin')}</b>
            &nbsp;&nbsp;<span style="color:#34d399; font-weight:700;">● Active</span>
        </div>
        """, unsafe_allow_html=True)


    # Route to selected page
    page = st.session_state.page
    if page == "Checkout":
        render_checkout()
    elif page == "Dashboard":
        render_dashboard()
    elif page == "Pending Review":
        render_pending_review()
    elif page == "History":
        render_history()
    elif page == "CSV Upload":
        render_csv_upload()
    elif page == "API Integration":
        render_api_integration()
    else:
        st.session_state.page = "Dashboard"
        st.rerun()


# ─── Root Router ─────────────────────────────────────────────────────────────
def main():
    route = st.session_state.route

    if route == "home":
        render_home()
    elif route == "login":
        render_login()
    elif route == "portal":
        if not st.session_state.logged_in:
            # Guard: redirect to login if session was cleared
            st.session_state.route = "login"
            st.rerun()
        else:
            render_portal()
    else:
        st.session_state.route = "home"
        st.rerun()

if __name__ == "__main__":
    main()
