#!/usr/bin/env python
"""
Forecast Hub - Decision Intelligence Dashboard
Interactive interface for exploring collective market consensus from Polymarket and Kalshi.
Designed from first principles for business executives and decision makers.
"""

import os
import sqlite3
import asyncio
import threading
import logging
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from db_manager import DatabaseManager
from pipeline import main as run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "Markets_database.db")

# Thread-safe background sync state
_sync_thread: threading.Thread | None = None
_sync_lock = threading.Lock()


def is_sync_running() -> bool:
    """Check if a background market sync is currently active."""
    global _sync_thread
    return _sync_thread is not None and _sync_thread.is_alive()


def trigger_background_sync() -> bool:
    """Start an asynchronous background thread to fetch market consensus."""
    global _sync_thread
    with _sync_lock:
        if _sync_thread is None or not _sync_thread.is_alive():
            def _worker():
                try:
                    logger.info("Background market sync started.")
                    asyncio.run(run_pipeline())
                    logger.info("Background market sync completed successfully.")
                except Exception as ex:
                    logger.error(f"Background market sync failed: {ex}")

            _sync_thread = threading.Thread(target=_worker, daemon=True)
            _sync_thread.start()
            return True
        return False

st.set_page_config(
    page_title="Forecast Hub",
    page_icon="bar_chart",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = True


def inject_theme_css(dark_mode: bool):
    """Inject CSS for Day (Light) or Night (Dark) mode."""
    if dark_mode:
        theme_css = """
        /* Night Mode Styling - Balanced & Refined Palette */
        header[data-testid="stHeader"] {
            background-color: transparent !important;
        }
        .stApp {
            background-color: #14171f !important;
            color: #e2e8f0 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #10131a !important;
            border-right: 1px solid #222734 !important;
        }
        [data-testid="stSidebar"] * {
            color: #cbd5e1 !important;
        }
        .status-pill {
            background-color: #1b202c !important;
            color: #94a3b8 !important;
            border: 1px solid #293042 !important;
        }
        .forecast-card {
            background: #1b202c !important;
            border: 1px solid #282f40 !important;
            box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.25) !important;
        }
        .forecast-card:hover {
            border-color: #3b455c !important;
            box-shadow: 0 6px 12px -2px rgba(0, 0, 0, 0.35) !important;
        }
        .topic-header {
            background-color: #1b202c !important;
            border-left: 4px solid #3b82f6 !important;
        }
        .topic-title {
            color: #f1f5f9 !important;
        }
        .topic-subtitle {
            color: #8b97ab !important;
        }
        .card-question {
            color: #f1f5f9 !important;
        }
        .card-meta {
            color: #8b97ab !important;
        }
        .metric-box {
            background-color: #13161f !important;
            border: 1px solid #222734 !important;
        }
        .metric-box-title {
            color: #8b97ab !important;
        }
        .metric-box-val {
            color: #f1f5f9 !important;
        }
        .comparison-container {
            background: #1b202c !important;
            border: 1px solid #282f40 !important;
        }
        .comparison-title {
            color: #f1f5f9 !important;
        }
        .badge-kalshi {
            background-color: #0c3325 !important;
            color: #6ee7b7 !important;
            border: 1px solid #13523c !important;
        }
        .badge-polymarket {
            background-color: #152642 !important;
            color: #93c5fd !important;
            border: 1px solid #1e3963 !important;
        }
        .prob-high { color: #34d399 !important; font-weight: 700; }
        .prob-mid { color: #fbbf24 !important; font-weight: 700; }
        .prob-low { color: #f87171 !important; font-weight: 700; }

        /* Form Inputs & Controls */
        input, [data-testid="stTextInput"] input {
            background-color: #1b202c !important;
            color: #f1f5f9 !important;
            border: 1px solid #2d3548 !important;
            border-radius: 6px !important;
        }
        [data-baseweb="select"], 
        [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] > div,
        [data-testid="stMultiSelect"] div[role="combobox"] {
            background-color: #1b202c !important;
            border-color: #2d3548 !important;
            color: #f1f5f9 !important;
        }
        [data-baseweb="popover"], [data-baseweb="menu"], ul[data-baseweb="menu"] {
            background-color: #1b202c !important;
            border: 1px solid #2d3548 !important;
            border-radius: 6px !important;
        }
        li[data-baseweb="menu-item"] {
            background-color: #1b202c !important;
            color: #e2e8f0 !important;
        }
        li[data-baseweb="menu-item"]:hover {
            background-color: #272f42 !important;
        }
        [data-baseweb="tag"] {
            background-color: #272f42 !important;
            border: 1px solid #3b4661 !important;
        }
        [data-baseweb="tag"] span, [data-baseweb="tag"] div {
            color: #cbd5e1 !important;
            background-color: transparent !important;
        }
        [data-baseweb="select"] svg {
            fill: #8b97ab !important;
            color: #8b97ab !important;
        }

        /* Buttons & Link Buttons in Night Mode */
        button, 
        [data-testid="baseButton-secondary"], 
        [data-testid="baseButton-primary"],
        div[data-testid="stLinkButton"] a,
        div[data-testid="stLinkButton"] > a {
            background-color: #242b3b !important;
            color: #e2e8f0 !important;
            border: 1px solid #364057 !important;
            border-radius: 6px !important;
        }
        div[data-testid="stLinkButton"] a * {
            color: #e2e8f0 !important;
        }
        button:hover, 
        [data-testid="baseButton-secondary"]:hover,
        div[data-testid="stLinkButton"] a:hover {
            background-color: #2e374c !important;
            border-color: #485675 !important;
            color: #ffffff !important;
        }

        /* Expander */
        [data-testid="stExpander"] {
            background-color: #161922 !important;
            border: 1px solid #242a38 !important;
            border-radius: 6px !important;
        }
        [data-testid="stExpander"] summary {
            color: #cbd5e1 !important;
        }
        [data-testid="stExpander"] p {
            color: #8b97ab !important;
        }

        /* Category Filter Pills in Night Mode */
        button[data-testid="stBaseButton-pills"],
        button[kind="pills"] {
            background-color: #1b202c !important;
            border: 1px solid #2e374c !important;
            color: #94a3b8 !important;
            border-radius: 9999px !important;
            font-size: 0.8rem !important;
            padding: 0.35rem 0.75rem !important;
            margin-bottom: 0.35rem !important;
            transition: all 0.15s ease !important;
        }
        button[data-testid="stBaseButton-pills"]:hover,
        button[kind="pills"]:hover {
            background-color: #272f42 !important;
            border-color: #3b82f6 !important;
            color: #f1f5f9 !important;
        }
        button[data-testid="stBaseButton-pillsActive"],
        button[kind="pillsActive"] {
            background-color: #2563eb !important;
            border-color: #60a5fa !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            border-radius: 9999px !important;
            font-size: 0.8rem !important;
            padding: 0.35rem 0.75rem !important;
            margin-bottom: 0.35rem !important;
        }
        /* Toggle Switch in Night Mode */
        [data-testid="stToggle"] label, [data-testid="stToggle"] span {
            color: #e2e8f0 !important;
        }
        [data-testid="stToggle"] div[role="switch"] {
            background-color: #242c3d !important;
            border: 1.5px solid #475569 !important;
        }
        [data-testid="stToggle"] div[role="switch"][aria-checked="true"] {
            background-color: #2563eb !important;
            border-color: #60a5fa !important;
        }
        """
    else:
        theme_css = """
        /* Day Mode Styling */
        header[data-testid="stHeader"] {
            background-color: transparent !important;
        }
        .stApp {
            background-color: #f8fafc !important;
            color: #0f172a !important;
        }
        [data-testid="stSidebar"] {
            background-color: #ffffff !important;
            border-right: 1px solid #e2e8f0 !important;
        }
        [data-testid="stSidebar"] * {
            color: #0f172a !important;
        }
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label {
            color: #334155 !important;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: #0f172a !important;
        }
        .status-pill {
            background-color: #f1f5f9 !important;
            color: #334155 !important;
            border: 1px solid #cbd5e1 !important;
        }
        .forecast-card {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
        }
        .forecast-card:hover {
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08) !important;
            border-color: #cbd5e1 !important;
        }
        .topic-header {
            background-color: #f8fafc !important;
            border-left: 4px solid #3b82f6 !important;
        }
        .topic-title {
            color: #0f172a !important;
        }
        .topic-subtitle {
            color: #475569 !important;
        }
        .card-question {
            color: #1e293b !important;
        }
        .card-meta {
            color: #64748b !important;
        }
        .metric-box {
            background-color: #f8fafc !important;
            border: 1px solid #e2e8f0 !important;
        }
        .metric-box-title {
            color: #64748b !important;
        }
        .metric-box-val {
            color: #0f172a !important;
        }
        .comparison-container {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
        }
        .comparison-title {
            color: #0f172a !important;
        }
        .badge-kalshi {
            background-color: #ecfdf5 !important;
            color: #065f46 !important;
            border: 1px solid #a7f3d0 !important;
        }
        .badge-polymarket {
            background-color: #eff6ff !important;
            color: #1e40af !important;
            border: 1px solid #bfdbfe !important;
        }
        .prob-high { color: #166534 !important; font-weight: 700; }
        .prob-mid { color: #854d0e !important; font-weight: 700; }
        .prob-low { color: #991b1b !important; font-weight: 700; }

        /* High-Contrast Toggle Switch in Day Mode */
        [data-testid="stToggle"] label, [data-testid="stToggle"] span {
            color: #0f172a !important;
            font-weight: 500 !important;
        }
        [data-testid="stToggle"] div[role="switch"] {
            background-color: #cbd5e1 !important;
            border: 2px solid #64748b !important;
        }
        [data-testid="stToggle"] div[role="switch"][aria-checked="true"] {
            background-color: #2563eb !important;
            border-color: #1d4ed8 !important;
        }
        [data-testid="stToggle"] div[role="switch"] > div {
            background-color: #ffffff !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3) !important;
        }

        /* Form Inputs in Day Mode */
        input, [data-testid="stTextInput"] input {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
        }
        input:focus, [data-testid="stTextInput"] input:focus {
            border-color: #2563eb !important;
            box-shadow: 0 0 0 1px #2563eb !important;
        }

        /* Radio & Slider in Day Mode */
        [data-testid="stRadio"] label, [data-testid="stRadio"] p {
            color: #0f172a !important;
        }
        [data-testid="stSlider"] label, [data-testid="stSlider"] p, [data-testid="stSlider"] div {
            color: #0f172a !important;
        }

        /* Buttons & Link Buttons in Day Mode */
        button, 
        [data-testid="baseButton-secondary"], 
        [data-testid="baseButton-primary"],
        div[data-testid="stLinkButton"] a,
        div[data-testid="stLinkButton"] > a {
            background-color: #f1f5f9 !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            font-weight: 500 !important;
        }
        div[data-testid="stLinkButton"] a * {
            color: #0f172a !important;
        }
        button:hover, 
        [data-testid="baseButton-secondary"]:hover,
        div[data-testid="stLinkButton"] a:hover {
            background-color: #e2e8f0 !important;
            border-color: #94a3b8 !important;
            color: #000000 !important;
        }

        /* Expander in Day Mode */
        [data-testid="stExpander"] {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 6px !important;
        }
        [data-testid="stExpander"] summary {
            color: #1e293b !important;
        }
        [data-testid="stExpander"] p {
            color: #475569 !important;
        }

        /* Category Filter Pills in Day Mode */
        button[data-testid="stBaseButton-pills"],
        button[kind="pills"] {
            background-color: #f8fafc !important;
            border: 1.5px solid #cbd5e1 !important;
            color: #475569 !important;
            border-radius: 9999px !important;
            font-size: 0.8rem !important;
            padding: 0.35rem 0.75rem !important;
            margin-bottom: 0.35rem !important;
            transition: all 0.15s ease !important;
        }
        button[data-testid="stBaseButton-pills"]:hover,
        button[kind="pills"]:hover {
            background-color: #f1f5f9 !important;
            border-color: #2563eb !important;
            color: #0f172a !important;
        }
        button[data-testid="stBaseButton-pillsActive"],
        button[kind="pillsActive"] {
            background-color: #1d4ed8 !important;
            border-color: #1e40af !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            border-radius: 9999px !important;
            font-size: 0.8rem !important;
            padding: 0.35rem 0.75rem !important;
            margin-bottom: 0.35rem !important;
            box-shadow: 0 0 8px rgba(29, 78, 216, 0.35) !important;
        }
        """

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', -apple-system, sans-serif; }}
    .block-container {{ padding-top: 1.5rem !important; padding-bottom: 2rem !important; max-width: 1350px !important; }}
    h1 {{ font-size: 1.85rem !important; font-weight: 700 !important; margin-bottom: 0.2rem !important; }}
    h2 {{ font-size: 1.35rem !important; font-weight: 600 !important; margin-top: 1rem !important; }}
    h3 {{ font-size: 1.1rem !important; font-weight: 600 !important; }}
    .status-pill {{ display: inline-block; padding: 0.25rem 0.65rem; font-size: 0.8rem; font-weight: 500; border-radius: 9999px; margin-right: 0.5rem; }}
    .forecast-card {{ border-radius: 8px; padding: 1.1rem; margin-bottom: 0.85rem; transition: box-shadow 0.2s ease, border-color 0.2s ease; }}
    .badge-kalshi, .badge-polymarket {{ font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.55rem; border-radius: 4px; text-transform: uppercase; }}
    .metric-box {{ text-align: center; padding: 0.5rem; border-radius: 6px; }}
    .metric-box-title {{ font-size: 0.75rem; font-weight: 500; margin-bottom: 0.2rem; text-transform: uppercase; letter-spacing: 0.025em; }}
    .metric-box-val {{ font-size: 1.15rem; font-weight: 700; }}
    .topic-header {{ padding: 0.65rem 1rem; border-radius: 0 6px 6px 0; margin: 1.25rem 0 0.75rem 0; }}
    .topic-title {{ font-size: 1.15rem; font-weight: 600; margin: 0; }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 0.5rem !important; }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {{ margin-bottom: 0 !important; }}
    [data-testid="stSidebar"] .block-container {{ padding-top: 1rem !important; padding-bottom: 1.5rem !important; }}

    /* Prevent screen dimming and opacity fading during execution or refresh */
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewBlockContainer"],
    section.main,
    .block-container,
    div[data-testid="stVerticalBlock"],
    div[data-testid="stElementContainer"] {{
        opacity: 1 !important;
        transition: none !important;
        filter: none !important;
    }}
    [data-test-script-state="running"] {{
        opacity: 1 !important;
    }}
    div[data-testid="stStatusWidget"] {{
        visibility: hidden !important;
    }}
    {theme_css}
    </style>
    """, unsafe_allow_html=True)

inject_theme_css(st.session_state.dark_mode)


def format_money(val: float | None) -> str:
    """Format dollar amounts into readable plain English."""
    if not val or val <= 0:
        return "$0"
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:.0f}"


def format_date(date_str: str | None) -> str:
    """Format ISO date string to plain English date."""
    if not date_str:
        return "Not specified"
    try:
        clean_str = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%b %d, %Y")
    except Exception:
        return str(date_str)[:10]


def format_relative_refresh(date_str: str | None) -> str:
    """Format ISO timestamp to relative and absolute freshness (e.g. '5m ago (14:32 UTC)')."""
    if not date_str:
        return "Not available"
    try:
        clean_str = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff_sec = max(0, int((now - dt).total_seconds()))

        utc_time = dt.strftime("%H:%M UTC")
        if diff_sec < 60:
            return f"Just now ({utc_time})"
        elif diff_sec < 3600:
            return f"{diff_sec // 60}m ago ({utc_time})"
        elif diff_sec < 86400:
            return f"{diff_sec // 3600}h ago ({utc_time})"
        else:
            return dt.strftime("%b %d, %H:%M UTC")
    except Exception:
        return "Recent"


def is_data_stale(date_str: str | None, max_age_hours: float = 6.0) -> bool:
    """Return True if data timestamp is missing or older than max_age_hours."""
    if not date_str:
        return True
    try:
        clean_str = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff_sec = max(0, int((now - dt).total_seconds()))
        return diff_sec >= max_age_hours * 3600
    except Exception:
        return True


def get_db_connection():
    """Create a SQLite database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=60)
