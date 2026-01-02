#!/usr/bin/env python
"""Polymarket BI Dashboard - Streamlit interface for filtering and exploring markets from both Polymarket and Kalshi.
Displays source attribution (color-coded badges) and allows filtering by duplicate status (cross-platform matches).
Watchlist saved to database for persistence across sessions."""

import os
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
import logging
from tz_utils import now_utc
from db_utils import retry_on_db_lock
from db_manager import DatabaseManager
import json

st.set_page_config(
    page_title="Polymarket BI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "polymarket_bi.db")

# Cache watchlist in session to avoid repeated DB calls
if 'watchlist_cache' not in st.session_state:
    st.session_state.watchlist_cache = None
    st.session_state.watchlist_cache_time = None

def format_oi(oi: float) -> str:
    """Format open interest/liquidity: K unless >= 1M."""
    if oi is None or oi == 0:
        return "$0"
    return f"${oi/1_000_000:.1f}M" if oi >= 1_000_000 else f"${oi/1_000:.0f}K"


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def load_markets():
    """Load markets from database including source and duplicate_group_id.
    Returns DataFrame with all market fields; source='polymarket'|'kalshi' identifies platform.
    duplicate_group_id links markets that appear on both platforms (based on 85% question similarity)."""
    conn = get_db()
    try:
        query = """
        SELECT id, question, volume, volume_24h, open_interest, probability, category, source, duplicate_group_id
        FROM markets
        ORDER BY open_interest DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    except sqlite3.Error as e:
        logger.error(f"Failed to load markets: {e}")
        st.error(f"Database error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_last_refresh_time():
    """Get last refresh timestamp."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = ? ORDER BY updated_at DESC LIMIT 1", ("last_refresh",))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def load_watchlist():
    """Load user's watchlist. Cached in session to avoid repeated DB calls."""
    # Check session cache
    if st.session_state.watchlist_cache is not None:
        return st.session_state.watchlist_cache
    
    conn = get_db()
    try:
        query = "SELECT m.id FROM markets m INNER JOIN watchlist w ON m.id = w.market_id"
        df = pd.read_sql_query(query, conn)
        result = set(df['id'].tolist()) if len(df) > 0 else set()
        st.session_state.watchlist_cache = result
        return result
    except sqlite3.Error:
        st.session_state.watchlist_cache = set()
        return set()
    finally:
        conn.close()


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def add_to_watchlist(market_id: str):
    """Add to watchlist."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO watchlist (market_id) VALUES (?)", (market_id,))
        conn.commit()
        st.session_state.watchlist_cache = None  # Clear cache
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def remove_from_watchlist(market_id: str):
    """Remove from watchlist."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE market_id = ?", (market_id,))
        conn.commit()
        st.session_state.watchlist_cache = None  # Clear cache
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_refresh_status():
    """Get human-readable refresh status."""
    last_refresh = get_last_refresh_time()
    if not last_refresh:
        return "Never refreshed", "red"
    
    try:
        last_dt = pd.to_datetime(last_refresh, utc=True).to_pydatetime()
        delta = now_utc() - last_dt
        minutes_ago = int(delta.total_seconds() / 60)
        
        if minutes_ago < 1:
            return "Just updated", "green"
        elif minutes_ago < 60:
            return f"Updated {minutes_ago}m ago", "green"
        else:
            hours_ago = minutes_ago // 60
            return f"Updated {hours_ago}h ago", "orange" if hours_ago < 7 else "red"
    except Exception:
        return "Unknown", "gray"


# ============================================================================
# MAIN DASHBOARD
# ============================================================================

# Load data
df = load_markets()

if len(df) == 0:
    st.warning("⚠️ No data available. Run: `python main.py`")
    st.stop()

