#!/usr/bin/env python
"""
Polymarket BI - Dashboard Entry Point
Streamlit dashboard for visualizing prediction market data.
Run with: streamlit run dashboard.py
"""

import os
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timezone
import json
import logging
import time
from functools import wraps
from dotenv import load_dotenv
from tz_utils import now_utc, days_until, format_relative_time
import threading
from queue import Queue, Empty

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "polymarket_bi.db")

# Ensure database can be found
if not os.path.exists(DATABASE_PATH):
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..")):
        os.chdir(os.path.dirname(__file__) or ".")


# ============================================================================
# CONNECTION POOL - Thread-safe SQLite connection management
# ============================================================================

class ConnectionPool:
    """Simple thread-safe connection pool for SQLite."""
    
    def __init__(self, db_path: str, pool_size: int = 5, timeout: float = 10.0):
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self.connections = Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        
        # Pre-create connections
        for _ in range(pool_size):
            conn = self._create_connection()
            self.connections.put(conn)
        
        logger.info(f"Connection pool initialized: {pool_size} connections")
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA cache_size=-64000')
        return conn
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool."""
        try:
            conn = self.connections.get_nowait()
            # Verify connection is still alive
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                # Connection dead, create new one
                return self._create_connection()
        except Empty:
            # Pool exhausted, create temporary connection
            logger.warning("Connection pool exhausted, creating temporary connection")
            return self._create_connection()
    
    def return_connection(self, conn: sqlite3.Connection):
        """Return a connection to the pool."""
        try:
            self.connections.put_nowait(conn)
        except:
            # Pool full, close connection
            try:
                conn.close()
            except:
                pass


# Initialize connection pool once
@st.cache_resource
def get_connection_pool():
    """Create and cache the connection pool."""
    pool = ConnectionPool(DATABASE_PATH, pool_size=5, timeout=10.0)
    return pool


def get_db_connection():
    """Get a database connection from the pool."""
    pool = get_connection_pool()
    return pool.get_connection()


def return_db_connection(conn: sqlite3.Connection):
    """Return a connection to the pool."""
    if conn:
        try:
            pool = get_connection_pool()
            pool.return_connection(conn)
        except Exception as e:
            logger.debug(f"Error returning connection: {e}")
            try:
                conn.close()
            except:
                pass

# ============================================================================
# PAGINATION CONFIGURATION
# ============================================================================

PAGINATION_SIZE = 20  # Show 20 markets per page

# Initialize pagination state
if "markets_to_show" not in st.session_state:
    st.session_state.markets_to_show = PAGINATION_SIZE

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Polymarket Business Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def retry_on_db_lock(max_retries: int = 3, initial_delay: float = 0.1):
    """Decorator to retry database operations on lock with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        if attempt < max_retries - 1:
                            logger.debug(f"[DB LOCK] Attempt {attempt + 1}/{max_retries}: retrying in {delay:.2f}s")
                            time.sleep(delay)
                            delay *= 2
                        continue
                    raise
            raise sqlite3.OperationalError(f"Database locked after {max_retries} retries")
        return wrapper
    return decorator


@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_max_open_interest():
    """Get maximum open interest value from database. Retries on DB lock."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(open_interest) FROM markets WHERE open_interest > 0")
        result = cursor.fetchone()
        return int(result[0]) if result and result[0] else 500_000_000
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch max OI: {e}")
        return 500_000_000
    finally:
        return_db_connection(conn)

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_last_refresh_time():
    """Get last data refresh timestamp from metadata table. Retries on DB lock."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = ? ORDER BY updated_at DESC LIMIT 1", ("last_refresh",))
        result = cursor.fetchone()
        if result and result[0]:
            return result[0]
    except sqlite3.Error as e:
        logger.debug(f"Could not fetch refresh timestamp: {e}")
    finally:
        return_db_connection(conn)
    return None

def get_refresh_status():
    """Get human-readable refresh status with staleness indicator."""
    last_refresh = get_last_refresh_time()
    if not last_refresh:
        return "⚠️ Never refreshed", "red"
    
    try:
        last_dt = pd.to_datetime(last_refresh, utc=True).to_pydatetime()
        current_dt = now_utc()
        delta = current_dt - last_dt
        
        minutes_ago = int(delta.total_seconds() / 60)
        if minutes_ago < 1:
            return "✅ Just updated", "green"
        elif minutes_ago < 30:
            return f"✅ Updated {minutes_ago}m ago", "green"
        elif minutes_ago < 60:
            return f"🟡 Updated {minutes_ago}m ago", "orange"
        else:
            hours_ago = minutes_ago // 60
            return f"⚠️ Updated {hours_ago}h ago (stale)", "red"
    except Exception as e:
        logger.debug(f"Error computing refresh status: {e}")
        return "❓ Unknown", "gray"