def load_all_markets() -> pd.DataFrame:
    """Load all current active markets from SQLite (cached with 60s TTL)."""
    conn = get_db_connection()
    try:
        query = """
            SELECT id, source, topic_title, question, liquidity, volume, volume_24h,
                   open_interest, probability, category, end_date, rules, url, duplicate_group_id
            FROM markets
            ORDER BY open_interest DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        logger.error(f"Failed to load markets: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def get_metadata(key: str) -> str | None:
    """Retrieve metadata key from SQLite."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def load_watchlist_ids() -> set:
    """Load IDs of watchlisted markets."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT market_id FROM watchlist")
        return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()
    finally:
        conn.close()


def toggle_watchlist(market_id: str, is_in_watchlist: bool):
    """Add or remove market from watchlist."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if is_in_watchlist:
            cur.execute("DELETE FROM watchlist WHERE market_id = ?", (market_id,))
        else:
            cur.execute("INSERT OR IGNORE INTO watchlist (market_id) VALUES (?)", (market_id,))
        conn.commit()
    finally:
        conn.close()


@st.cache_resource
def ensure_db_initialized() -> bool:
    """Initialize database schema once per process."""
    db = DatabaseManager(DATABASE_PATH)
    db.connect()
    db.init_schema()
    db.close()
    return True


