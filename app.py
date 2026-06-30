"""
Nautilus — מסך פשוט
=====================
מציג רק שני מספרים: כמה פוזיציות Nautilus פתוחות עכשיו,
וכמה רווח/הפסד הן צוברות כרגע.

הרצה: streamlit run app.py
"""

import streamlit as st
import time

st.set_page_config(page_title="Nautilus", page_icon="🌊", layout="centered")

st.markdown("""
<style>
* { direction: rtl; text-align: center; }
.main .block-container { padding-top: 4rem; max-width: 600px; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.stTextArea textarea { text-align: left; direction: ltr; font-family: monospace; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_alpaca_client():
    from alpaca.trading.client import TradingClient
    return TradingClient(
        api_key=st.secrets["ALPACA_API_KEY"],
        secret_key=st.secrets["ALPACA_API_SECRET"],
        paper=True,
    )


@st.cache_data(ttl=15)
def fetch_positions():
    client = get_alpaca_client()
    positions = client.get_all_positions()
    return [
        {"symbol": p.symbol, "pl": float(p.unrealized_pl)}
        for p in positions
    ]


if "tickers" not in st.session_state:
    st.session_state["tickers"] = "IREN, COST"

with st.expander("⚙️ אילו טיקרים שייכים ל-Nautilus"):
    st.session_state["tickers"] = st.text_area(
        "טיקרים", value=st.session_state["tickers"], label_visibility="collapsed"
    )

watchlist = set(t.strip().upper() for t in st.session_state["tickers"].split(",") if t.strip())

try:
    all_positions = fetch_positions()
    nautilus_positions = [p for p in all_positions if p["symbol"] in watchlist]
    count = len(nautilus_positions)
    total_pl = sum(p["pl"] for p in nautilus_positions)
    error = None
except Exception as e:
    count = 0
    total_pl = 0
    error = str(e)

if error:
    st.error(f"שגיאת חיבור: {error}")
else:
    pl_color = "#4ade80" if total_pl >= 0 else "#f87171"

    st.markdown(f"""
    <div style="margin-top:2rem;">
        <div style="font-size:1rem; color:#94a3b8; margin-bottom:0.5rem;">פוזיציות Nautilus פתוחות</div>
        <div style="font-size:5rem; font-weight:700; line-height:1;">{count}</div>
    </div>
    <div style="margin-top:3rem;">
        <div style="font-size:1rem; color:#94a3b8; margin-bottom:0.5rem;">רווח / הפסד עכשיו</div>
        <div style="font-size:4rem; font-weight:700; color:{pl_color}; direction:ltr;">${total_pl:,.0f}</div>
    </div>
    """, unsafe_allow_html=True)

    if count > 0:
        st.write("")
        st.write("")
        symbols_line = "  ·  ".join(
            f"{p['symbol']} ({'+' if p['pl']>=0 else ''}{p['pl']:,.0f}$)"
            for p in nautilus_positions
        )
        st.caption(symbols_line)

st.write("")
st.write("")
auto = st.toggle("רענון אוטומטי", value=True)
if auto:
    time.sleep(15)
    st.rerun()
