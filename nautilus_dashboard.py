# ============================================================
# Nautilus Control Room — מסך בקרה למערכת FTI Nautilus Pro
# The Financial Runner © 2026
# ------------------------------------------------------------
# READ-ONLY monitor. This dashboard NEVER writes, cancels, or
# modifies any order or position. It only displays.
#
# Data sources:
#   • Alpaca  (live truth)     — open positions, pending orders,
#                                live P&L, account equity
#   • Supabase (history)       — event log (trade_executions),
#                                closed-trade stats, equity history
# ============================================================
import os
from datetime import datetime, timezone, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Optional deps: fail gracefully with a clear message, never a stack trace ──
try:
    from supabase import create_client
    _SUPABASE_AVAILABLE = True
except Exception:
    _SUPABASE_AVAILABLE = False

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    _ALPACA_AVAILABLE = True
except Exception:
    _ALPACA_AVAILABLE = False


# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="Nautilus Control Room",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

REFRESH_SECONDS = 30


def _get_secret(name: str, default: str = "") -> str:
    """Read from st.secrets first (Streamlit Cloud), then env (Railway/local)."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


SUPABASE_URL   = _get_secret("SUPABASE_URL")
SUPABASE_KEY   = _get_secret("SUPABASE_KEY")
ALPACA_KEY     = _get_secret("APCA_API_KEY_ID")
ALPACA_SECRET  = _get_secret("APCA_API_SECRET_KEY")
ALPACA_PAPER   = _get_secret("ALPACA_PAPER", "true").lower() != "false"


# ============================================================
# STYLING — a control-room look: deep slate, instrument-panel
# cyan/amber accents, monospace for numbers. Not a template.
# ============================================================
st.markdown(
    """
    <style>
    :root {
        --bg:        #0d1117;
        --panel:     #161b22;
        --border:    #21262d;
        --ink:       #e6edf3;
        --muted:     #7d8590;
        --cyan:      #2f9e9e;
        --amber:     #d9a441;
        --green:     #3fb950;
        --red:       #f85149;
    }
    .stApp { background: var(--bg); }
    section[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--border); }
    h1, h2, h3 { color: var(--ink); font-family: 'Inter', system-ui, sans-serif; letter-spacing: -0.01em; }
    .metric-num { font-family: 'JetBrains Mono', 'SF Mono', monospace; }
    .panel {
        background: var(--panel); border: 1px solid var(--border);
        border-radius: 10px; padding: 18px 20px; margin-bottom: 14px;
    }
    .panel-title {
        color: var(--muted); font-size: 12px; text-transform: uppercase;
        letter-spacing: 0.08em; margin-bottom: 12px; font-weight: 600;
    }
    .stat-big { font-size: 30px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .pos { color: var(--green); }
    .neg { color: var(--red); }
    .neutral { color: var(--ink); }
    .pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 600; font-family: monospace;
    }
    .pill-live { background: rgba(63,185,80,0.15); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
    .pill-stale { background: rgba(248,81,73,0.12); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }
    .pill-warn { background: rgba(217,164,65,0.12); color: var(--amber); border: 1px solid rgba(217,164,65,0.3); }
    div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATA LAYER — every fetch is wrapped so a single source failing
# never blanks the whole dashboard. Each returns (data, error).
# ============================================================
@st.cache_resource
def get_supabase():
    if not (_SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


@st.cache_resource
def get_alpaca():
    if not (_ALPACA_AVAILABLE and ALPACA_KEY and ALPACA_SECRET):
        return None
    try:
        return TradingClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET, paper=ALPACA_PAPER)
    except Exception:
        return None


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch_alpaca_account():
    client = get_alpaca()
    if client is None:
        return None, "Alpaca not connected"
    try:
        acct = client.get_account()
        return {
            "equity": float(acct.equity),
            "last_equity": float(acct.last_equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "status": str(acct.status),
            "account_number": acct.account_number,
        }, None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch_alpaca_positions():
    client = get_alpaca()
    if client is None:
        return pd.DataFrame(), "Alpaca not connected"
    try:
        positions = client.get_all_positions()
        if not positions:
            return pd.DataFrame(), None
        rows = []
        for p in positions:
            rows.append({
                "Symbol": p.symbol,
                "Side": p.side.value if hasattr(p.side, "value") else str(p.side),
                "Qty": float(p.qty),
                "Avg Entry": float(p.avg_entry_price),
                "Current": float(p.current_price),
                "Mkt Value": float(p.market_value),
                "Unreal P&L": float(p.unrealized_pl),
                "Unreal P&L %": float(p.unrealized_plpc) * 100,
            })
        return pd.DataFrame(rows), None
    except Exception as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch_alpaca_open_orders():
    client = get_alpaca()
    if client is None:
        return pd.DataFrame(), "Alpaca not connected"
    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100)
        orders = client.get_orders(req)
        if not orders:
            return pd.DataFrame(), None
        rows = []
        for o in orders:
            rows.append({
                "Symbol": o.symbol,
                "Side": o.side.value if hasattr(o.side, "value") else str(o.side),
                "Type": o.order_type.value if hasattr(o.order_type, "value") else str(o.order_type),
                "Qty": float(o.qty) if o.qty else None,
                "Limit": float(o.limit_price) if o.limit_price else None,
                "Stop": float(o.stop_price) if o.stop_price else None,
                "Status": o.status.value if hasattr(o.status, "value") else str(o.status),
                "Submitted": o.submitted_at.strftime("%Y-%m-%d %H:%M") if o.submitted_at else "",
            })
        return pd.DataFrame(rows), None
    except Exception as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch_event_log(limit: int = 200):
    sb = get_supabase()
    if sb is None:
        return pd.DataFrame(), "Supabase not connected"
    try:
        resp = (
            sb.table("trade_executions")
            .select("created_at, event_type, execution_price, exit_price, pnl_usd, pnl_pct, trading_days_open, alpaca_order_id")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        df = pd.DataFrame(resp.data or [])
        if not df.empty:
            df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch_equity_history(limit: int = 500):
    sb = get_supabase()
    if sb is None:
        return pd.DataFrame(), "Supabase not connected"
    try:
        resp = (
            sb.table("nautilus_dashboard_log")
            .select("logged_at, open_positions_count, total_unrealized_pl")
            .order("logged_at", desc=True)
            .limit(limit)
            .execute()
        )
        df = pd.DataFrame(resp.data or [])
        if not df.empty:
            df["logged_at"] = pd.to_datetime(df["logged_at"], utc=True, errors="coerce")
            df = df.sort_values("logged_at")
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


# ============================================================
# STATS — computed only from CLOSED trades (rows with a real
# exit + pnl). Honest about insufficient data rather than
# inventing a win rate from zero closes.
# ============================================================
def compute_stats(event_df: pd.DataFrame) -> dict:
    empty = {
        "closed": 0, "wins": 0, "losses": 0,
        "win_rate": None, "profit_factor": None,
        "total_pnl": 0.0, "avg_win": None, "avg_loss": None,
    }
    if event_df.empty or "pnl_usd" not in event_df.columns:
        return empty

    # A closed trade = a row that carries a realised P&L value.
    closed = event_df[event_df["pnl_usd"].notna()].copy()
    if closed.empty:
        return empty

    wins = closed[closed["pnl_usd"] > 0]
    losses = closed[closed["pnl_usd"] < 0]
    gross_win = wins["pnl_usd"].sum()
    gross_loss = abs(losses["pnl_usd"].sum())

    return {
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(closed) * 100) if len(closed) else None,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "total_pnl": closed["pnl_usd"].sum(),
        "avg_win": wins["pnl_usd"].mean() if len(wins) else None,
        "avg_loss": losses["pnl_usd"].mean() if len(losses) else None,
    }


# ============================================================
# UI HELPERS
# ============================================================
def money(v, decimals=2):
    if v is None or pd.isna(v):
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.{decimals}f}"