ensure_db_initialized()


def get_market_count() -> int:
    """Quick market count check."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM markets")
        row = cur.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


# ============================================================================
# INITIALIZATION & COLD-START LOADING UX
# ============================================================================

market_count = get_market_count()


# If cold start (no data exists), display loading screen and fetch immediately
if market_count == 0:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align: center; padding: 2.5rem; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);'>
            <h2 style='margin-bottom: 0.5rem;'>Initializing Forecast Hub</h2>
            <p style='color: #64748b; font-size: 0.95rem; margin-bottom: 1.5rem;'>
                Connecting to Polymarket and Kalshi APIs to ingest verified prediction markets and establish cross-platform consensus...
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.spinner("Fetching active forecast markets over HTTP/2..."):
            try:
                exit_code = asyncio.run(run_pipeline())
                if exit_code == 0:
                    st.success("Ingestion complete. Loading dashboard...")
                    st.rerun()
                else:
                    st.error("Failed to complete initial market fetch. Please check network connection.")
            except Exception as e:
                st.error(f"Startup error: {e}")
        st.stop()


# ============================================================================
# MAIN APPLICATION
# ============================================================================

df = load_all_markets()
last_refresh = get_metadata("last_refresh")
watchlist_ids = load_watchlist_ids()

# Automatic background refresh if data already exists and is older than 6 hours
if market_count > 0 and is_data_stale(last_refresh, max_age_hours=6.0):
    if trigger_background_sync():
        logger.info("Market data is older than 6 hours. Background sync triggered silently.")

# Top Header & Command Bar
refresh_str = format_relative_refresh(last_refresh)

top_hdr_col, top_actions_col = st.columns([3, 1.4])
with top_hdr_col:
    title_color = "#f8fafc" if st.session_state.dark_mode else "#0f172a"
    badge_bg = "#1e293b" if st.session_state.dark_mode else "#eff6ff"
    badge_color = "#38bdf8" if st.session_state.dark_mode else "#1d4ed8"
    badge_border = "#334155" if st.session_state.dark_mode else "#bfdbfe"
    sub_color = "#94a3b8" if st.session_state.dark_mode else "#64748b"

    st.markdown(f"""
    <div style='display: flex; align-items: center; gap: 0.85rem; margin-top: -0.4rem;'>
        <h1 style='color: {title_color}; margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.025em;'>Forecast Hub</h1>
        <span style='font-size: 0.72rem; font-weight: 700; padding: 0.25rem 0.65rem; border-radius: 9999px; background: {badge_bg}; color: {badge_color}; border: 1px solid {badge_border}; letter-spacing: 0.05em; display: inline-flex; align-items: center;'>
            <span style='width: 7px; height: 7px; border-radius: 50%; background: #22c55e; margin-right: 6px; box-shadow: 0 0 6px #22c55e;'></span>LIVE INTELLIGENCE
        </span>
    </div>
    <p style='color: {sub_color}; font-size: 0.92rem; margin-top: 0.25rem; margin-bottom: 0.85rem;'>
        Institutional prediction market consensus synthesized from Polymarket and Kalshi.
    </p>
    """, unsafe_allow_html=True)

with top_actions_col:
    st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
    act1, act2 = st.columns([1.4, 1])
    with act1:
        if st.button("↻ Refresh Data", key="top_refresh_btn", use_container_width=True):
            st.cache_data.clear()
            if trigger_background_sync():
                st.toast("Syncing latest market consensus in background...", icon="↻")
            else:
                st.toast("Sync already running in background...", icon="⏳")
    with act2:
        mode_label = "🌙 Dark" if st.session_state.dark_mode else "☀️ Light"
        mode_help = "Switch to Light Mode" if st.session_state.dark_mode else "Switch to Dark Mode"
        if st.button(mode_label, key="theme_toggle_btn", help=mode_help, use_container_width=True):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.rerun()
    time_color = "#64748b" if st.session_state.dark_mode else "#94a3b8"
    sync_status = " <span style='color: #38bdf8;'>(Syncing...)</span>" if is_sync_running() else ""
    st.markdown(f"<div style='text-align: right; font-size: 0.78rem; color: {time_color}; margin-top: -0.2rem;'>Updated: <b>{refresh_str}</b>{sync_status}</div>", unsafe_allow_html=True)

# Status Bar
total_volume = df['volume'].sum() if not df.empty else 0
total_oi = df['open_interest'].sum() if not df.empty else 0
unique_topics = df['topic_title'].nunique() if not df.empty else 0

sync_pill = "<span class='status-pill' style='background-color: #0284c7 !important; color: #ffffff !important; font-weight: 600;'>↻ Syncing in background</span>" if is_sync_running() else ""

st.markdown(f"""
<div style='margin-bottom: 1.25rem;'>
    <span class='status-pill'>Active Markets: <b>{len(df):,}</b></span>
    <span class='status-pill'>Event Topics: <b>{unique_topics:,}</b></span>
    <span class='status-pill'>Total Market Activity: <b>{format_money(total_oi)}</b></span>
    <span class='status-pill'>Last Refreshed: <b>{refresh_str}</b></span>
    {sync_pill}