# Sidebar filters
with st.sidebar:
    st.header("🎚️ Filters")
    st.divider()
    
    # Categories
    available_categories = sorted(df['category'].unique().tolist()) if 'category' in df.columns else []
    selected_categories = st.multiselect("Market Categories", available_categories, default=[])
    st.divider()
    
    # Watchlist
    show_favorites_only = st.checkbox("Show Favorites Only", value=False)
    st.divider()
    
    # Overlapping markets (different terminology, same feature)
    show_overlaps_only = st.checkbox("Show Overlapping Markets Only (appear on both platforms)", value=False)
    st.divider()
    
    # OI threshold
    max_oi = int(df['open_interest'].max()) if len(df) > 0 else 1_000_000_000
    min_open_interest = st.slider("Minimum OI ($)", 50_000, max_oi, 50_000, format="$%d")
    st.divider()
    
    # Probability range
    prob_min, prob_max = st.slider("Probability Range (%)", 0, 100, (0, 100))
    st.divider()

# Define sort options (moved to main page)
sort_options = {
    "Open Interest (High to Low)": ("open_interest", False),
    "Open Interest (Low to High)": ("open_interest", True),
    "24h Volume (High to Low)": ("volume_24h", False),
    "24h Volume (Low to High)": ("volume_24h", True),
    "Total Volume (High to Low)": ("volume", False),
    "Total Volume (Low to High)": ("volume", True),
    "Liquidity (High to Low)": ("liquidity", False),
    "Liquidity (Low to High)": ("liquidity", True),
    "Probability (High to Low)": ("probability", False),
    "Probability (Low to High)": ("probability", True),
}

# Apply filters
df_filtered = df[
    (df['open_interest'] >= min_open_interest) &
    (df['probability'] >= prob_min) &
    (df['probability'] <= prob_max)
].copy()

if selected_categories:
    df_filtered = df_filtered[df_filtered['category'].isin(selected_categories)]

# Watchlist filter
if show_favorites_only:
    user_watchlist = load_watchlist()
    df_filtered = df_filtered[df_filtered['id'].isin(user_watchlist)]

# Overlaps filter
if show_overlaps_only:
    df_filtered = df_filtered[df_filtered['duplicate_group_id'].notna()]

# Main content
st.title("Business Prediction Market Intelligence")
st.markdown("**Real-time consensus for strategic decision-making**")

col_refresh, col_status = st.columns([2, 3])
with col_refresh:
    if st.button("Refresh Data", use_container_width=True):
        import asyncio
        from pipeline import find_duplicate_groups
        from fetchers.polymarket_api import fetch_all_markets as fetch_polymarket
        from fetchers.kalshi_api import fetch_all_markets as fetch_kalshi
        
        with st.spinner("Fetching data..."):
            try:
                async def fetch_both():
                    pm, k = await asyncio.gather(fetch_polymarket(), fetch_kalshi(), return_exceptions=True)
                    pm = pm if not isinstance(pm, Exception) else []
                    k = k if not isinstance(k, Exception) else []
                    for m in pm:
                        m['source'] = 'polymarket'
                    for m in k:
                        m['source'] = 'kalshi'
                    return pm + k
                
                markets = asyncio.run(fetch_both())
                if markets:
                    db = DatabaseManager()
                    db.connect()
                    db.init_schema()
                    dup_groups = find_duplicate_groups(markets)
                    db.insert_markets(markets, dup_groups)
                    db.close()
                    st.success(f"✅ {len(markets)} markets updated")
                    st.rerun()
                else:
                    st.error("No markets fetched")
            except Exception as e:
                st.error(f"Failed: {e}")

with col_status:
    refresh_status, _ = get_refresh_status()
    st.markdown(f"**{refresh_status}**")

st.divider()

# Metrics (filter-aware)
col1, col2, col3, col4 = st.columns(4)
with col1:
    high_consensus = ((df_filtered['probability'] > 70) | (df_filtered['probability'] < 30)).sum()
    st.metric("High Conviction", high_consensus)
with col2:
    overlapping = df_filtered[df_filtered['duplicate_group_id'].notna()].shape[0]
    st.metric("Overlapping Markets", overlapping)
with col3:
    high_liquidity = (df_filtered['liquidity'] > df_filtered['liquidity'].quantile(0.75)).sum() if 'liquidity' in df_filtered.columns else 0
    st.metric("High Liquidity", high_liquidity)
with col4:
    st.metric("Total Markets", len(df_filtered))

st.divider()