def pct(v, decimals=1):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.{decimals}f}%"


def pnl_class(v):
    if v is None or pd.isna(v) or v == 0:
        return "neutral"
    return "pos" if v > 0 else "neg"


# ============================================================
# SIDEBAR — connection status + controls
# ============================================================
with st.sidebar:
    st.markdown("### 🎛️ Nautilus Control Room")
    st.caption("Read-only monitor · does not trade")
    st.divider()

    st.markdown("**Connections**")
    alpaca_ok = get_alpaca() is not None
    supa_ok = get_supabase() is not None
    st.markdown(
        f"{'🟢' if alpaca_ok else '🔴'} Alpaca "
        f"({'Paper' if ALPACA_PAPER else 'LIVE'})",
    )
    st.markdown(f"{'🟢' if supa_ok else '🔴'} Supabase")
    st.divider()

    if st.button("🔄 Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    auto = st.toggle("Auto-refresh", value=False)
    st.caption(f"Every {REFRESH_SECONDS}s when on")
    st.divider()
    st.caption(f"Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")


# ============================================================
# HEADER + TOP-LINE ACCOUNT STRIP
# ============================================================
st.markdown("## Control Room")

acct, acct_err = fetch_alpaca_account()

c1, c2, c3, c4 = st.columns(4)
if acct:
    day_change = acct["equity"] - acct["last_equity"]
    day_change_pct = (day_change / acct["last_equity"] * 100) if acct["last_equity"] else 0
    with c1:
        st.markdown('<div class="panel-title">Equity</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="stat-big neutral">{money(acct["equity"])}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="panel-title">Today</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="stat-big {pnl_class(day_change)}">{money(day_change)} '
            f'<span style="font-size:15px">({pct(day_change_pct)})</span></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown('<div class="panel-title">Cash</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="stat-big neutral">{money(acct["cash"])}</div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class="panel-title">Buying Power</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="stat-big neutral">{money(acct["buying_power"])}</div>', unsafe_allow_html=True)
else:
    st.warning(
        "Alpaca account data unavailable. "
        "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in secrets/env to see live account state."
        + (f"  \n_Detail: {acct_err}_" if acct_err else "")
    )

st.divider()


# ============================================================
# MAIN TABS
# ============================================================
tab_live, tab_stats, tab_equity, tab_log = st.tabs(
    ["🔴 Live", "📊 Performance", "📈 Equity", "📜 Event Log"]
)

# ────────────────────────────────────────────────────────────
# TAB 1: LIVE — positions + pending orders (Alpaca truth)
# ────────────────────────────────────────────────────────────
with tab_live:
    left, right = st.columns([1.4, 1])

    with left:
        st.markdown("#### Open Positions")
        pos_df, pos_err = fetch_alpaca_positions()
        if pos_err:
            st.info(f"Positions unavailable — {pos_err}")
        elif pos_df.empty:
            st.markdown(
                '<div class="panel">No open positions right now. '
                'When the system enters a trade, it appears here in real time.</div>',
                unsafe_allow_html=True,
            )
        else:
            total_upl = pos_df["Unreal P&L"].sum()
            st.markdown(
                f'Live unrealized P&L: '
                f'<span class="stat-big {pnl_class(total_upl)}">{money(total_upl)}</span>',
                unsafe_allow_html=True,
            )
            styled = pos_df.style.format({
                "Qty": "{:.0f}", "Avg Entry": "${:.2f}", "Current": "${:.2f}",
                "Mkt Value": "${:,.2f}", "Unreal P&L": "${:,.2f}", "Unreal P&L %": "{:.2f}%",
            }).map(
                lambda v: f"color: {'#3fb950' if v > 0 else '#f85149'}" if isinstance(v, (int, float)) else "",
                subset=["Unreal P&L", "Unreal P&L %"],
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)

    with right:
        st.markdown("#### Pending Orders")
        ord_df, ord_err = fetch_alpaca_open_orders()
        if ord_err:
            st.info(f"Orders unavailable — {ord_err}")
        elif ord_df.empty:
            st.markdown(
                '<div class="panel">No pending orders. '
                'Limit orders waiting to fill — and anything the Kill Switch is about '
                'to cancel — show up here.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.dataframe(
                ord_df.style.format({
                    "Qty": "{:.0f}", "Limit": "${:.2f}", "Stop": "${:.2f}",
                }, na_rep="—"),
                use_container_width=True, hide_index=True,
            )

# ────────────────────────────────────────────────────────────
# TAB 2: PERFORMANCE — stats from closed trades, honest gaps
# ────────────────────────────────────────────────────────────
with tab_stats:
    log_df, log_err = fetch_event_log(limit=500)
    if log_err:
        st.info(f"History unavailable — {log_err}")
    else:
        # Date filter
        fcol1, fcol2, _ = st.columns([1, 1, 2])
        with fcol1:
            days_back = st.selectbox("Period", [7, 30, 90, 365, 99999],
                                     format_func=lambda d: "All time" if d == 99999 else f"Last {d}d",
                                     index=4)
        filtered = log_df.copy()
        if not filtered.empty and days_back != 99999:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back)
            filtered = filtered[filtered["created_at"] >= cutoff]

        stats = compute_stats(filtered)

        if stats["closed"] == 0:
            st.markdown(
                '<div class="panel"><span class="pill pill-warn">NO CLOSED TRADES YET</span>'
                '<br><br>The event log currently holds only entry-side events '
                '(OPENED / TIME_DECAY). Win rate, profit factor and ROI need trades with a '
                'recorded exit and realised P&L. As soon as closed trades start landing in '
                '<code>trade_executions</code>, these fill in automatically.</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Heads-up: no EXIT/CLOSED rows are being written yet. Until the watchdog "
                "records exits back to Supabase, closed-trade stats stay empty here — even "
                "though positions may be closing on Alpaca via OCO."
            )
        else:
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown('<div class="panel-title">Win Rate</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="stat-big neutral">{pct(stats["win_rate"])}</div>', unsafe_allow_html=True)
                st.caption(f'{stats["wins"]}W / {stats["losses"]}L · {stats["closed"]} closed')
            with m2:
                st.markdown('<div class="panel-title">Profit Factor</div>', unsafe_allow_html=True)
                pf = stats["profit_factor"]
                pf_txt = f"{pf:.2f}" if pf is not None else "—"
                pf_cls = "pos" if (pf is not None and pf >= 1) else "neg"
                st.markdown(
                    f'<div class="stat-big {pf_cls}">{pf_txt}</div>',
                    unsafe_allow_html=True,
                )
            with m3:
                st.markdown('<div class="panel-title">Total P&L</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="stat-big {pnl_class(stats["total_pnl"])}">{money(stats["total_pnl"])}</div>',
                    unsafe_allow_html=True,
                )
            with m4:
                st.markdown('<div class="panel-title">Avg Win / Loss</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="stat-big neutral" style="font-size:20px">'
                    f'<span class="pos">{money(stats["avg_win"])}</span> / '
                    f'<span class="neg">{money(stats["avg_loss"])}</span></div>',
                    unsafe_allow_html=True,
                )

# ────────────────────────────────────────────────────────────
# TAB 3: EQUITY — from nautilus_dashboard_log snapshots
# ────────────────────────────────────────────────────────────
with tab_equity:
    eq_df, eq_err = fetch_equity_history(limit=1000)
    if eq_err:
        st.info(f"Equity history unavailable — {eq_err}")
    elif eq_df.empty:
        st.markdown('<div class="panel">No equity snapshots recorded yet.</div>', unsafe_allow_html=True)
    else:
        # Staleness check — the snapshot table was observed stuck; surface it.
        last_log = eq_df["logged_at"].max()
        age = pd.Timestamp.now(tz="UTC") - last_log
        if age > pd.Timedelta(hours=6):
            st.markdown(
                f'<span class="pill pill-stale">SNAPSHOT STALE</span> '
                f'&nbsp;last write {last_log.strftime("%Y-%m-%d %H:%M UTC")} '
                f'({age.days}d {age.seconds // 3600}h ago). '
                f'This tab reflects the snapshot log, not live Alpaca — treat as archival.',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span class="pill pill-live">LIVE SNAPSHOTS</span>', unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq_df["logged_at"], y=eq_df["total_unrealized_pl"],
            mode="lines", name="Unrealized P&L",
            line=dict(color="#2f9e9e", width=2),
            fill="tozeroy", fillcolor="rgba(47,158,158,0.08)",
        ))
        fig.update_layout(
            height=380, margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#7d8590"),
            xaxis=dict(gridcolor="#21262d"), yaxis=dict(gridcolor="#21262d", title="Unrealized P&L ($)"),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Position count over time")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=eq_df["logged_at"], y=eq_df["open_positions_count"],
            mode="lines", line=dict(color="#d9a441", width=1.5, shape="hv"),
        ))
        fig2.update_layout(
            height=200, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#7d8590"),
            xaxis=dict(gridcolor="#21262d"), yaxis=dict(gridcolor="#21262d"),
        )
        st.plotly_chart(fig2, use_container_width=True)

