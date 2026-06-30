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
    initial_sidebar_state="expanded",
)

# ============================================================
# עיצוב מקצועי - RTL מלא + כרטיסי KPI + פלטת צבעים כהה
# ============================================================
st.markdown("""
<style>
    html, body, [class*="css"] {
        direction: rtl;
        text-align: right;
        font-family: 'Segoe UI', 'Heebo', Arial, sans-serif;
    }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    /* כותרת ראשית */
    h1 {
        font-size: 2.1rem !important;
        font-weight: 700 !important;
        background: linear-gradient(90deg, #0ea5e9, #0284c7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0 !important;
    }
    /* כרטיסי KPI */
    div[data-testid="stMetric"] {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 14px;
        padding: 1.1rem 1.2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        transition: border-color 0.15s ease;
    }
    div[data-testid="stMetric"]:hover {
        border-color: #0ea5e9;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: #9ca3af !important;
        font-weight: 500 !important;
        justify-content: flex-end !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        direction: ltr;
        text-align: right !important;
    }
    div[data-testid="stMetricDelta"] {
        justify-content: flex-end !important;
        direction: ltr;
    }
    /* תיבת טקסט - watchlist */
    .stTextArea textarea {
        text-align: left;
        direction: ltr;
        font-family: 'Consolas', monospace;
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 10px !important;
        color: #38bdf8 !important;
    }
    /* טאבים */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        direction: rtl;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-weight: 600;
    }
    /* טבלאות */
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #1f2937;
    }
    /* divider */
    hr {
        margin: 1.2rem 0 !important;
        border-color: #1f2937 !important;
    }
    /* תיבת אזהרה/מידע */
    div[data-testid="stAlert"] {
        border-radius: 10px;
        text-align: right;
    }
    /* כותרות משנה */
    h2, h3 {
        text-align: right !important;
    }
    /* טוגל ו-selectbox מימין */
    .stToggle, .stSelectbox {
        direction: rtl;
    }
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
    st.title("🌊 Nautilus — Live Trading Dashboard")
    st.caption(f"מתעדכן אוטומטית | עדכון אחרון: {datetime.now().strftime('%H:%M:%S')}")
with col_refresh:
    auto_refresh = st.toggle("רענון אוטומטי", value=True)
    refresh_sec = st.selectbox("מרווח (שנ')", [10, 15, 30, 60], index=1, label_visibility="collapsed")

st.divider()

# ============================================================
# רשימת טיקרים פעילה — מסננת מה-Nautilus מתוך כל הפוזיציות
# ============================================================
st.subheader("🎯 רשימת טיקרים פעילה")
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

k5, k4, k3, k2, k1 = st.columns(5)
k1.metric("💰 שווי תיק כולל", f"${account['portfolio_value']:,.2f}")
k2.metric(
    "📈 רווח/הפסד יומי (חשבון)",
    f"${daily_pl:,.2f}",
    f"{daily_pl_pct:+.2f}%",
)
k3.metric("🔓 רווח/הפסד פתוח (Nautilus)", f"${open_pl:,.2f}")
k4.metric("📊 פוזיציות Nautilus פתוחות", len(positions_df))
k5.metric("💵 כוח קנייה", f"${account['buying_power']:,.0f}")

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

        def color_pl(val):
            color = "#16a34a" if val >= 0 else "#dc2626"
            return f"color: {color}; font-weight: bold"

        styled = positions_df.style.applymap(
            color_pl, subset=["Unrealized P&L ($)", "Unrealized P&L (%)"]
        ).format({
            "Avg Entry": "${:.2f}",
            "Current Price": "${:.2f}",
            "Market Value": "${:,.2f}",
            "Unrealized P&L ($)": "${:,.2f}",
            "Unrealized P&L (%)": "{:.2f}%",
            "Qty": "{:.0f}",
        })
        st.dataframe(styled, use_container_width=True, hide_index=True, height=420)

        # פילוח Long/Short
        c1, c2 = st.columns(2)
        with c1:
            long_count = (positions_df["Side"] == "Long").sum()
            short_count = (positions_df["Side"] == "Short").sum()
            st.metric("Long / Short", f"{long_count} / {short_count}")
        with c2:
            winners = (positions_df["Unrealized P&L ($)"] > 0).sum()
            losers = (positions_df["Unrealized P&L ($)"] < 0).sum()
            st.metric("ברווח / בהפסד", f"{winners} / {losers}")

# --- טאב 2: היסטוריית מעקב (יומן עצמי) ---
with tab2:
    if log_df.empty:
        st.info("עדיין אין נתוני היסטוריה. היומן נבנה אוטומטית מרגע שהדשבורד פעיל ויש watchlist מוגדר.")
    else:
        display_log = log_df.copy()
        display_log["logged_at"] = pd.to_datetime(display_log["logged_at"])
        display_log = display_log.sort_values("logged_at", ascending=False)

        st.dataframe(
            display_log[["logged_at", "open_positions_count", "total_unrealized_pl", "watchlist"]].rename(columns={
                "logged_at": "זמן",
                "open_positions_count": "מס' פוזיציות",
                "total_unrealized_pl": "רווח/הפסד פתוח ($)",
                "watchlist": "רשימת טיקרים",
            }),
            use_container_width=True,
            hide_index=True,
            height=400,
        )
        st.caption(f"מציג {len(display_log)} רשומות יומן, מ-{display_log['logged_at'].min().strftime('%d/%m %H:%M')} עד {display_log['logged_at'].max().strftime('%d/%m %H:%M')}")

# --- טאב 3: סטטיסטיקות ---
with tab3:
    if log_df.empty:
        st.info("אין מספיק נתונים לחישוב סטטיסטיקות עדיין — המתן לכמה רענונים.")
    else:
        display_log = log_df.copy()
        display_log["logged_at"] = pd.to_datetime(display_log["logged_at"])
        display_log = display_log.sort_values("logged_at")

        s1, s2, s3 = st.columns(3)
        s1.metric("נקודות מדידה ביומן", len(display_log))
        s2.metric("רווח/הפסד פתוח שיא", f"${display_log['total_unrealized_pl'].max():,.2f}")
        s3.metric("רווח/הפסד פתוח שפל", f"${display_log['total_unrealized_pl'].min():,.2f}")

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
