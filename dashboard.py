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
from datetime import datetime
import json

# Ensure database can be found
if not os.path.exists("polymarket_bi.db"):
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..")):
        os.chdir(os.path.dirname(__file__) or ".")

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Polymarket BI Dashboard",
    page_icon="📊",
    layout="wide"
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db_connection():
    """Create fresh database connection."""
    conn = sqlite3.connect("polymarket_bi.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_max_open_interest():
    """Get maximum open interest value from database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(open_interest) FROM markets WHERE open_interest > 0")
        result = cursor.fetchone()
        conn.close()
        return int(result[0]) if result[0] else 500_000_000
    except:
        return 500_000_000

def load_markets():
    """Load all markets from database."""
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
    df['end_date'] = pd.to_datetime(df['end_date'], format='ISO8601', utc=True)
    df['end_date'] = pd.to_datetime(df['end_date'], format='ISO8601', utc=True)
    conn.close()
    return df

def parse_json_field(json_str):
    """Parse JSON string safely."""
    try:
        return json.loads(json_str) if json_str else []
    except:
        return []

# ============================================================================
# SIDEBAR CONTROLS
# ============================================================================

st.sidebar.header("🎚️ Open Interest Filter")

# Get max open interest from database
max_open_interest = get_max_open_interest()
open_interest_step = max(1000, max_open_interest // 100)

# Open Interest threshold slider
min_open_interest = st.sidebar.slider(
    "Minimum Open Interest ($)",
    min_value=50_000,
    max_value=max_open_interest,
    value=200_000,
    step=open_interest_step,
    format="$%d",
    help="Only show markets with open interest >= this value"
)

st.sidebar.divider()

# Glossary
with st.sidebar.expander("ℹ️ About This Dashboard"):
    st.write("""
**Open Interest**: Total USD value of all outstanding/active contracts in a market. 
Higher open interest indicates more trading activity and market interest.

**Probability**: Implied probability that the "Yes" outcome will occur, based on 
current market prices.

**Volume**: Total USD value of contracts traded in this market.
""")

# ============================================================================
# MAIN DASHBOARD
# ============================================================================

st.title("📊 Polymarket Business Intelligence Dashboard")

# Load data
df = load_markets()

if len(df) == 0:
    st.warning("No data in database. Please run the data pipeline.")
    st.stop()

# Filter by open interest threshold
df_filtered = df[df['open_interest'] >= min_open_interest].copy()

# ============================================================================
# KEY METRICS
# ============================================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Markets", len(df_filtered))

with col2:
    avg_oi = df_filtered['open_interest'].mean() if len(df_filtered) > 0 else 0
    st.metric("Average Open Interest", f"${avg_oi:,.0f}")

with col3:
    total_oi = df_filtered['open_interest'].sum() if len(df_filtered) > 0 else 0
    st.metric("Total Open Interest", f"${total_oi:,.0f}")

with col4:
    active_count = int(df_filtered['active'].sum()) if len(df_filtered) > 0 else 0
    st.metric("Active Markets", active_count)

st.divider()

# ============================================================================
# SEARCH
# ============================================================================

search_term = st.text_input(
    "🔍 Search markets by keyword",
    placeholder="e.g., Bitcoin, election, inflation..."
)

if search_term:
    df_filtered = df_filtered[
        df_filtered['question'].str.contains(search_term, case=False, na=False)
    ]

st.divider()

# ============================================================================
# VISUALIZATIONS
# ============================================================================

st.subheader("Market Analysis")

if len(df_filtered) > 0:
    col1, col2 = st.columns(2)
    
    with col1:
        fig_histogram = px.histogram(
            df_filtered,
            x="open_interest",
            nbins=20,
            title="Open Interest Distribution",
            labels={"open_interest": "Open Interest ($)"}
        )
        st.plotly_chart(fig_histogram, use_container_width=True)
    
    with col2:
        fig_scatter = px.scatter(
            df_filtered,
            x="open_interest",
            y="volume",
            hover_data=["question"],
            title="Volume vs Open Interest",
            labels={
                "open_interest": "Open Interest ($)",
                "volume": "Volume ($)"
            }
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# ============================================================================
# MARKET LIST
# ============================================================================

st.subheader(f"Markets ({len(df_filtered)} found)")

if len(df_filtered) == 0:
    st.info("No markets match your filters. Try adjusting the open interest threshold.")
else:
    for idx, row in df_filtered.iterrows():
        prices = parse_json_field(row['outcome_prices'])
        outcomes = parse_json_field(row['outcomes'])
        
        # Market expander
        with st.expander(f"{row['question'][:70]}... | {row['probability']:.1f}%"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Market ID:**\n`{row['id']}`")
                st.write(f"**Condition ID:**\n`{row['condition_id']}`")
            
            with col2:
                st.write(f"**Open Interest:**\n${row['open_interest']:,.0f}")
                st.write(f"**Volume:**\n${row['volume']:,.0f}")
            
            with col3:
                status = "🟢 Active" if row['active'] else "🔴 Inactive"
                end_date = row['end_date'].strftime('%Y-%m-%d') if pd.notna(row['end_date']) else 'N/A'
                st.write(f"**Status:** {status}")
                st.write(f"**End Date:** {end_date}")
            
            # Outcome probabilities table
            if outcomes and prices:
                st.divider()
                outcome_df = pd.DataFrame({
                    'Outcome': outcomes,
                    'Price': prices,
                    'Probability (%)': [p * 100 for p in prices]
                })
                st.dataframe(outcome_df, use_container_width=True, hide_index=True)

st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total markets in database: {len(df)}")