# ────────────────────────────────────────────────────────────
# TAB 4: EVENT LOG — the raw sequence, filterable
# ────────────────────────────────────────────────────────────
with tab_log:
    log_df, log_err = fetch_event_log(limit=200)
    if log_err:
        st.info(f"Event log unavailable — {log_err}")
    elif log_df.empty:
        st.markdown('<div class="panel">No events logged yet.</div>', unsafe_allow_html=True)
    else:
        types = ["All"] + sorted(log_df["event_type"].dropna().unique().tolist())
        chosen = st.selectbox("Event type", types)
        view = log_df if chosen == "All" else log_df[log_df["event_type"] == chosen]

        show = view.copy()
        if "created_at" in show.columns:
            show["created_at"] = show["created_at"].dt.strftime("%Y-%m-%d %H:%M")
        show = show.rename(columns={
            "created_at": "Time", "event_type": "Event",
            "execution_price": "Entry", "exit_price": "Exit",
            "pnl_usd": "P&L $", "pnl_pct": "P&L %",
            "trading_days_open": "Days", "alpaca_order_id": "Order ID",
        })
        st.dataframe(
            show.style.format({
                "Entry": "${:.2f}", "Exit": "${:.2f}",
                "P&L $": "${:,.2f}", "P&L %": "{:.2f}%", "Days": "{:.0f}",
            }, na_rep="—"),
            use_container_width=True, hide_index=True, height=460,
        )

# ── Auto-refresh loop (opt-in) ──────────────────────────────
if auto:
    import time
    time.sleep(REFRESH_SECONDS)
    st.cache_data.clear()
    st.rerun()
