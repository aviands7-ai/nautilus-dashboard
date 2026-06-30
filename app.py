"""
Nautilus Live Dashboard
========================
דשבורד מסחר חי לעקוב אך ורק אחרי עסקאות Nautilus.

מאחר שאין תיוג source ב-Alpaca/Supabase בין Nautilus ל-Financial Runner,
הדשבורד מסנן פוזיציות חיות לפי רשימת טיקרים שאתה מעדכן ידנית (תואם את
ה-alerts הפעילים שלך ב-TradingView), ובונה היסטוריה משלו ב-Supabase
(טבלה nautilus_dashboard_log) רק מהרגע שהפעלת מעקב לראשונה — בלי
להסתמך על trade_journal המשותפת שלא ניתן להפריד בה בין המנועים.

מקורות נתונים:
- Alpaca API: פוזיציות פתוחות בזמן אמת + P&L (מסונן לפי watchlist)
- Supabase nautilus_dashboard_log: יומן עצמי שהדשבורד בונה החל מהפעלתו

הרצה: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import time
import json

# ============================================================
# הגדרות עמוד
# ============================================================
st.set_page_config(
    page_title="Nautilus Live Dashboard",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# עיצוב - RTL + פלטה אחידה (תואם config.toml theme=dark)
# ============================================================
st.markdown("""
<style>
    * { direction: rtl; }
    .stApp { direction: rtl; }

    .main .block-container {
        max-width: 1280px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3, h4, p, span, label, div {
        text-align: right;
    }

    h1 {
        font-size: 1.9rem !important;
        font-weight: 700 !important;
        color: #f1f5f9 !important;
        margin-bottom: 0.2rem !important;
        letter-spacing: -0.01em;
    }

    [data-testid="stCaptionContainer"] {
        color: #64748b !important;
        font-size: 0.85rem !important;
    }

    h2 {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: #cbd5e1 !important;
        margin-top: 0 !important;
    }

    /* כרטיסי KPI - אחיד עם הרקע */
    div[data-testid="stMetric"] {
        background: #131c2e;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 1rem 1.1rem;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.8rem !important;
        color: #94a3b8 !important;
        font-weight: 500 !important;
        text-align: right !important;
        justify-content: flex-end !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #f1f5f9 !important;
        direction: ltr;
        text-align: right !important;
        justify-content: flex-end !important;
    }
    div[data-testid="stMetricDelta"] {
        justify-content: flex-end !important;
        direction: ltr;
    }

    /* תיבת watchlist */
    .stTextArea textarea {
        text-align: left !important;
        direction: ltr !important;
        font-family: 'SFMono-Regular', Consolas, monospace !important;
        font-size: 0.9rem !important;
        background: #0b1120 !important;
        border: 1px solid #1e293b !important;
        border-radius: 10px !important;
        color: #38bdf8 !important;
    }
    .stTextArea textarea:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 1px #3b82f6 !important;
    }

    /* טאבים */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid #1e293b;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 8px 8px 0 0;
        padding: 8px 18px;
        font-weight: 500;
        font-size: 0.9rem;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        color: #3b82f6 !important;
        border-bottom: 2px solid #3b82f6;
    }

    /* טבלאות */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        border: 1px solid #1e293b;
        overflow: hidden;
    }

    /* alerts */
    div[data-testid="stAlert"] {
        border-radius: 10px;
        text-align: right;
    }

    /* divider */
    hr { border-color: #1e293b !important; margin: 1.5rem 0 !important; }

    /* כפתורים וטוגלים מיושרים נכון */
    .stToggle, .stSelectbox, .stButton { direction: rtl; }
    .stSelectbox > div { text-align: right; }

    /* הסתרת תפריט/footer של Streamlit לתחושת אפליקציה אמיתית */
    #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# חיבורים - Alpaca + Supabase
# ============================================================
@st.cache_resource
def get_alpaca_client():
    from alpaca.trading.client import TradingClient
    return TradingClient(
        api_key=st.secrets["ALPACA_API_KEY"],
        secret_key=st.secrets["ALPACA_API_SECRET"],
        paper=True,  # שנה ל-False אם עובד על חשבון live
    )


@st.cache_resource
def get_supabase_client():
    from supabase import create_client
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


# ============================================================
# שליפת נתונים
# ============================================================
@st.cache_data(ttl=15)  # רענון כל 15 שניות
def fetch_open_positions():
    client = get_alpaca_client()
    positions = client.get_all_positions()
    rows = []
    for p in positions:
        rows.append({
            "Symbol": p.symbol,
            "Side": "Long" if p.side == "long" else "Short",
            "Qty": float(p.qty),
            "Avg Entry": float(p.avg_entry_price),
            "Current Price": float(p.current_price) if p.current_price else None,
            "Market Value": float(p.market_value),
            "Unrealized P&L ($)": float(p.unrealized_pl),
            "Unrealized P&L (%)": float(p.unrealized_plpc) * 100,
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=15)
def fetch_account_summary():
    client = get_alpaca_client()
    account = client.get_account()
    return {
        "equity": float(account.equity),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "portfolio_value": float(account.portfolio_value),
        "last_equity": float(account.last_equity),
    }


@st.cache_data(ttl=20)
def fetch_dashboard_log(limit=500):
    """
    שולף את היומן העצמי שהדשבורד בנה — לא trade_journal המשותפת.
    אם הטבלה לא קיימת עדיין, מחזיר DataFrame ריק (הטבלה תיווצר
    אוטומטית בקריאה הראשונה ל-log_snapshot).
    """
    supabase = get_supabase_client()
    try:
        response = (
            supabase.table("nautilus_dashboard_log")
            .select("*")
            .order("id", desc=False)
            .limit(limit)
            .execute()
        )
        return pd.DataFrame(response.data)
    except Exception:
        return pd.DataFrame()


def log_snapshot(watchlist_symbols, positions_df):
    """
    שומר snapshot של מצב הפוזיציות המסוננות לטבלה העצמית.
    נקרא פעם בכל ריענון — בונה היסטוריה רציפה משלנו, ללא תלות
    ב-trade_journal שלא מתויג לפי source.
    """
    supabase = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()
    total_pl = float(positions_df["Unrealized P&L ($)"].sum()) if not positions_df.empty else 0.0
    open_count = len(positions_df)

    record = {
        "logged_at": now,
        "watchlist": ",".join(sorted(watchlist_symbols)),
        "open_positions_count": open_count,
        "total_unrealized_pl": total_pl,
        "positions_snapshot": json.dumps(
            positions_df.to_dict(orient="records") if not positions_df.empty else []
        ),
    }
    try:
        supabase.table("nautilus_dashboard_log").insert(record).execute()
    except Exception as e:
        st.session_state["log_error"] = str(e)


def get_tracking_start():
    """מחזיר את תאריך תחילת המעקב (הרשומה הראשונה ביומן)."""
    log_df = fetch_dashboard_log(limit=1)
    if log_df.empty:
        return None
    return log_df.iloc[0]["logged_at"]


# ============================================================
# כותרת + רענון אוטומטי
# ============================================================
col_refresh, col_title = st.columns([1, 4])
with col_title:
    st.markdown("""
    <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.9rem;">🌊</span>
        <h1 style="margin:0; padding:0;">Nautilus — Live Trading Dashboard</h1>
    </div>
    """, unsafe_allow_html=True)
    st.caption(f"מתעדכן אוטומטית · עדכון אחרון {datetime.now().strftime('%H:%M:%S')}")
with col_refresh:
    auto_refresh = st.toggle("רענון אוטומטי", value=True)
    refresh_sec = st.selectbox("מרווח (שנ')", [10, 15, 30, 60], index=1, label_visibility="collapsed")

st.divider()

# ============================================================
# רשימת טיקרים פעילה — מסננת מה-Nautilus מתוך כל הפוזיציות
# ============================================================
st.markdown("""
<div style="display:flex; align-items:center; gap:8px; margin-bottom:2px;">
    <span style="font-size:1.1rem;">🎯</span>
    <h2 style="margin:0;">רשימת טיקרים פעילה</h2>
</div>
""", unsafe_allow_html=True)
st.caption("עדכן כל פעם שמשנים alert ב-TradingView. הדשבורד יסנן רק פוזיציות עם הסימבולים האלה.")

if "watchlist_text" not in st.session_state:
    st.session_state["watchlist_text"] = ""

watchlist_input = st.text_area(
    "טיקרים (מופרדים בפסיק)",
    value=st.session_state["watchlist_text"],
    height=68,
    placeholder="ORCL, IREN, MRVL, SMH, CRWV, AMZN, COST, AAPL, TSLA, NVDA",
    label_visibility="collapsed",
)
st.session_state["watchlist_text"] = watchlist_input
watchlist_symbols = set(
    s.strip().upper() for s in watchlist_input.split(",") if s.strip()
)

if not watchlist_symbols:
    st.warning("⚠️ הזן לפחות טיקר אחד כדי לסנן פוזיציות Nautilus.")

st.divider()

# ============================================================
# שגיאות חיבור - הצגה ידידותית
# ============================================================
try:
    account = fetch_account_summary()
    all_positions_df = fetch_open_positions()
    if not all_positions_df.empty and watchlist_symbols:
        positions_df = all_positions_df[all_positions_df["Symbol"].isin(watchlist_symbols)].copy()
    else:
        positions_df = pd.DataFrame(columns=all_positions_df.columns if not all_positions_df.empty else [])
    connection_ok = True
except Exception as e:
    connection_ok = False
    st.error(f"⚠️ שגיאת חיבור: {e}")
    st.info("ודא שה-secrets מוגדרים נכון: ALPACA_API_KEY, ALPACA_API_SECRET, SUPABASE_URL, SUPABASE_KEY")
    st.stop()

# שמירת snapshot ביומן העצמי (בונה היסטוריה רציפה לאורך זמן)
if watchlist_symbols:
    log_snapshot(watchlist_symbols, positions_df)

log_df = fetch_dashboard_log()
tracking_start = get_tracking_start()

# ============================================================
# שורת KPI עליונה
# ============================================================
daily_pl = account["equity"] - account["last_equity"]
daily_pl_pct = (daily_pl / account["last_equity"] * 100) if account["last_equity"] else 0
open_pl = positions_df["Unrealized P&L ($)"].sum() if not positions_df.empty else 0

def kpi_card(label, value, color="#f1f5f9", sub=None):
    sub_html = f'<div style="font-size:0.78rem; color:#64748b; margin-top:4px; direction:ltr; text-align:right;">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div style="background:#131c2e; border:1px solid #1e293b; border-radius:12px; padding:1rem 1.1rem; height:100%;">
        <div style="font-size:0.8rem; color:#94a3b8; font-weight:500; margin-bottom:6px;">{label}</div>
        <div style="font-size:1.5rem; font-weight:700; color:{color}; direction:ltr; text-align:right;">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

k5, k4, k3, k2, k1 = st.columns(5)
with k1:
    kpi_card("שווי תיק כולל", f"${account['portfolio_value']:,.2f}")
with k2:
    pl_color = "#4ade80" if daily_pl >= 0 else "#f87171"
    kpi_card("רווח/הפסד יומי (חשבון)", f"${daily_pl:,.2f}", color=pl_color, sub=f"{daily_pl_pct:+.2f}%")
with k3:
    open_color = "#4ade80" if open_pl >= 0 else "#f87171"
    kpi_card("רווח/הפסד פתוח (Nautilus)", f"${open_pl:,.2f}", color=open_color)
with k4:
    kpi_card("פוזיציות Nautilus פתוחות", str(len(positions_df)))
with k5:
    kpi_card("כוח קנייה", f"${account['buying_power']:,.0f}")

if tracking_start:
    tracking_dt = pd.to_datetime(tracking_start)
    st.caption(f"📅 מעקב Nautilus החל מ-{tracking_dt.strftime('%d/%m/%Y %H:%M')} — ההיסטוריה למטה רק מהנקודה הזו ואילך.")
else:
    st.caption("📅 זהו הריצה הראשונה — היסטוריית המעקב תתחיל להיבנות מעכשיו.")

st.divider()

# ============================================================
# טאבים: פוזיציות פתוחות | היסטוריה | סטטיסטיקות
# ============================================================
tab1, tab2, tab3 = st.tabs(["🔴 פוזיציות Nautilus פתוחות", "📜 יומן מעקב (מאז ההפעלה)", "📊 גרפים וסטטיסטיקות"])

# --- טאב 1: פוזיציות פתוחות ---
with tab1:
    if positions_df.empty:
        st.info("אין פוזיציות Nautilus פתוחות התואמות לרשימת הטיקרים שהזנת.")
    else:
        # מיון לפי P&L
        positions_df = positions_df.sort_values("Unrealized P&L ($)", ascending=False)

        rows_html = ""
        for _, row in positions_df.iterrows():
            pl_color = "#4ade80" if row["Unrealized P&L ($)"] >= 0 else "#f87171"
            side_color = "#4ade80" if row["Side"] == "Long" else "#f87171"
            side_bg = "rgba(74,222,128,0.12)" if row["Side"] == "Long" else "rgba(248,113,113,0.12)"
            rows_html += f"""
            <tr style="border-bottom:1px solid #1e293b;">
                <td style="padding:10px 12px; font-weight:600; text-align:right;">{row['Symbol']}</td>
                <td style="padding:10px 12px; text-align:right;">
                    <span style="background:{side_bg}; color:{side_color}; font-size:0.78rem; padding:3px 10px; border-radius:6px; font-weight:600;">{row['Side']}</span>
                </td>
                <td style="padding:10px 12px; text-align:right; direction:ltr;">{row['Qty']:,.0f}</td>
                <td style="padding:10px 12px; text-align:right; direction:ltr;">${row['Avg Entry']:,.2f}</td>
                <td style="padding:10px 12px; text-align:right; direction:ltr;">${row['Current Price']:,.2f}</td>
                <td style="padding:10px 12px; text-align:right; direction:ltr; color:{pl_color}; font-weight:700;">${row['Unrealized P&L ($)']:,.2f}</td>
                <td style="padding:10px 12px; text-align:right; direction:ltr; color:{pl_color}; font-weight:600;">{row['Unrealized P&L (%)']:+.2f}%</td>
            </tr>
            """

        table_html = f"""
        <div style="border:1px solid #1e293b; border-radius:10px; overflow:hidden;">
        <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
            <thead>
                <tr style="background:#0b1120; border-bottom:1px solid #1e293b;">
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">סימבול</th>
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">כיוון</th>
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">כמות</th>
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">כניסה</th>
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">נוכחי</th>
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">רווח/הפסד</th>
                    <th style="padding:10px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem;">אחוז</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)

        st.write("")

        # פילוח Long/Short
        c2, c1 = st.columns(2)
        with c1:
            long_count = (positions_df["Side"] == "Long").sum()
            short_count = (positions_df["Side"] == "Short").sum()
            kpi_card("Long / Short", f"{long_count} / {short_count}")
        with c2:
            winners = (positions_df["Unrealized P&L ($)"] > 0).sum()
            losers = (positions_df["Unrealized P&L ($)"] < 0).sum()
            kpi_card("ברווח / בהפסד", f"{winners} / {losers}")

# --- טאב 2: היסטוריית מעקב (יומן עצמי) ---
with tab2:
    if log_df.empty:
        st.info("עדיין אין נתוני היסטוריה. היומן נבנה אוטומטית מרגע שהדשבורד פעיל ויש watchlist מוגדר.")
    else:
        display_log = log_df.copy()
        display_log["logged_at"] = pd.to_datetime(display_log["logged_at"])
        display_log = display_log.sort_values("logged_at", ascending=False)

        log_rows_html = ""
        for _, row in display_log.iterrows():
            pl_val = row["total_unrealized_pl"]
            pl_color = "#4ade80" if pl_val >= 0 else "#f87171"
            log_rows_html += f"""
            <tr style="border-bottom:1px solid #1e293b;">
                <td style="padding:8px 12px; text-align:right; direction:ltr; color:#cbd5e1; font-size:0.85rem;">{row['logged_at'].strftime('%d/%m %H:%M:%S')}</td>
                <td style="padding:8px 12px; text-align:right; direction:ltr;">{row['open_positions_count']}</td>
                <td style="padding:8px 12px; text-align:right; direction:ltr; color:{pl_color}; font-weight:600;">${pl_val:,.2f}</td>
                <td style="padding:8px 12px; text-align:left; direction:ltr; color:#64748b; font-size:0.8rem; font-family:monospace;">{row['watchlist']}</td>
            </tr>
            """

        log_table_html = f"""
        <div style="border:1px solid #1e293b; border-radius:10px; overflow:hidden; max-height:420px; overflow-y:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
            <thead>
                <tr style="background:#0b1120; border-bottom:1px solid #1e293b;">
                    <th style="padding:8px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem; position:sticky; top:0; background:#0b1120;">זמן</th>
                    <th style="padding:8px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem; position:sticky; top:0; background:#0b1120;">פוזיציות</th>
                    <th style="padding:8px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem; position:sticky; top:0; background:#0b1120;">רווח/הפסד פתוח</th>
                    <th style="padding:8px 12px; text-align:right; color:#94a3b8; font-weight:600; font-size:0.8rem; position:sticky; top:0; background:#0b1120;">רשימת טיקרים</th>
                </tr>
            </thead>
            <tbody>
                {log_rows_html}
            </tbody>
        </table>
        </div>
        """
        st.markdown(log_table_html, unsafe_allow_html=True)
        st.caption(f"מציג {len(display_log)} רשומות יומן, מ-{display_log['logged_at'].min().strftime('%d/%m %H:%M')} עד {display_log['logged_at'].max().strftime('%d/%m %H:%M')}")

# --- טאב 3: סטטיסטיקות ---
with tab3:
    if log_df.empty:
        st.info("אין מספיק נתונים לחישוב סטטיסטיקות עדיין — המתן לכמה רענונים.")
    else:
        display_log = log_df.copy()
        display_log["logged_at"] = pd.to_datetime(display_log["logged_at"])
        display_log = display_log.sort_values("logged_at")

        s3, s2, s1 = st.columns(3)
        with s1:
            kpi_card("נקודות מדידה ביומן", str(len(display_log)))
        with s2:
            kpi_card("רווח/הפסד פתוח שיא", f"${display_log['total_unrealized_pl'].max():,.2f}", color="#4ade80")
        with s3:
            kpi_card("רווח/הפסד פתוח שפל", f"${display_log['total_unrealized_pl'].min():,.2f}", color="#f87171")

        st.markdown("**רווח/הפסד פתוח לאורך זמן (Nautilus בלבד)**")
        chart_data = display_log.set_index("logged_at")["total_unrealized_pl"]
        st.line_chart(chart_data, use_container_width=True)

        st.markdown("**מספר פוזיציות פתוחות לאורך זמן**")
        positions_chart = display_log.set_index("logged_at")["open_positions_count"]
        st.line_chart(positions_chart, use_container_width=True)

# ============================================================
# רענון אוטומטי
# ============================================================
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()
