#!/usr/bin/env python
"""Business Intelligence Dashboard - Streamlit interface for filtering and exploring markets from both Polymarket and Kalshi.
Displays source attribution (color-coded badges) and allows filtering by duplicate status (cross-platform matches).
Watchlist saved to database for persistence across sessions."""

import os
import sqlite3
import pandas as pd
import streamlit as st
import logging
from tz_utils import now_utc
from db_utils import retry_on_db_lock
from db_manager import DatabaseManager

st.set_page_config(
    page_title="Forecast Hub",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Compact CSS to reduce spacing
st.markdown("""
<style>
/* Remove all padding/margins */
.block-container { padding-top: 2rem !important; padding-bottom: 0 !important; margin: 0 !important; }
.main { padding-top: 0 !important; }

/* Headings - no space */
h1, h2, h3, h4, h5, h6 { margin: 0 !important; padding: 0.2rem 0 !important; line-height: 1.2 !important; }

/* Sidebar extreme compression */
[data-testid="stSidebar"] { font-size: 0.8rem; }
[data-testid="stSidebar"] h2 { margin: 0 !important; padding: 0 !important; font-size: 0.95rem !important; }
[data-testid="stSidebar"] label { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stCheckbox, [data-testid="stSidebar"] .stRadio { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stSlider { margin: 0.15rem 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stExpander { margin: 0 !important; padding: 0 !important; }

/* Remove element container padding */
.element-container { margin: 0 !important; padding: 0 !important; }
.stDivider { margin: 0.1rem 0 !important; }

/* Market cards: defined borders */
[data-testid="stContainer"] { 
  border: 1.5px solid #e5e7eb !important; 
  border-radius: 6px !important; 
  padding: 0.6rem !important; 
  margin: 0.3rem 0 !important; 
}
</style>
""", unsafe_allow_html=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "Markets_database.db")

# Theme colors
COLORS = {
    "kalshi": "#10b981",  # Green - Kalshi brand color
    "polymarket": "#3b82f6",  # Blue - Polymarket brand color
    "probability_high": "#2ecc71",
    "probability_low": "#e74c3c",
    "liquidity": "#f59e0b",
    "overlaps": "#9333ea",
    "metric_value": "#64748b",
    "metric_label": "#475569",
}

# Probability color bands (10% increments, red to green)
PROBABILITY_BANDS = [
    (10, "#991b1b"),   # 0-10%: dark red
    (20, "#dc2626"),   # 10-20%: red
    (30, "#ea580c"),   # 20-30%: orange-red
    (40, "#ea8317"),   # 30-40%: orange
    (50, "#eab308"),   # 40-50%: yellow-orange
    (60, "#d4af37"),   # 50-60%: golden
    (70, "#84cc16"),   # 60-70%: lime green
    (80, "#22c55e"),   # 70-80%: green
    (90, "#10b981"),   # 80-90%: emerald
    (101, "#059669"),  # 90-100%: deep green
]

def get_probability_color(prob: float) -> str:
    """Return color for probability value (0-100) using 10% bands."""
    for threshold, color in PROBABILITY_BANDS:
        if prob < threshold:
            return color
    return PROBABILITY_BANDS[-1][1]

def get_category_color(category: str) -> str:
    """Return a consistent color for a category."""
    category_colors = {
        "politics": "#ef4444",
        "economics": "#f97316",
        "crypto": "#8b5cf6",
        "science and tech": "#3b82f6",
        "sports": "#ec4899",
        "entertainment": "#d946ef",
        "world": "#06b6d4",
        "other": "#6b7280",
    }
    cat_lower = category.lower() if category else "other"
    return category_colors.get(cat_lower, "#6b7280")

# Cache watchlist in session to avoid repeated DB calls
if 'watchlist_cache' not in st.session_state:
    st.session_state.watchlist_cache = None

# Navigation state for overlap view
if 'show_overlaps_view' not in st.session_state:
    st.session_state.show_overlaps_view = False
if 'navigate_to_group' not in st.session_state:
    st.session_state.navigate_to_group = None

def format_oi(oi: float) -> str:
    """Format market metric (OI, volume, liquidity) in human-readable K/M notation."""
    if oi is None or oi == 0:
        return "$0"
    return f"${oi/1_000_000:.1f}M" if oi >= 1_000_000 else f"${oi/1_000:.0f}K"


def display_metric(label: str, value: str, color: str = None) -> None:
    """Display metric with consistent styling (label + value)."""
    if color is None:
        color = COLORS["metric_value"]
    st.markdown(
        f"<div style='margin: 3px 0;'>"
        f"<span style='font-weight: 500; font-size: 12px; color: {COLORS['metric_label']};'>{label}:</span> "
        f"<span style='color: {color}; font-weight: 600; font-size: 13px;'>{value}</span>"
        f"</div>",
        unsafe_allow_html=True
    )


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def load_markets():
    """Load markets from database including source, duplicate_group_id, and liquidity.
    Returns DataFrame with all market fields; source='polymarket'|'kalshi' identifies platform.
    duplicate_group_id links markets that appear on both platforms (based on 85% question similarity).
    liquidity represents market depth/trading capacity from fetchers."""
    conn = get_db()
    try:
        query = """
        SELECT id, question, volume, volume_24h, open_interest, probability, category, source, duplicate_group_id, liquidity
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
    """Add to watchlist and update session state."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO watchlist (market_id) VALUES (?)", (market_id,))
        conn.commit()
        st.session_state.watchlist_cache = None  # Clear cache
        # Update session to track this item was added
        if 'watchlist_updates' not in st.session_state:
            st.session_state.watchlist_updates = {}
        st.session_state.watchlist_updates[market_id] = True
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def remove_from_watchlist(market_id: str):
    """Remove from watchlist and update session state."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE market_id = ?", (market_id,))
        conn.commit()
        st.session_state.watchlist_cache = None  # Clear cache
        # Update session to track this item was removed
        if 'watchlist_updates' not in st.session_state:
            st.session_state.watchlist_updates = {}
        st.session_state.watchlist_updates[market_id] = False
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

# Normalize categories
df['category'] = df['category'].str.lower().replace(
    {'science': 'Science and Tech', 'science and technology': 'Science and Tech', 'tech': 'Science and Tech'},
    regex=False
)

# Sidebar filters
with st.sidebar:
    st.markdown("<h3 style='margin: 0; padding: 0; font-size: 0.9rem;'>🎚️ Filters</h3>", unsafe_allow_html=True)
    st.divider()
    
    # Market source filter
    source_option = st.radio("Market Source", ["Both", "Polymarket", "Kalshi"], index=0, horizontal=True)
    
    # Categories (collapsed by default)
    available_categories = sorted(df['category'].unique().tolist()) if 'category' in df.columns else []
    selected_categories = []
    with st.expander("📁 Categories", expanded=False):
        for cat in available_categories:
            if st.checkbox(cat, value=False, key=f"cat_{cat}"):
                selected_categories.append(cat)
    st.divider()
    
    # Watchlist
    show_favorites_only = st.checkbox("Show Favorites Only", value=False)
    
    # Overlapping markets (different terminology, same feature)
    show_overlaps_only = st.checkbox("Show Overlapping Markets Only (appear on both platforms)", value=False)
    st.divider()
    
    # OI threshold
    max_oi = int(df['open_interest'].max()) if len(df) > 0 else 1_000_000_000
    min_open_interest = st.slider("Minimum OI ($)", 50_000, max_oi, 50_000, format="$%d")
    
    # Probability range
    prob_min, prob_max = st.slider("Probability Range (%)", 0, 100, (0, 100))
    st.divider()
    
    # Quick Reference
    with st.expander("📖 Quick Reference", expanded=False):
        st.markdown("**Platform Badges:**")
        st.markdown(f"<span style='background-color: {COLORS['polymarket']}; color: white; padding: 3px 6px; border-radius: 2px; font-size: 0.85rem;'>Polymarket</span> | <span style='background-color: {COLORS['kalshi']}; color: white; padding: 3px 6px; border-radius: 2px; font-size: 0.85rem;'>Kalshi</span>", unsafe_allow_html=True)
        st.markdown("**Probability Colors:** Red (unlikely) → Green (likely)")
        st.markdown("**Metrics:**")
        st.markdown("- **OI:** Open Interest (market depth)")
        st.markdown("- **Volume:** Total/24h trading activity")
        st.markdown("- **Liquidity:** Market maker depth")
        st.markdown("**Icons:**")
        st.markdown("- **❤️ / 🤍:** Add/remove from favorites")
        st.markdown("- **🔗 Overlap:** View matching market on other platform")

# Apply filters
df_filtered = df[
    (df['open_interest'] >= min_open_interest) &
    (df['probability'] >= prob_min) &
    (df['probability'] <= prob_max)
].copy()

if selected_categories:
    df_filtered = df_filtered[df_filtered['category'].isin(selected_categories)]

# Apply source filter
if source_option == "Polymarket":
    df_filtered = df_filtered[df_filtered['source'] == 'polymarket']
elif source_option == "Kalshi":
    df_filtered = df_filtered[df_filtered['source'] == 'kalshi']

# Watchlist filter
if show_favorites_only:
    user_watchlist = load_watchlist()
    df_filtered = df_filtered[df_filtered['id'].isin(user_watchlist)]

# Overlaps filter
if show_overlaps_only:
    df_filtered = df_filtered[df_filtered['duplicate_group_id'].notna()]

# Main content
st.title("Market Consensus Intelligence")
st.markdown("**Harness collective Human intelligence to inform strategic business decisions**")

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
col1, col2, col3 = st.columns(3)
with col1:
    high_consensus = ((df_filtered['probability'] > 70) | (df_filtered['probability'] < 30)).sum()
    st.metric("High Conviction", high_consensus)
with col2:
    overlapping = df_filtered[df_filtered['duplicate_group_id'].notna()].shape[0]
    st.metric("Overlapping Markets", overlapping)
with col3:
    st.metric("Total Markets", len(df_filtered))

st.divider()

# Initialize search state
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

# Search bar (compact) with clear and suggestions
col_search, col_clear = st.columns([0.95, 0.05])

# Clear button first (before widget instantiation)
with col_clear:
    if st.button("✕", key="clear_search", help="Clear search"):
        st.session_state.search_query = ""

# Then render selectbox with callback
with col_search:
    suggestions = df_filtered['question'].unique().tolist() if len(df_filtered) > 0 else []
    search_query = st.selectbox(
        "Search markets",
        options=[""] + suggestions,
        index=0,
        format_func=lambda x: x if x else "Search by question...",
        key="search_query",
        label_visibility="collapsed"
    )

# Sorting and pagination controls
col_metric, col_direction = st.columns([2, 1])
with col_metric:
    sort_metric = st.selectbox("Sort By", ["Open Interest", "24h Volume", "Total Volume", "Liquidity", "Probability"], index=0)
with col_direction:
    sort_direction = st.radio("Direction", ["High → Low", "Low → High"], index=0, horizontal=True)

# Map sort metric to column
sort_map = {
    "Open Interest": "open_interest",
    "24h Volume": "volume_24h",
    "Total Volume": "volume",
    "Liquidity": "liquidity",
    "Probability": "probability",
}

sort_column = sort_map[sort_metric]
sort_ascending = (sort_direction == "Low → High")

# Apply search filter if query exists
if search_query.strip():
    df_filtered = df_filtered[df_filtered['question'].str.contains(search_query, case=False, na=False)]

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
showing_overlaps_only = (show_overlaps_only or st.session_state.show_overlaps_view) and len(df_filtered_sorted) > 0

if showing_overlaps_only:
    # Show back button if navigated from a market card
    if st.session_state.show_overlaps_view:
        if st.button("← Back to Markets"):
            st.session_state.show_overlaps_view = False
            st.session_state.navigate_to_group = None
            st.rerun()
        st.divider()
    
    # Filter to ONLY groups with markets from BOTH platforms (true overlaps)
    # First, exclude markets with no overlap group ID
    df_with_overlaps = df_filtered_sorted[pd.notna(df_filtered_sorted['duplicate_group_id'])]
    
    if len(df_with_overlaps) == 0:
        st.info("📭 No overlapping markets found.")
    else:
        grouped = df_with_overlaps.groupby('duplicate_group_id')
        true_overlaps = []
        for group_id, group_markets in grouped:
            sources = group_markets['source'].unique()
            # Only include groups with markets from BOTH Polymarket AND Kalshi
            if len(sources) >= 2 and 'polymarket' in [s.lower() for s in sources] and 'kalshi' in [s.lower() for s in sources]:
                true_overlaps.append(group_id)
        
        if len(true_overlaps) == 0:
            st.info("📭 No overlapping markets found between platforms.")
        else:
            # If navigating to specific group, show ONLY that group
            if st.session_state.navigate_to_group and st.session_state.navigate_to_group in true_overlaps:
                true_overlaps = [st.session_state.navigate_to_group]
            
            # Filter dataframe to only true overlaps
            df_overlaps_only = df_with_overlaps[df_with_overlaps['duplicate_group_id'].isin(true_overlaps)]
            grouped = df_overlaps_only.groupby('duplicate_group_id')
            total_groups = len(grouped)
            group_list = list(grouped.groups.keys())
            
            # Pagination for groups
            total_pages = (total_groups + st.session_state.markets_per_page - 1) // st.session_state.markets_per_page
            start_idx = (st.session_state.current_page - 1) * st.session_state.markets_per_page
            end_idx = min(start_idx + st.session_state.markets_per_page, total_groups)
            
            st.subheader(f"Overlapping Markets ({total_groups} groups) | Page {st.session_state.current_page}/{total_pages}")
            
            # Display groups for current page
            for group_idx in range(start_idx, end_idx):
                group_id = group_list[group_idx]
                group_markets = grouped.get_group(group_id).reset_index(drop=True)
                
                with st.container(border=True):
                    # Side-by-side comparison of platforms (with questions)
                    platform_cols = st.columns(len(group_markets))
                    
                    for col_idx, (_, market) in enumerate(group_markets.iterrows()):
                        with platform_cols[col_idx]:
                            source = market['source'].capitalize()
                            source_color = COLORS["kalshi"] if source == "Kalshi" else COLORS["polymarket"]
                            
                            # Platform header
                            st.markdown(f"<div style='background-color: {source_color}; color: white; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold;'>{source}</div>", unsafe_allow_html=True)
                            
                            # Question text
                            st.caption(f"**{market['question']}**")
                            st.divider()
                            
                            # Probability
                            prob = market['probability']
                            prob_color = get_probability_color(prob)
                            st.markdown(f"<div style='background-color: {prob_color}; color: white; padding: 8px; border-radius: 3px; text-align: center; margin: 8px 0; font-weight: bold;'>{prob:.0f}%</div>", unsafe_allow_html=True)
                            
                            # Details
                            display_metric("Open Interest", format_oi(market['open_interest']))
                            vol = market.get('volume', 0)
                            vol_24h = market['volume_24h']
                            display_metric("Total Volume", format_oi(vol) if vol else "$0", color=COLORS["polymarket"])
                            display_metric("Volume (24h)", format_oi(vol_24h), color=COLORS["probability_high"])
                            liq = market.get('liquidity', 0)
                            display_metric("Liquidity", format_oi(liq) if liq else "$0", color=COLORS["liquidity"])
                            
                            # Favorites button
                            in_watchlist = market['id'] in user_watchlist
                            # Check if this item was updated in current session
                            updated_state = st.session_state.watchlist_updates.get(market['id']) if 'watchlist_updates' in st.session_state else None
                            display_in_watchlist = updated_state if updated_state is not None else in_watchlist
                            
                            if display_in_watchlist:
                                if st.button("❤️", key=f"watch_{market['id']}", help="Remove from favorites"):
                                    if remove_from_watchlist(market['id']):
                                        st.toast("💔 Removed from favorites")
                                        st.rerun()
                            else:
                                if st.button("🤍", key=f"watch_{market['id']}", help="Add to favorites"):
                                    if add_to_watchlist(market['id']):
                                        st.toast("❤️ Added to favorites")
                                        st.rerun()
                            
                            # Category tag
                            category = market.get('category', 'N/A')
                            category_color = get_category_color(category)
                            st.markdown(f"<span style='background-color: {category_color}; color: white; padding: 4px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 500;'>{category}</span>", unsafe_allow_html=True)
            
            # Pagination controls for groups
            st.divider()
            col_prev, col_center, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("← Previous", disabled=(st.session_state.current_page == 1), use_container_width=True):
                    st.session_state.current_page -= 1
                    st.rerun()
            with col_center:
                st.markdown(f"<div style='text-align: center; padding: 8px;'>Page {st.session_state.current_page} of {total_pages}</div>", unsafe_allow_html=True)
            with col_next:
                if st.button("Next →", disabled=(st.session_state.current_page == total_pages), use_container_width=True):
                    st.session_state.current_page += 1
                    st.rerun()

else:
    # Normal view: show each market individually
    if total_markets == 0:
        st.info("📭 No markets match your filters. Try adjusting your selection.")
    else:
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
                # Top row: Probability + Question + Platform/Overlap (top right)
                col_prob, col_q, col_tags = st.columns([0.6, 3.2, 0.8])
                
                with col_prob:
                    prob = row['probability']
                    color = get_probability_color(prob)
                    st.markdown(f"<div style='background-color: {color}; padding: 6px; border-radius: 4px; text-align: center; color: white; font-size: 1.3rem;'>{prob:.0f}%<br><span style=\"font-size: 0.65rem; font-style: italic;\">probability</span></div>", unsafe_allow_html=True)
                
                with col_q:
                    st.caption(row['question'])  # Full question, no truncation
                
                with col_tags:
                    # Platform tag
                    source = row['source'].capitalize() if pd.notna(row['source']) else "Unknown"
                    source_color = COLORS["kalshi"] if source == "Kalshi" else COLORS["polymarket"]
                    st.markdown(f"<div style='background-color: {source_color}; color: white; padding: 4px 6px; border-radius: 3px; font-size: 0.8rem; text-align: center; font-weight: bold;'>{source}</div>", unsafe_allow_html=True)
                    
                    # Overlap tag (under platform)
                    if has_overlaps:
                        if st.button("🔗 Overlap", key=f"overlap_{row['id']}", help="View overlap group"):
                            st.session_state.navigate_to_group = row['duplicate_group_id']
                            st.session_state.show_overlaps_view = True
                            st.rerun()
                
                # Details row
                col_vol, col_oi, col_liq, col_watch = st.columns([1.2, 1.2, 1.2, 0.6])
                
                with col_vol:
                    vol = row.get('volume', 0)
                    vol_24h = row['volume_24h']
                    display_metric("Total Volume", format_oi(vol) if vol else "$0", color=COLORS["polymarket"])
                    display_metric("Volume (24h)", format_oi(vol_24h), color=COLORS["probability_high"])
                
                with col_oi:
                    display_metric("Open Interest", format_oi(row['open_interest']))
                
                with col_liq:
                    liq = row.get('liquidity', 0)
                    display_metric("Liquidity", format_oi(liq) if liq else "$0", color=COLORS["liquidity"])
                
                with col_watch:
                    in_watchlist = row['id'] in user_watchlist
                    # Check if this item was updated in current session
                    updated_state = st.session_state.watchlist_updates.get(row['id']) if 'watchlist_updates' in st.session_state else None
                    display_in_watchlist = updated_state if updated_state is not None else in_watchlist
                    
                    if display_in_watchlist:
                        if st.button("❤️", key=f"watch_{row['id']}", help="Remove from favorites"):
                            if remove_from_watchlist(row['id']):
                                st.toast("💔 Removed from favorites")
                                st.rerun()
                    else:
                        if st.button("🤍", key=f"watch_{row['id']}", help="Add to favorites"):
                            if add_to_watchlist(row['id']):
                                st.toast("❤️ Added to favorites")
                                st.rerun()
                
                # Bottom row: Category tag (bottom left)
                col_cat, col_spacer = st.columns([1.5, 3])
                with col_cat:
                    category = row.get('category', 'N/A')
                    category_color = get_category_color(category)
                    st.markdown(f"<span style='background-color: {category_color}; color: white; padding: 4px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 500;'>{category}</span>", unsafe_allow_html=True)
        
        # Pagination controls
        st.divider()
        col_prev, col_center, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Previous", disabled=(st.session_state.current_page == 1), use_container_width=True):
                st.session_state.current_page -= 1
                st.rerun()
        with col_center:
            st.markdown(f"<div style='text-align: center; padding: 8px;'>Page {st.session_state.current_page} of {total_pages}</div>", unsafe_allow_html=True)
        with col_next:
            if st.button("Next →", disabled=(st.session_state.current_page == total_pages), use_container_width=True):
                st.session_state.current_page += 1
                st.rerun()

