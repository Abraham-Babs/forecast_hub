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
    initial_sidebar_state="collapsed"
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

@st.cache_resource
def get_db_connection():
    """Create database connection with concurrency handling (cached for reuse)."""
    try:
        # Use 10-second timeout and WAL mode for better concurrency
        conn = sqlite3.connect(DATABASE_PATH, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA cache_size=-64000')
        logger.info("Database connection established (WAL mode, 10s timeout)")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection failed: {e}")
        st.error(f"Failed to connect to database: {e}")
        st.stop()

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_max_open_interest():
    """Get maximum open interest value from database. Retries on DB lock."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(open_interest) FROM markets WHERE open_interest > 0")
        result = cursor.fetchone()
        return int(result[0]) if result and result[0] else 500_000_000
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch max OI: {e}")
        return 500_000_000

@retry_on_db_lock(max_retries=3, initial_delay=0.1)
def get_last_refresh_time():
    """Get last data refresh timestamp from metadata table. Retries on DB lock."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = ? ORDER BY updated_at DESC LIMIT 1", ("last_refresh",))
        result = cursor.fetchone()
        if result and result[0]:
            return result[0]
    except sqlite3.Error as e:
        logger.debug(f"Could not fetch refresh timestamp: {e}")
    return None

def get_refresh_status():
    """Get human-readable refresh status with staleness indicator."""
    last_refresh = get_last_refresh_time()
    if not last_refresh:
        return "⚠️ Never refreshed", "red"
    
    try:
        last_dt = pd.to_datetime(last_refresh, utc=True)
        now_dt = datetime.now(timezone.utc)
        delta = now_dt - last_dt
        
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