def parse_json_field(value):
    """Parse JSON-formatted field from database."""
    if not value:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value

def display_market_detail(row, market_id_key: str):
    """Display clickable market button that navigates to detailed market view."""
    prob = row['probability']
    verdict = "📈 HIGHLY LIKELY" if prob > 80 else ("📉 HIGHLY UNLIKELY" if prob < 20 else "⚖️ BALANCED")
    
    # Create a button that scrolls to the market in the detailed section
    # Full question text (no truncation) with arrow indicator for affordance
    if st.button(
        f"▶ 📊 {row['question']}\n{verdict} | {prob:.0f}% | Capital: ${row['open_interest']:,.0f}",
        key=f"market_nav_{market_id_key}",
        use_container_width=True,
        help="Click to view full market details and trading interface"
    ):
        # Store the selected market ID in session state
        st.session_state.selected_market_id = row['id']
        st.rerun()

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def load_markets():
    """Load all markets from database. Waits if refresh is in progress."""
    conn = get_db_connection()
    try:
        # Wait for refresh to complete if in progress (max 30 seconds)
        max_wait = 30
        wait_interval = 0.5
        elapsed = 0
        while elapsed < max_wait:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'refresh_in_progress'")
            row = cursor.fetchone()
            if row and row[0] == "true":
                elapsed += wait_interval
                time.sleep(wait_interval)
                continue
            break
        
        query = """
        SELECT 
            id,
            question,
            condition_id,
            volume,
            open_interest,
            end_date,
            active,
            outcomes,
            outcome_prices,
            probability,
            category
        FROM markets
        ORDER BY open_interest DESC
        """
        df = pd.read_sql_query(query, conn)
        
        if len(df) == 0:
            return df
        
        # Safely parse dates
        try:
            df['end_date'] = pd.to_datetime(df['end_date'], format='ISO8601', utc=True)
        except Exception as e:
            logger.warning(f"Date parsing failed: {e}. Using fallback parsing.")
            df['end_date'] = pd.to_datetime(df['end_date'], errors='coerce')
        
        return df
    except sqlite3.Error as e:
        logger.error(f"Failed to load markets: {e}")
        st.error(f"Failed to load market data: {e}")
        return pd.DataFrame()
    finally:
        return_db_connection(conn)

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def load_watchlist():
    """Load user's watchlist from database."""
    conn = get_db_connection()
    try:
        query = """
        SELECT m.id FROM markets m
        INNER JOIN watchlist w ON m.id = w.market_id
        """
        df = pd.read_sql_query(query, conn)
        return set(df['id'].tolist()) if len(df) > 0 else set()
    except sqlite3.Error as e:
        logger.debug(f"Failed to load watchlist: {e}")
        return set()
    finally:
        return_db_connection(conn)

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def add_to_watchlist(market_id: str):
    """Add market to watchlist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO watchlist (market_id) VALUES (?)", (market_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to add to watchlist: {e}")
        return False
    finally:
        return_db_connection(conn)

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def remove_from_watchlist(market_id: str):
    """Remove market from watchlist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE market_id = ?", (market_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to remove from watchlist: {e}")
        return False
    finally:
        return_db_connection(conn)

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_probability_history(market_id: str):
    """Get historical probability data for a market."""
    conn = get_db_connection()
    try:
        query = """
        SELECT timestamp, probability FROM snapshots
        WHERE market_id = ?
        ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn, params=(market_id,))
        if len(df) > 0:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        return df
    except sqlite3.Error as e:
        logger.debug(f"Failed to load probability history: {e}")
        return pd.DataFrame()
    finally:
        return_db_connection(conn)

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def trigger_data_refresh():
    """Trigger a manual data refresh by calling the pipeline."""
    # Debouncing: prevent multiple simultaneous refreshes
    if "refresh_in_progress" not in st.session_state:
        st.session_state.refresh_in_progress = False
    
    if st.session_state.refresh_in_progress:
        st.warning("⏳ Refresh already in progress. Please wait...")
        return
    
    try:
        st.session_state.refresh_in_progress = True
        
        from pipeline import DatabaseManager
        import asyncio
        from pipeline import PolymarketPoller
        
        # Show detailed progress
        progress_bar = st.progress(0, "🔄 Starting refresh...")
        status_text = st.empty()
        
        def update_progress(step: int, total: int, message: str):
            progress_bar.progress(min(step / total, 0.99), message)
            status_text.caption(message)
        
        # Step 1: Fetch markets
        update_progress(1, 4, "🔄 Fetching markets from Polymarket API (13 categories)...")
        min_volume = float(os.getenv("MIN_VOLUME_USD", "100000"))
        min_oi = float(os.getenv("MIN_OPEN_INTEREST_USD", "50000"))
        
        markets = asyncio.run(PolymarketPoller.fetch_all_categories(min_volume, min_oi))
        update_progress(2, 4, f"✓ Fetched {len(markets)} markets. Now updating database...")
        
        # Step 2: Store in database
        db = DatabaseManager()
        db.connect()
        db.init_schema()
        new, updated = db.insert_markets(markets)
        db.close()
        
        update_progress(3, 4, f"✓ Database updated: {new} new, {updated} updated")
        
        # Step 3: Complete
        progress_bar.progress(1.0, "✅ Refresh complete!")
        st.success(f"✅ Data refresh successful! {new} new markets, {updated} updated markets")
        
        time.sleep(1)  # Let user see success message
        st.rerun()
    except Exception as e:
        st.error(f"❌ Refresh failed: {e}")
        st.error("💡 Tip: Check that Polymarket API is accessible and you have internet connection")
        logger.error(f"Manual refresh error: {e}", exc_info=True)
    finally:
        st.session_state.refresh_in_progress = False


def parse_json_field(json_str):
    """Parse JSON string safely."""
    try:
        return json.loads(json_str) if json_str else []
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return []

# ============================================================================
# MAIN CONTENT STARTS HERE
# ============================================================================

# Load market data first
df = load_markets()

# Show staleness warning if data is old
refresh_status, status_color = get_refresh_status()
if "stale" in refresh_status.lower():
    st.warning(f"⚠️ {refresh_status} - Data may be outdated. Live updates temporarily unavailable.")
elif "never" in refresh_status.lower():
    st.error("❌ No data available. Pipeline has not run yet.")

if len(df) == 0:
    st.warning("⚠️ No data in database. Please run the data pipeline first.")
    st.info("Run: `python main.py`")
    st.stop()

# Prepare filtering variables
max_open_interest = get_max_open_interest()
open_interest_step = max(1000, max_open_interest // 100)

# ============================================================================
# SIDEBAR CONTROLS
# ============================================================================

with st.sidebar:
    st.header("🎚️ Filters")
    
    st.divider()
    
    # Category/tag filtering - only show categories with active markets
    if 'category' in df.columns and len(df) > 0:
        # Count markets per category
        category_counts = df['category'].value_counts().sort_index()
        # Only include categories with at least one market
        available_categories = sorted([cat for cat in category_counts[category_counts > 0].index.tolist()])
    else:
        available_categories = []
    
    selected_categories = st.multiselect(
        "Market Categories",
        available_categories if available_categories else ["No categories found"],
        default=[],
        help="Filter to specific prediction market categories. Leave empty to see all markets."
    )
    
    st.divider()
    
    # Favorites filter
    show_favorites_only = st.checkbox(
        "⭐ Show Favorites Only",
        value=False,
        help="Display only your watchlist markets"
    )
    
    st.divider()
    
    # Open Interest threshold slider
    min_open_interest = st.slider(
        "Minimum Open Interest ($)",
        min_value=50_000,
        max_value=max_open_interest,
        value=50_000,
        step=open_interest_step,
        format="$%d",
        help="Markets below this liquidity level are excluded"
    )
    
    st.divider()
    
    # Probability range filtering with business context
    st.write("**Probability Conviction Range**")
    prob_min, prob_max = st.slider(
        "Filter markets by YES probability",
        0, 100, (0, 100),
        help="Show markets where the crowd thinks YES has between X% and Y% chance. Use to find consensus or disagreement zones."
    )
    
    # Show what this range means
    if prob_min > 60 or prob_max < 40:
        st.caption("🎯 Showing high conviction markets (crowd strongly agrees)")
    elif 40 <= prob_min and prob_max <= 60:
        st.caption("⚖️ Showing balanced markets (crowd is split)")
    else:
        st.caption("🔍 Showing full spectrum of market opinions")
    
    st.divider()
    
    # Time to expiration with smart bucketing
    df_temp = load_markets()
    df_temp['days_left'] = df_temp['end_date'].apply(lambda x: days_until(pd.to_datetime(x, utc=True).to_pydatetime()) if pd.notna(x) else 999)
    max_days = int(df_temp['days_left'].max()) if len(df_temp) > 0 else 365
    
    st.write("**Market Timeline**")
    time_bucket = st.radio(
        "When do you want markets to resolve?",
        ["Today (0-1 days)", "This Week (2-7 days)", "Next 30 Days (8-30 days)", "All Markets"],
        horizontal=True,
        index=3,
        help="Markets resolving sooner are more informative; longer-dated markets are more speculative"
    )
    
    if time_bucket == "Today (0-1 days)":
        time_min, time_max = 0, 1
    elif time_bucket == "This Week (2-7 days)":
        time_min, time_max = 2, 7
    elif time_bucket == "Next 30 Days (8-30 days)":
        time_min, time_max = 8, 30
    else:
        time_min, time_max = 0, max_days
    
    st.divider()
    
    # About
    with st.expander("ℹ️ Business Intelligence Guide"):
        st.write("""