# Sorting and pagination controls
col_sort, col_view = st.columns([2, 1])
with col_sort:
    sort_by_label = st.selectbox("Sort By", list(sort_options.keys()), index=0)
    sort_column, sort_ascending = sort_options[sort_by_label]

# Pagination
if 'markets_per_page' not in st.session_state:
    st.session_state.markets_per_page = 20
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

st.divider()

# Market list
df_filtered_sorted = df_filtered.sort_values(sort_column, ascending=sort_ascending).reset_index(drop=True)
total_markets = len(df_filtered_sorted)

# Load watchlist once for all cards
user_watchlist = load_watchlist()

# Check if showing overlaps only
showing_overlaps_only = show_overlaps_only and len(df_filtered_sorted) > 0

if showing_overlaps_only:
    # Filter to ONLY groups with markets from BOTH platforms (true overlaps)
    # First, exclude markets with no overlap group ID
    df_with_overlaps = df_filtered_sorted[pd.notna(df_filtered_sorted['duplicate_group_id'])]
    
    if len(df_with_overlaps) == 0:
        st.info("No overlapping markets found.")
    else:
        grouped = df_with_overlaps.groupby('duplicate_group_id')
        true_overlaps = []
        for group_id, group_markets in grouped:
            sources = group_markets['source'].unique()
            # Only include groups with markets from BOTH Polymarket AND Kalshi
            if len(sources) >= 2 and 'polymarket' in [s.lower() for s in sources] and 'kalshi' in [s.lower() for s in sources]:
                true_overlaps.append(group_id)
        
        if len(true_overlaps) == 0:
            st.info("No overlapping markets found between platforms.")
        else:
            # Filter dataframe to only true overlaps
            df_overlaps_only = df_with_overlaps[df_with_overlaps['duplicate_group_id'].isin(true_overlaps)]
            grouped = df_overlaps_only.groupby('duplicate_group_id')
            total_groups = len(grouped)
            
            # Pagination for groups
            total_pages = (total_groups + st.session_state.markets_per_page - 1) // st.session_state.markets_per_page
            start_idx = (st.session_state.current_page - 1) * st.session_state.markets_per_page
            end_idx = min(start_idx + st.session_state.markets_per_page, total_groups)
            
            st.subheader(f"Overlapping Markets ({total_groups} groups) | Page {st.session_state.current_page}/{total_pages}")
            
            # Display groups for current page
            group_list = list(grouped.groups.keys())
            for group_idx in range(start_idx, end_idx):
                group_id = group_list[group_idx]
                group_markets = grouped.get_group(group_id).reset_index(drop=True)
                
                with st.container(border=True):
                    # Side-by-side comparison of platforms (with questions)
                    platform_cols = st.columns(len(group_markets))
                    
                    for col_idx, (_, market) in enumerate(group_markets.iterrows()):
                        with platform_cols[col_idx]:
                            source = market['source'].capitalize()
                            source_color = "#f97316" if source == "Kalshi" else "#3b82f6"
                            
                            # Platform header
                            st.markdown(f"<div style='background-color: {source_color}; color: white; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold;'>{source}</div>", unsafe_allow_html=True)
                            
                            # Question text
                            st.caption(f"**{market['question']}**")
                            st.divider()
                            
                            # Probability
                            prob = market['probability']
                            prob_color = "#2ecc71" if prob >= 50 else "#e74c3c"
                            st.markdown(f"<div style='background-color: {prob_color}; color: white; padding: 8px; border-radius: 3px; text-align: center; margin: 8px 0; font-weight: bold;'>{prob:.0f}%</div>", unsafe_allow_html=True)
                            
                            # Details
                            st.caption(f"OI: {format_oi(market['open_interest'])}")
                            st.caption(f"24h Vol: {format_oi(market['volume_24h'])}")
                            liq = market.get('liquidity', 0)
                            st.caption(f"Liq: {format_oi(liq) if liq else '$0'}")
                            
                            # Watchlist button
                            in_watchlist = market['id'] in user_watchlist
                            if in_watchlist:
                                if st.button("❤️", key=f"watch_{market['id']}", help="Remove from watchlist"):
                                    remove_from_watchlist(market['id'])
                                    st.rerun()
                            else:
                                if st.button("🤍", key=f"watch_{market['id']}", help="Add to watchlist"):
                                    add_to_watchlist(market['id'])
                                    st.rerun()
            
            # Pagination controls for groups
            st.divider()
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("← Previous", disabled=(st.session_state.current_page == 1)):
                    st.session_state.current_page -= 1
                    st.rerun()
            with col_page:
                page_num = st.number_input("Go to page", min_value=1, max_value=total_pages, value=st.session_state.current_page)
                st.session_state.current_page = page_num
            with col_next:
                if st.button("Next →", disabled=(st.session_state.current_page == total_pages)):
                    st.session_state.current_page += 1
                    st.rerun()