</div>
""", unsafe_allow_html=True)

# Prominent Search Bar
search_query = st.text_input(
    "Search",
    placeholder="🔍 Search topics, questions, rules, or tickers (e.g. Fed rate cut, Nvidia, inflation, recession)...",
    label_visibility="collapsed",
    key="search_input"
)


# ============================================================================
# SIDEBAR FILTERS (Compact & Zero-Scroll)
# ============================================================================

with st.sidebar:
    st.markdown("### Decision Filters")

    # Dynamic facet counts calculated from active baseline criteria
    curr_min_prob = st.session_state.get("filter_min_prob", 0)
    curr_min_oi = st.session_state.get("filter_min_oi", 10_000)
    curr_platform = st.session_state.get("filter_platform", "Both Platforms")
    curr_search = st.session_state.get("search_input", "")

    facet_df = df.copy()
    if curr_min_prob > 0:
        facet_df = facet_df[facet_df['probability'].fillna(0) >= curr_min_prob]
    if curr_min_oi > 0:
        facet_df = facet_df[facet_df['open_interest'].fillna(0) >= curr_min_oi]
    if curr_platform == "Polymarket Only":
        facet_df = facet_df[facet_df['source'] == 'polymarket']
    elif curr_platform == "Kalshi Only":
        facet_df = facet_df[facet_df['source'] == 'kalshi']
    if curr_search and curr_search.strip():
        search_tokens = curr_search.strip().lower().split()
        search_corpus = (
            facet_df['question'].fillna('') + ' ' +
            facet_df['topic_title'].fillna('') + ' ' +
            facet_df['category'].fillna('') + ' ' +
            facet_df['rules'].fillna('')
        ).str.lower()
        search_mask = pd.Series(True, index=facet_df.index)
        for token in search_tokens:
            search_mask &= search_corpus.str.contains(token, regex=False)
        facet_df = facet_df[search_mask]

    cat_counts = facet_df['category'].value_counts().to_dict() if not facet_df.empty else {}
    all_categories = sorted([c for c in df['category'].dropna().unique() if c])

    CAT_ICONS = {
        "Economy & Macro": "📈",
        "Finance & Markets": "💰",
        "Politics & Governance": "🏛️",
        "Companies & Business": "🏢",
        "Technology & Science": "🔬",
        "Global Affairs": "🌐"
    }

    st.markdown("<p style='font-size: 0.85rem; font-weight: 600; margin-bottom: 0.35rem; margin-top: 0.2rem;'>Categories</p>", unsafe_allow_html=True)
    selected_pills = st.pills(
        "Categories",
        options=all_categories,
        selection_mode="multi",
        label_visibility="collapsed",
        format_func=lambda cat: f"{CAT_ICONS.get(cat, '📁')} {cat} ({cat_counts.get(cat, 0):,})",
        key="filter_categories",
        help="Click to isolate specific sectors. All active when none selected."
    )

    selected_categories = selected_pills if selected_pills else all_categories

    # Minimum likelihood
    min_prob = st.slider("Minimum Likelihood", min_value=0, max_value=100, value=0, format="%d%%", key="filter_min_prob")

    # Minimum capital active
    min_oi = st.slider(
        "Minimum Money Placed",
        min_value=0,
        max_value=1_000_000,
        value=10_000,
        step=10_000,
        format="$%d",
        key="filter_min_oi",
        help="Filter for contracts with verifiable capital commitment"
    )

    platform_filter = st.radio(
        "Platforms",
        options=["Both Platforms", "Polymarket Only", "Kalshi Only"],
        index=0,
        key="filter_platform"
    )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    if st.button("↺ Reset Filters", key="reset_filters_btn", help="Reset all filters to defaults", use_container_width=True):
        for k in ["filter_categories", "filter_min_prob", "filter_min_oi", "filter_platform", "search_input"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()




# Apply filters
filtered_df = df.copy()

# Filter by selected categories (deselecting all correctly filters to empty)
filtered_df = filtered_df[filtered_df['category'].isin(selected_categories)]


if min_prob > 0:
    filtered_df = filtered_df[filtered_df['probability'].fillna(0) >= min_prob]

if min_oi > 0:
    filtered_df = filtered_df[filtered_df['open_interest'].fillna(0) >= min_oi]

if platform_filter == "Polymarket Only":
    filtered_df = filtered_df[filtered_df['source'] == 'polymarket']
elif platform_filter == "Kalshi Only":
    filtered_df = filtered_df[filtered_df['source'] == 'kalshi']

# Tokenized multi-term search across questions, topics, categories, and settlement rules
if search_query and search_query.strip():
    tokens = search_query.strip().lower().split()
    search_corpus = (
        filtered_df['question'].fillna('') + ' ' +
        filtered_df['topic_title'].fillna('') + ' ' +
        filtered_df['category'].fillna('') + ' ' +
        filtered_df['rules'].fillna('')
    ).str.lower()
    
    match_mask = pd.Series(True, index=filtered_df.index)
    for token in tokens:
        match_mask &= search_corpus.str.contains(token, regex=False)
    filtered_df = filtered_df[match_mask]



# ============================================================================
# MAIN TABS (Two-Tier View, Cross-Platform Comparison, Watchlist)
# ============================================================================

tab_topics, tab_comparison, tab_watchlist = st.tabs([
    "Forecasts by Event Topic",
    "Cross-Platform Consensus",
    "Watchlist"
])


def render_market_item(row, prefix: str = "", show_toggle: bool = True):
    """Render a single market prediction cleanly with plain English terms."""
    m_id = row['id']
    source = row.get('source', 'polymarket').lower()
    prob = row.get('probability')
    vol = row.get('volume', 0)
    oi = row.get('open_interest', 0)
    question = row.get('question') or "Untitled Market"
    target_date = format_date(row.get('end_date'))
    rules = row.get('rules') or ""
    url = row.get('url') or ""
    is_saved = m_id in watchlist_ids

    badge_html = f"<span class='badge-{source}'>{source}</span>"
    
    # Likelihood color class
    prob_display = f"{prob:.1f}%" if prob is not None else "Pending"
    prob_class = "prob-high" if prob and prob >= 60 else ("prob-mid" if prob and prob >= 30 else "prob-low")

    st.markdown(f"""
    <div class='forecast-card'>
        <div style='display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.6rem;'>
            <div style='flex: 1;'>
                {badge_html}
                <span class='card-meta' style='font-size: 0.8rem; margin-left: 0.5rem;'>Target Date: <b>{target_date}</b></span>
                <div class='card-question' style='font-size: 1rem; font-weight: 600; margin-top: 0.4rem;'>{question}</div>
            </div>
            <div style='text-align: right; min-width: 110px;'>
                <div class='card-meta' style='font-size: 0.75rem; font-weight: 500; text-transform: uppercase;'>Likelihood</div>
                <div class='{prob_class}' style='font-size: 1.45rem;'>{prob_display}</div>
            </div>
        </div>
        <div style='display: flex; gap: 1rem; margin-top: 0.5rem;'>
            <div class='metric-box' style='flex: 1;'>
                <div class='metric-box-title'>Total Money Placed</div>
                <div class='metric-box-val'>{format_money(oi)}</div>
            </div>
            <div class='metric-box' style='flex: 1;'>
                <div class='metric-box-title'>Trading Volume</div>
                <div class='metric-box-val'>{format_money(vol)}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Action bar below card (Direct URL link, watchlist toggle, rules)
    act_col1, act_col2 = st.columns([1, 1])
    with act_col1:
        if url:
            st.link_button("↗ View Contract", url, use_container_width=True)
    with act_col2:
        btn_label = "★ In Watchlist" if is_saved else "☆ Add to Watchlist"
        if st.button(btn_label, key=f"{prefix}_wl_{m_id}", use_container_width=True):
            toggle_watchlist(m_id, is_saved)
            st.rerun()

    if rules:
        with st.expander("Decision & Settlement Rules"):
            st.markdown(f"<p style='font-size: 0.82rem; line-height: 1.4; opacity: 0.85;'>{rules}</p>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# TAB 1: Forecasts by Event Topic (Two-Tier Parent/Child)
# ----------------------------------------------------------------------------

with tab_topics:
    if filtered_df.empty:
        st.info("No forecasts match your selected filters. Adjust your criteria in the sidebar.")
    else:
        # Group by topic title
        grouped = filtered_df.groupby('topic_title')
        
        # Sort topics by total money placed
        topic_order = filtered_df.groupby('topic_title')['open_interest'].sum().sort_values(ascending=False).index

        for topic in topic_order:
            topic_markets = grouped.get_group(topic)
            topic_oi = topic_markets['open_interest'].sum()
            topic_count = len(topic_markets)
            
            st.markdown(f"""
            <div class='topic-header'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <div class='topic-title'>{topic}</div>
                    <div style='font-size: 0.82rem; color: #475569;'>
                        <b>{topic_count}</b> related contract{'s' if topic_count > 1 else ''} | Total Size: <b>{format_money(topic_oi)}</b>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            for _, row in topic_markets.iterrows():
                render_market_item(row, prefix="topic")


# ----------------------------------------------------------------------------
# TAB 2: Cross-Platform Consensus (Side-by-side comparison)
# ----------------------------------------------------------------------------

with tab_comparison:
    st.markdown("### Cross-Platform Consensus")
    st.markdown("<p style='color: #64748b; font-size: 0.9rem;'>Direct side-by-side comparison where both Polymarket and Kalshi track the exact same target event.</p>", unsafe_allow_html=True)

    matched_groups = filtered_df[filtered_df['duplicate_group_id'].notna()]['duplicate_group_id'].unique()

    if len(matched_groups) == 0:
        st.info("No matching cross-platform contracts currently meet your active filter criteria.")
    else:
        for gid in matched_groups:
            pair = filtered_df[filtered_df['duplicate_group_id'] == gid]
            if len(pair) < 2:
                continue

            pm_row = pair[pair['source'] == 'polymarket']
            k_row = pair[pair['source'] == 'kalshi']

            if pm_row.empty or k_row.empty:
                continue

            pm_item = pm_row.iloc[0]
            k_item = k_row.iloc[0]

            pm_prob = pm_item.get('probability') or 0
            k_prob = k_item.get('probability') or 0
            diff = abs(pm_prob - k_prob)
            avg_prob = (pm_prob + k_prob) / 2.0

            consensus_status = "Strong Agreement" if diff <= 3.0 else ("Moderate Agreement" if diff <= 8.0 else "Platform Divergence")
            status_color = "#22c55e" if diff <= 3.0 else ("#f59e0b" if diff <= 8.0 else "#ef4444")
            card_bg = "#1b202c" if st.session_state.dark_mode else "#ffffff"
            card_border = "#282f40" if st.session_state.dark_mode else "#e2e8f0"
            q_color = "#f8fafc" if st.session_state.dark_mode else "#0f172a"
            tag_bg = "#242c3d" if st.session_state.dark_mode else "#f8fafc"

            st.markdown(f"""
            <div style='border: 1px solid {card_border}; border-radius: 8px; padding: 0.85rem 1rem; margin-bottom: 0.85rem; background: {card_bg};'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <div style='font-size: 1.05rem; font-weight: 600; color: {q_color};'>{pm_item['question']}</div>
                    <span style='color: {status_color}; font-size: 0.82rem; font-weight: 700; padding: 0.25rem 0.65rem; background: {tag_bg}; border-radius: 6px; border: 1px solid {card_border};'>
                        {consensus_status} (Δ {diff:.1f}%)
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                render_market_item(pm_item, prefix=f"comp_{gid}_pm")
            with col2:
                render_market_item(k_item, prefix=f"comp_{gid}_k")


# ----------------------------------------------------------------------------
# TAB 3: Watchlist
# ----------------------------------------------------------------------------

with tab_watchlist:
    st.markdown("### Saved Watchlist")
    st.markdown("<p style='color: #64748b; font-size: 0.9rem;'>Contracts pinned for ongoing strategic monitoring.</p>", unsafe_allow_html=True)

    if not watchlist_ids:
        st.info("Your watchlist is currently empty. Click '☆ Add to Watchlist' on any forecast card to pin it here.")
    else:
        watchlisted_df = df[df['id'].isin(watchlist_ids)]
        if watchlisted_df.empty:
            st.info("Saved markets are no longer active.")
        else:
            for _, row in watchlisted_df.iterrows():
                render_market_item(row, prefix="wl")
