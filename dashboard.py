#!/usr/bin/env python
"""
Polymarket BI - Dashboard Entry Point
Streamlit dashboard for visualizing prediction market data.
Run with: streamlit run dashboard.py
"""

import sys
import os
import asyncio

# Ensure database can be found
if not os.path.exists("polymarket_bi.db"):
    # Try from src directory
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..")):
        os.chdir(os.path.dirname(__file__) or ".")

# Now import and run the dashboard
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import json

# Import pipeline for data fetching
from pipeline import main as fetch_data

# Page configuration
st.set_page_config(
    page_title="Polymarket BI Dashboard",
    page_icon="📊",
    layout="wide"
)

# Initialize sidebar with controls
st.sidebar.header("📥 Data Management")

# Volume threshold slider
min_volume = st.sidebar.slider(
    "Minimum Volume Threshold ($)",
    min_value=1000,
    max_value=1000000,
    value=100000,
    step=10000,
    help="Only fetch and display markets with volume >= this value"
)

# Fetch button
if st.sidebar.button("🔄 Fetch Market Data", key="fetch_button"):
    with st.spinner(f"Fetching markets with min volume ${min_volume:,.0f}..."):
        try:
            asyncio.run(fetch_data(min_volume))
            st.sidebar.success("✓ Data fetched successfully!")
        except Exception as e:
            st.sidebar.error(f"Error fetching data: {e}")

def get_db_connection():
    """Create fresh database connection."""
    conn = sqlite3.connect("polymarket_bi.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def load_markets():
    """Load all markets from database."""
    conn = get_db_connection()
    query = """
    SELECT DISTINCT
        m.id,
        m.question,
        m.liquidity,
        m.volume,
        m.end_date,
        m.active,
        m.outcomes,
        m.outcome_prices,
        m.probability
    FROM markets m
    ORDER BY m.liquidity DESC
    """
    df = pd.read_sql_query(query, conn)
    df['end_date'] = pd.to_datetime(df['end_date'], format='ISO8601', utc=True)
    conn.close()
    return df

def parse_outcome_prices(prices_json):
    """Parse JSON string of outcome prices."""
    try:
        return json.loads(prices_json)
    except:
        return []

# Main dashboard
st.title("📊 Polymarket Business Intelligence Dashboard")

# Load data
df = load_markets()

if len(df) == 0:
    st.warning("No data in database. Run: uv run ingest.py")
    st.stop()

# Key metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Markets", len(df))

with col2:
    st.metric("Avg Liquidity", f"${df['liquidity'].mean():,.0f}")

with col3:
    st.metric("Total Volume", f"${df['volume'].sum():,.0f}")

with col4:
    st.metric("Active Markets", df['active'].sum())

st.divider()

# Sidebar search filter
with st.sidebar:
    st.header("🔍 Search")
    search_term = st.text_input("Search markets", placeholder="e.g., Bitcoin, election")

# Apply search filter
df_filtered = df.copy()
if search_term:
    df_filtered = df_filtered[df_filtered['question'].str.contains(search_term, case=False, na=False)]

# Charts
st.subheader("Market Analysis")

col1, col2 = st.columns(2)

with col1:
    fig_liquidity = px.histogram(
        df_filtered,
        x="liquidity",
        nbins=20,
        title="Liquidity Distribution",
        labels={"liquidity": "Liquidity ($)"}
    )
    st.plotly_chart(fig_liquidity, use_container_width=True)

with col2:
    fig_scatter = px.scatter(
        df_filtered,
        x="liquidity",
        y="volume",
        hover_data=["question"],
        title="Volume vs Liquidity",
        labels={"liquidity": "Liquidity ($)", "volume": "Volume ($)"}
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# Market list
st.subheader(f"Markets ({len(df_filtered)} found)")

for idx, row in df_filtered.iterrows():
    prices = parse_outcome_prices(row['outcome_prices'])
    outcomes = parse_outcome_prices(row['outcomes']) if row['outcomes'] else []
    
    with st.expander(f"{row['question'][:80]}... | 📊 {row['probability']:.1f}%"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write(f"**ID:** {row['id']}")
            st.write(f"**Liquidity:** ${row['liquidity']:,.0f}")
        
        with col2:
            end_date_str = row['end_date'].strftime('%Y-%m-%d') if pd.notna(row['end_date']) else 'N/A'
            st.write(f"**Volume:** ${row['volume']:,.0f}")
            st.write(f"**End Date:** {end_date_str}")
        
        with col3:
            status = "🟢 Active" if row['active'] else "🔴 Inactive"
            st.write(f"**Status:** {status}")
            st.write(f"**Yes Probability:** {row['probability']:.1f}%")
        
        st.divider()
        
        # Show outcome details
        if outcomes and prices:
            outcome_df = pd.DataFrame({
                'Outcome': outcomes,
                'Price': prices,
                'Probability (%)': [p * 100 for p in prices]
            })
            st.dataframe(outcome_df, use_container_width=True, hide_index=True)

st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total markets in DB: {len(df)}")