def load_markets():
    """Load all markets from database."""
    try:
        conn = get_db_connection()
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
            probability
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
    
    # Probability range
    prob_min, prob_max = st.slider(
        "Probability Range",
        0, 100, (0, 100),
        help="Filter by 'Yes' probability range"
    )
    
    st.divider()
    
    # Time to expiration with smart bucketing
    df_temp = load_markets()
    df_temp['days_left'] = (df_temp['end_date'] - datetime.now(timezone.utc)).dt.days
    max_days = int(df_temp['days_left'].max()) if len(df_temp) > 0 else 365
    
    st.write("**Market Timeline**")
    time_bucket = st.radio(
        "When do you want markets to resolve?",
        ["Today (0-1 days)", "This Week (2-7 days)", "Next 30 Days (8-30 days)", "All Markets"],
        horizontal=True,
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

# Apply filters
df_filtered = df[
    (df['open_interest'] >= min_open_interest) &
    (df['probability'] >= prob_min) &
    (df['probability'] <= prob_max)
].copy()

# Calculate days left for time filtering
df_filtered['days_left'] = (df_filtered['end_date'] - datetime.now(timezone.utc)).dt.days
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
    
    for _, market in extreme.iterrows():
        prob = market['probability']
        verdict = "📈 HIGHLY LIKELY" if prob > 80 else "📉 HIGHLY UNLIKELY"
        st.write(f"**{market['question'][:45]}...**")
        st.caption(f"{verdict} | {prob:.0f}% confidence | Capital: ${market['open_interest']:,.0f}")

with col_disagree:
    st.markdown("### ⚖️ Markets in Flux")
    st.caption("High disagreement = high risk/reward opportunities")
    
    df_filtered['distance_from_50'] = abs(df_filtered['probability'] - 50)
    balanced = df_filtered.nsmallest(3, 'distance_from_50')
    
    for _, market in balanced.iterrows():
        prob = market['probability']
        st.write(f"**{market['question'][:45]}...**")
        st.caption(f"Split: {prob:.0f}%/{100-prob:.0f}% | Capital: ${market['open_interest']:,.0f}")

with col_critical:
    st.markdown("### 🚨 Resolution Imminent")
    st.caption("Markets resolving soon - Final verdicts emerging")
    
    soon = df_filtered[df_filtered['days_left'] < 7].nlargest(3, 'open_interest')
    
    for _, market in soon.iterrows():
        days = market['days_left']
        prob = market['probability']
        st.write(f"**{market['question'][:45]}...**")
        st.caption(f"{prob:.0f}% likely | ⏰ {days:.0f} days | Capital: ${market['open_interest']:,.0f}")

st.divider()

# ============================================================================
# SEARCH & DETAILED EXPLORATION
# ============================================================================

st.subheader("🔍 Find Specific Markets")

search_term = st.text_input(
    "Search by keyword",
    placeholder="e.g., Bitcoin, Fed, election, earnings...",
    help="Search across all market questions"
)

if search_term:
    df_filtered = df_filtered[
        df_filtered['question'].str.contains(search_term, case=False, na=False)
    ]
    st.caption(f"✅ Found {len(df_filtered)} matching markets")

st.divider()

# ============================================================================
# DETAILED MARKET ANALYSIS
# ============================================================================

st.subheader(f"📊 Market Details ({len(df_filtered)} markets)")

if len(df_filtered) == 0:
    st.info("💡 No markets match your filters. Try adjusting the thresholds above.")
else:
    # Display count and pagination info
    remaining = len(df_filtered) - st.session_state.markets_to_show
    if remaining > 0:
        st.caption(f"📍 Showing {min(st.session_state.markets_to_show, len(df_filtered))} of {len(df_filtered)} markets (+ {remaining} more)")
    else:
        st.caption(f"✅ Showing all {len(df_filtered)} markets")
    
    # Market cards with business focus
    for idx, (_, row) in enumerate(df_filtered.iterrows()):
        # Stop rendering after pagination limit
        if idx >= st.session_state.markets_to_show:
            break
        prices = parse_json_field(row['outcome_prices'])
        outcomes = parse_json_field(row['outcomes'])
        
        with st.container(border=True):
            # Header with full question and probability badge
            col_q, col_p = st.columns([4, 1])
            
            with col_q:
                st.markdown(f"### {row['question']}")
            
            with col_p:
                prob = row['probability']
                st.metric("Probability", f"{prob:.0f}%", 
                         help="Market consensus (0-100%)", label_visibility="visible")
            
            st.divider()
            
            # Key metrics for business decisions
            m1, m2, m3, m4 = st.columns(4)
            
            with m1:
                st.metric("Open Interest", f"${row['open_interest']:,.0f}", 
                         help="Total capital at risk. Higher = more confidence, better price discovery")
            
            with m2:
                st.metric("24h Volume", f"${row['volume']:,.0f}",
                         help="Trading activity. Higher = more liquid, easier to enter/exit positions")
            
            with m3:
                days = (row['end_date'] - datetime.now(timezone.utc)).days
                st.metric("Resolution", f"{days}d",
                         help="Time until certainty. Shorter = near-final verdict, longer = still speculative")
            
            with m4:
                status = "🟢 ACTIVE" if row['active'] else "🔴 CLOSED"
                st.metric("Status", status, label_visibility="collapsed")
            
            st.divider()
            
            # Prediction bar - clear yes/no indicator
            prob_val = row['probability']
            prob_color = "🟢" if prob_val > 50 else "🔴"
            st.progress(prob_val / 100.0, f"{prob_color} {prob_val:.0f}% YES likelihood")
            
            st.divider()
            
            # Outcome probabilities as business decision points
            if outcomes and prices:
                st.write("**Outcome Probabilities:**")
                
                for outcome, price in zip(outcomes, prices):
                    prob_pct = float(price) * 100
                    col_label, col_bar = st.columns([1, 4])
                    
                    with col_label:
                        st.write(f"**{outcome}**")
                    
                    with col_bar:
                        st.progress(float(price), f"{prob_pct:.1f}%")
    
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