**Key Metrics Explained:**

- **Probability %** - Market's implicit forecast (higher = more certain)
- **Open Interest (OI)** - Capital at risk in this market (higher = more reliable signal)
- **24h Volume** - Recent trading activity (shows market engagement)
- **Days to Resolution** - Time remaining (shorter = more informative, longer = more speculative)
- **Market Maturity** - Today = near-final predictions, Week = active forecasts, 30+ days = speculative

**How to use this dashboard:**

1. **Find Consensus** - Markets above 70% or below 30% show strong expert agreement
2. **Spot Disagreement** - Markets near 50/50 highlight where opinion diverges (risk zones)
3. **Trust Older Predictions** - Markets resolved soon carry more predictive weight
4. **Check Liquidity** - Higher OI = more reliable prices; low OI = potentially noisy

**Business Use Cases:**
- Forecast planning (What does the market predict?)
- Risk assessment (Where is opinion split?)
- Decision timing (When is conviction strongest?)
- Hedging (Which outcomes are underpriced?)
""")


# ============================================================================
# MAIN DASHBOARD
# ============================================================================

st.title("📈 Business Prediction Market Intelligence")
st.markdown("**Real-time consensus analysis for strategic decision-making**")

# Display last refresh timestamp and manual refresh button
col_refresh, col_status = st.columns([2, 3])

with col_refresh:
    # Disable button if refresh is already in progress
    refresh_disabled = st.session_state.get("refresh_in_progress", False)
    if st.button(
        "🔄 Refresh Data Now",
        use_container_width=True,
        help="Manually fetch latest data from Polymarket API. Takes 5-10 minutes.",
        disabled=refresh_disabled
    ):
        trigger_data_refresh()

with col_status:
    refresh_status, status_color = get_refresh_status()
    st.markdown(f"**{refresh_status}**")

st.divider()

# Apply filters
df_filtered = df[
    (df['open_interest'] >= min_open_interest) &
    (df['probability'] >= prob_min) &
    (df['probability'] <= prob_max)
].copy()

# Apply category filter if selected
if selected_categories and 'category' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['category'].isin(selected_categories)]

# Calculate days left for time filtering
df_filtered['days_left'] = df_filtered['end_date'].apply(
    lambda x: days_until(pd.to_datetime(x, utc=True).to_pydatetime()) if pd.notna(x) else 999
)
df_filtered = df_filtered[
    (df_filtered['days_left'] >= time_min) &
    (df_filtered['days_left'] <= time_max)
]

# Add market maturity category for display
def get_maturity(days):
    if days <= 1:
        return "🔴 FINAL VERDICT"
    elif days <= 7:
        return "🟡 ACTIVE"
    else:
        return "🔵 SPECULATIVE"

df_filtered['maturity'] = df_filtered['days_left'].apply(get_maturity)

# Load user's watchlist
user_watchlist = load_watchlist()

# Apply favorites filter if enabled
if show_favorites_only:
    df_filtered = df_filtered[df_filtered['id'].isin(user_watchlist)]

# ============================================================================
# BUSINESS INSIGHTS SECTION
# ============================================================================

st.subheader("🎯 Market Consensus Analysis")

col1, col2, col3, col4 = st.columns(4)

with col1:
    # High consensus markets (>70% or <30%)
    high_consensus = (
        (df_filtered['probability'] > 70) | 
        (df_filtered['probability'] < 30)
    ).sum()
    st.metric(
        "🎯 High Conviction",
        high_consensus,
        f"{high_consensus/len(df_filtered)*100 if len(df_filtered) > 0 else 0:.0f}% of markets",
        help="Markets where experts strongly agree (>70% or <30%)"
    )

with col2:
    # Disagreement markets (40-60%)
    disagreement = (
        (df_filtered['probability'] > 40) & 
        (df_filtered['probability'] < 60)
    ).sum()
    st.metric(
        "⚖️ Balanced View",
        disagreement,
        f"{disagreement/len(df_filtered)*100 if len(df_filtered) > 0 else 0:.0f}% of markets",
        help="Markets where experts are divided (40-60%)"
    )

with col3:
    # Imminent resolutions (<7 days)
    imminent = (df_filtered['days_left'] < 7).sum()
    st.metric(
        "⏰ Resolutions This Week",
        imminent,
        f"{imminent/len(df_filtered)*100 if len(df_filtered) > 0 else 0:.0f}% of markets",
        help="Markets with <7 days to resolution"
    )

with col4:
    # High liquidity markets
    high_liquidity_threshold = df_filtered['open_interest'].quantile(0.75)
    high_liq = (df_filtered['open_interest'] > high_liquidity_threshold).sum()
    st.metric(
        "💰 Highly Liquid",
        high_liq,
        f"Top 25% OI",
        help="Markets with best price discovery"
    )

st.divider()

# ============================================================================
# STRATEGIC DISCOVERY SECTION
# ============================================================================

st.subheader("✨ Key Markets to Monitor")

col_hot, col_disagree, col_critical = st.columns(3)

with col_hot:
    st.markdown("### 🔥 Strongest Consensus")
    st.caption("Where the smart money agrees (>80% or <20% probability)")
    
    extreme = df_filtered[
        (df_filtered['probability'] > 80) | 
        (df_filtered['probability'] < 20)
    ].nlargest(3, 'open_interest')
    
    for idx, (_, market) in enumerate(extreme.iterrows()):
        prob = market['probability']
        verdict = "📈 HIGHLY LIKELY" if prob > 80 else "📉 HIGHLY UNLIKELY"
        display_market_detail(market, f"consensus_hot_{idx}")

with col_disagree:
    st.markdown("### ⚖️ Markets in Flux")
    st.caption("High disagreement = high risk/reward opportunities")
    
    df_filtered['distance_from_50'] = abs(df_filtered['probability'] - 50)
    balanced = df_filtered.nsmallest(3, 'distance_from_50')
    
    for idx, (_, market) in enumerate(balanced.iterrows()):
        display_market_detail(market, f"consensus_flux_{idx}")

with col_critical:
    st.markdown("### 🚨 Resolution Imminent")
    st.caption("Markets resolving soon - Final verdicts emerging")
    
    soon = df_filtered[df_filtered['days_left'] < 7].nlargest(3, 'open_interest')
    
    for idx, (_, market) in enumerate(soon.iterrows()):
        display_market_detail(market, f"consensus_imminent_{idx}")

st.divider()

# ============================================================================
# SEARCH & DETAILED EXPLORATION
# ============================================================================

st.subheader("🔍 Find Specific Markets")

# Search box with context-aware filtering
search_col1, search_col2 = st.columns([4, 0.8])

with search_col1:
    search_term = st.text_input(
        "Search by keyword",
        placeholder="e.g., Bitcoin, Fed, election, earnings...",
        help="Search respects active filters - results limited to selected categories, time range, and conviction"
    )

with search_col2:
    if search_term:
        if st.button("✕ Clear", key="clear_search", help="Clear search and show all filtered markets"):
            st.session_state.search_query = ""
            st.rerun()

# Smart search results with context-aware filtering
search_results = df_filtered.copy()
if search_term:
    # Filter by keyword
    search_results = search_results[
        search_results['question'].str.contains(search_term, case=False, na=False)
    ]
    
    # Sort by relevance (OI as proxy for importance)
    search_results = search_results.sort_values('open_interest', ascending=False)

if search_term and len(search_results) > 0:
    # Display result summary
    filtered_context = []
    if selected_categories:
        filtered_context.append(f"in {len(selected_categories)} categories")
    if time_bucket != "All Markets":
        filtered_context.append(f"{time_bucket.lower()}")
    
    context_str = f" ({', '.join(filtered_context)})" if filtered_context else ""
    st.caption(f"✅ Found **{len(search_results)} markets** matching '{search_term}'{context_str}")
    
    # Show top 5 smart suggestions as compact cards
    if len(search_results) > 0:
        st.caption("**Top matches by liquidity:**")
        top_5 = search_results.head(5)
        
        for idx, (_, market) in enumerate(top_5.iterrows()):
            with st.container(border=True):
                col_q, col_p, col_oi = st.columns([3, 1, 1.5])
                
                with col_q:
                    st.markdown(f"**{market['question'][:60]}{'...' if len(market['question']) > 60 else ''}**")
                
                with col_p:
                    prob = market['probability']
                    st.metric("Prob", f"{prob:.0f}%", label_visibility="collapsed")
                
                with col_oi:
                    st.metric("OI", f"${market['open_interest']/1e6:.1f}M", label_visibility="collapsed")
    
    if len(search_results) > 5:
        st.caption(f"📍 +{len(search_results)-5} more markets match. Scroll to Market Details to see all.")
    
    # Sorting options for full search results
    if len(search_results) > 0:
        col_sort1, col_sort2 = st.columns(2)
        with col_sort1:
            sort_by = st.selectbox(
                "Sort all results by",
                ["Liquidity (Highest OI)", "Conviction (Highest %)", "Resolution Time (Soonest)"],
                key="search_sort"
            )
        
        # Apply sorting
        if sort_by == "Conviction (Highest %)":
            search_results = search_results.iloc[(search_results['probability'] - 50).abs().argsort()]
            search_results = search_results.iloc[::-1]  # Highest conviction first
        elif sort_by == "Liquidity (Highest OI)":
            search_results = search_results.sort_values('open_interest', ascending=False)
        elif sort_by == "Resolution Time (Soonest)":
            search_results = search_results.sort_values('end_date', ascending=True)
        
        # Update filtered dataframe to show sorted search results
        df_filtered = search_results
else:
    if search_term:
        context_msg = ""
        if selected_categories or time_bucket != "All Markets" or min_open_interest > 50_000:
            context_msg = " within your active filters"
        st.info(f"💡 No markets match '{search_term}'{context_msg}. Try different keywords: crypto, Fed, politics, earnings, etc.")

st.divider()

# ============================================================================
# ACTIVE FILTERS SUMMARY
# ============================================================================

# Build active filters list
active_filters = []

# Category filter
if selected_categories:
    active_filters.append(f"📁 {', '.join(selected_categories)}")

# Favorites filter
if show_favorites_only:
    active_filters.append("⭐ Favorites Only")

# Open Interest filter
if min_open_interest > 50_000:
    active_filters.append(f"💰 Min OI: ${min_open_interest:,.0f}")

# Probability filter
if prob_min > 0 or prob_max < 100:
    active_filters.append(f"📊 Probability: {prob_min}%-{prob_max}%")

# Timeline filter
if time_bucket != "All Markets":
    active_filters.append(f"⏰ {time_bucket}")

# Display filter summary if any filters are active
if active_filters:
    col_filters, col_clear = st.columns([4, 0.6])
    with col_filters:
        st.caption(f"**🔍 Active Filters:** {' • '.join(active_filters)}")
    with col_clear:
        if st.button("✕ Clear All", key="clear_filters", help="Reset all filters to defaults"):
            st.session_state.selected_categories = []
            st.session_state.show_favorites = False
            st.rerun()

st.divider()

# ============================================================================
# DETAILED MARKET ANALYSIS
# ============================================================================

st.subheader(f"📊 Market Details ({len(df_filtered)} markets)")

if len(df_filtered) == 0:
    st.info("💡 No markets match your filters. Try adjusting the thresholds above.")
else:
    # Sort options - right-aligned with controls
    sort_col1, sort_col2 = st.columns([4, 1])
    
    with sort_col1:
        # Display count and pagination info
        remaining = len(df_filtered) - st.session_state.markets_to_show
        if remaining > 0:
            st.caption(f"📍 Showing {min(st.session_state.markets_to_show, len(df_filtered))} of {len(df_filtered)} markets (+ {remaining} more)")
        else:
            st.caption(f"✅ Showing all {len(df_filtered)} markets")
    
    with sort_col2:
        # Sort selector dropdown
        sort_option = st.selectbox(
            "Sort by",
            options=[
                "High OI First (💰 Capital)",
                "High Probability (📈 Conviction)",
                "Low Probability (📉 Outlier)",
                "Resolution Soon (⏰ Time)",
                "Newest Activity",
                "Open Interest ↓"
            ],
            index=0,
            key="market_sort_selector",
            help="Rank markets by different factors"
        )
    
    # Apply sorting based on selection
    if sort_option == "High OI First (💰 Capital)":
        df_filtered = df_filtered.sort_values('open_interest', ascending=False)
    elif sort_option == "High Probability (📈 Conviction)":
        df_filtered = df_filtered.sort_values('probability', ascending=False)
    elif sort_option == "Low Probability (📉 Outlier)":
        df_filtered = df_filtered.sort_values('probability', ascending=True)
    elif sort_option == "Resolution Soon (⏰ Time)":
        df_filtered = df_filtered.sort_values('end_date', ascending=True)
    elif sort_option == "Newest Activity":
        # Note: Would need timestamp field in DB for true "newest activity"
        # For now, using open_interest as proxy for recent activity
        df_filtered = df_filtered.sort_values('open_interest', ascending=False)
    elif sort_option == "Open Interest ↓":
        df_filtered = df_filtered.sort_values('open_interest', ascending=True)
    
    # Market cards with business focus
    for idx, (_, row) in enumerate(df_filtered.iterrows()):
        # Stop rendering after pagination limit
        if idx >= st.session_state.markets_to_show:
            break
        prices = parse_json_field(row['outcome_prices'])
        outcomes = parse_json_field(row['outcomes'])
        
        # Get category from database or infer from question
        if pd.notna(row.get('category')):
            category = row['category']
        else:
            question_lower = row['question'].lower()
            if any(word in question_lower for word in ['bitcoin', 'ethereum', 'crypto', 'xrp', 'solana', 'doge']):
                category = "🔐 Crypto"
            elif any(word in question_lower for word in ['trump', 'biden', 'election', 'congress', 'senate', 'democrat', 'republican', 'president']):
                category = "🏛️ Politics"
            elif any(word in question_lower for word in ['fed', 'interest rate', 'inflation', 'recession', 'gdp', 'unemployment', 'economy', 'stock', 'dow', 'nasdaq', 's&p']):
                category = "📈 Finance"
            elif any(word in question_lower for word in ['ai', 'llm', 'openai', 'google', 'meta', 'apple', 'microsoft', 'tech', 'software']):
                category = "💻 Tech"
            elif any(word in question_lower for word in ['war', 'conflict', 'russia', 'ukraine', 'israel', 'international']):
                category = "🌍 Geopolitics"
            else:
                category = "📊 Other"
        
        # Check if in watchlist
        in_watchlist = row['id'] in user_watchlist
        
        # Check if this is the selected market - highlight it with expanded view
        is_selected = st.session_state.get('selected_market_id') == row['id']
        
        # Determine conviction level based on probability
        prob = row['probability']
        if prob >= 80 or prob <= 20:
            conviction = "high"
            conviction_label = "🟢 High Conviction"
            conviction_color = "#d4f1d4"  # Light green
        elif (prob >= 60 and prob <= 80) or (prob >= 20 and prob <= 40):
            conviction = "moderate"
            conviction_label = "🟡 Moderate Conviction"
            conviction_color = "#fff3cd"  # Light yellow
        else:
            conviction = "balanced"
            conviction_label = "⚖️ Balanced"
            conviction_color = "#e9ecef"  # Light gray
        
        with st.container(border=is_selected):
            # Header with conviction color indicator
            st.markdown(f"<div style='background-color: {conviction_color}; padding: 12px; border-radius: 6px; margin-bottom: 12px;'>"
                       f"<b>{conviction_label}</b></div>", unsafe_allow_html=True)
            
            # Header with category badge, question, and probability + watchlist button
            col_cat, col_q, col_p, col_watch = st.columns([1, 3, 1.2, 0.8])
            
            with col_cat:
                if is_selected:
                    st.caption(f"✨ {category}")
                else:
                    st.caption(category)
            
            with col_q:
                st.markdown(f"### {row['question']}")
            
            with col_p:
                st.metric("Probability", f"{prob:.0f}%", 
                         help="Market consensus (0-100%)", label_visibility="visible")
            
            with col_watch:
                # Watchlist button
                if in_watchlist:
                    if st.button("⭐", key=f"watch_{row['id']}", help="Remove from watchlist"):
                        remove_from_watchlist(row['id'])
                        st.rerun()
                else:
                    if st.button("☆", key=f"watch_{row['id']}", help="Add to watchlist"):
                        add_to_watchlist(row['id'])
                        st.rerun()
            
            st.divider()
            
            # Key metrics for business decisions (SIMPLIFIED - essential only)
            m1, m2, m3 = st.columns(3)
            
            with m1:
                st.metric("Open Interest", f"${row['open_interest']:,.0f}", 
                         help="Total capital at risk. Higher = more confidence, better price discovery")
            
            with m2:
                end_dt = pd.to_datetime(row['end_date'], utc=True).to_pydatetime()
                days = days_until(end_dt)
                st.metric("Resolution", f"{days}d" if days is not None else "N/A",
                         help="Time until certainty. Shorter = near-final verdict, longer = still speculative")
            
            with m3:
                status = "🟢 ACTIVE" if row['active'] else "🔴 CLOSED"
                st.metric("Status", status, label_visibility="collapsed")
            
            st.divider()
            
            # Prediction bar - clear yes/no indicator
            prob_val = row['probability']
            prob_color = "🟢" if prob_val > 50 else "🔴"
            st.progress(prob_val / 100.0, f"{prob_color} {prob_val:.0f}% YES likelihood")
            
            # COLLAPSED DETAILS SECTION (user must expand to see)
            with st.expander("📊 More Details (Chart & Outcomes)", expanded=False):
                st.divider()
                
                # Historical probability trend
                prob_history = get_probability_history(row['id'])
                if len(prob_history) > 1:
                    try:
                        chart_data = prob_history.set_index('timestamp')
                        st.line_chart(chart_data['probability'], height=200, use_container_width=True)
                        st.caption("📈 Historical probability trend")
                    except Exception as e:
                        logger.debug(f"Could not render chart: {e}")
                else:
                    st.caption("💡 No historical data available yet")
                
                st.divider()
                
                # Show additional metric in collapsed section
                st.metric("24h Volume", f"${row['volume']:,.0f}",
                         help="Trading activity. Higher = more liquid, easier to enter/exit positions")
                
                st.divider()
                
                # Outcome probabilities as business decision points
                if outcomes and prices:
                    try:
                        if len(outcomes) != len(prices):
                            st.warning(f"⚠️ Data mismatch: {len(outcomes)} outcomes but {len(prices)} prices")
                        else:
                            st.write("**Outcome Probabilities:**")
                            
                            for outcome, price in zip(outcomes, prices):
                                try:
                                    prob_pct = float(price) * 100
                                    col_label, col_bar = st.columns([1, 4])
                                    
                                    with col_label:
                                        st.write(f"**{outcome}**")
                                    
                                    with col_bar:
                                        st.progress(float(price), f"{prob_pct:.1f}%")
                                except (ValueError, TypeError) as e:
                                    st.warning(f"Could not display {outcome}: invalid price value")
                    except Exception as e:
                        logger.debug(f"Error rendering outcome probabilities: {e}")
                        st.caption("💡 Outcome probabilities unavailable for this market")
                elif outcomes or prices:
                    st.caption("⚠️ Incomplete outcome data (missing prices or outcomes)")
    
    # Load More button
    st.divider()
    if st.session_state.markets_to_show < len(df_filtered):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("📥 Load More Markets", use_container_width=True, key="load_more"):
                st.session_state.markets_to_show += PAGINATION_SIZE
                st.rerun()
    else:
        st.caption("✅ All markets loaded")

st.divider()

# Enhanced footer with meaningful stats and refresh status
f1, f2, f3, f4 = st.columns(4)
with f1:
    st.metric("Total Markets", len(df), delta=None, label_visibility="collapsed")
with f2:
    liquid_count = len(df[df['open_interest'] > 50000])
    st.metric("Highly Liquid", liquid_count, label_visibility="collapsed")
with f3:
    high_conviction = len(df[(df['probability'] > 80) | (df['probability'] < 20)])
    st.metric("High Conviction", high_conviction, label_visibility="collapsed")
with f4:
    refresh_status, _ = get_refresh_status()
    st.caption(refresh_status)