else:
    # Normal view: show each market individually
    # Normal view: show each market individually
    total_pages = (total_markets + st.session_state.markets_per_page - 1) // st.session_state.markets_per_page
    start_idx = (st.session_state.current_page - 1) * st.session_state.markets_per_page
    end_idx = min(start_idx + st.session_state.markets_per_page, total_markets)
    
    st.subheader(f"Markets ({total_markets}) | Page {st.session_state.current_page}/{total_pages}")
    
    # Display markets for current page
    for idx in range(start_idx, end_idx):
        row = df_filtered_sorted.iloc[idx]
        in_watchlist = row['id'] in user_watchlist
        
        # Check if market has overlaps
        has_overlaps = pd.notna(row['duplicate_group_id'])
        
        with st.container(border=True):
            # Header: Probability + Question + Overlap indicator
            col_prob, col_q, col_overlap = st.columns([0.6, 3.5, 0.7])
            
            with col_prob:
                prob = row['probability']
                color = "#2ecc71" if prob >= 50 else "#e74c3c"
                st.markdown(f"<div style='background-color: {color}; padding: 8px; border-radius: 4px; text-align: center; color: white; font-weight: bold;'>{prob:.0f}%</div>", unsafe_allow_html=True)
            
            with col_q:
                st.caption(row['question'])  # Full question, no truncation
            
            with col_overlap:
                if has_overlaps:
                    st.markdown(f"<div style='background-color: #9333ea; color: white; padding: 4px 8px; border-radius: 3px; font-size: 11px; text-align: center; font-weight: bold;'>🔗 Overlap</div>", unsafe_allow_html=True)
            
            # Details row
            col_source, col_vol_24h, col_oi, col_liq, col_watch = st.columns([0.9, 1, 1, 1, 0.7])
            
            with col_source:
                source = row['source'].capitalize() if pd.notna(row['source']) else "Unknown"
                source_color = "#f97316" if source == "Kalshi" else "#3b82f6"
                st.markdown(f"<div style='background-color: {source_color}; color: white; padding: 4px 8px; border-radius: 3px; font-size: 11px; text-align: center;'>{source}</div>", unsafe_allow_html=True)
            
            with col_vol_24h:
                st.caption(f"24h Vol: {format_oi(row['volume_24h'])}")
            
            with col_oi:
                st.caption(f"OI: {format_oi(row['open_interest'])}")
            
            with col_liq:
                liq = row.get('liquidity', 0)
                st.caption(f"Liq: {format_oi(liq) if liq else '$0'}")
            
            with col_watch:
                if in_watchlist:
                    if st.button("❤️", key=f"watch_{row['id']}", help="Remove from watchlist"):
                        remove_from_watchlist(row['id'])
                        st.rerun()
                else:
                    if st.button("🤍", key=f"watch_{row['id']}", help="Add to watchlist"):
                        add_to_watchlist(row['id'])
                        st.rerun()
    
    # Pagination controls
    st.divider()
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Previous", disabled=(st.session_state.current_page == 1)):
            st.session_state.current_page -= 1
            st.rerun()
    with col_page:
        page_num = st.number_input("Go to page", min_value=1, max_value=total_pages, value=st.session_state.current_page)
        st.session_state.current_page = page_num
    with col_next:
        if st.button("Next →", disabled=(st.session_state.current_page == total_pages)):
            st.session_state.current_page += 1
            st.rerun()

