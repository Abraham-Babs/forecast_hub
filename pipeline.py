#!/usr/bin/env python
"""
Polymarket BI - Async Data Pipeline
Fetches markets from Polymarket and Kalshi APIs concurrently, detects duplicates by question similarity,
and stores in SQLite. Each refresh UPSERTs current markets and deletes resolved ones (current-state only).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "Markets_database.db")


import re


def extract_numeric_tokens(text: str) -> set:
    """Extract numbers, percentages, and unit values from text."""
    return set(re.findall(r'\b\d+(?:\.\d+)?(?:%|k|m|b|bps)?\b', text.lower()))


def extract_clean_tokens(text: str) -> set:
    """Normalize text into core semantic words, removing common filler."""
    stop_words = {
        "will", "the", "a", "an", "in", "by", "of", "to", "for", "on", "at", "be", 
        "is", "are", "or", "and", "if", "there", "before", "after", "end", "any", 
        "this", "market", "resolve", "yes", "no"
    }
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return {w for w in words if w not in stop_words and len(w) > 1}


def are_contracts_matching(q1: str, q2: str) -> bool:
    """
    Check if two contracts from different platforms represent the exact same event.
    Applies a strict parameter guardrail to prevent false matches across different numbers.
    """
    # Parameter guardrail: If both contain numbers/targets, they must not conflict
    nums1 = extract_numeric_tokens(q1)
    nums2 = extract_numeric_tokens(q2)
    if nums1 and nums2:
        if not (nums1 & nums2):
            return False  # Distinct numeric targets (e.g. 2% vs 3%)

    tokens1 = extract_clean_tokens(q1)
    tokens2 = extract_clean_tokens(q2)
    if not tokens1 or not tokens2:
        return False

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    jaccard = len(intersection) / len(union)
    seq_ratio = SequenceMatcher(None, q1.lower(), q2.lower()).ratio()

    return jaccard >= 0.50 or seq_ratio >= 0.72


def find_duplicate_groups(markets: list) -> dict:
    """
    Assign duplicate_group_id to cross-platform overlapping contracts.
    Only pairs markets from different sources where both topic and exact parameters agree.
    """
    groups = {}  # market_id -> group_id
    group_id = 0
    
    for i, m1 in enumerate(markets):
        if m1['id'] in groups:
            continue
        
        for m2 in markets[i+1:]:
            if m2['id'] in groups:
                continue
            
            # Cross-platform pairing only
            if m1.get('source') == m2.get('source'):
                continue
            
            q1 = m1.get('question') or ""
            q2 = m2.get('question') or ""
            
            if are_contracts_matching(q1, q2):
                groups[m1['id']] = group_id
                groups[m2['id']] = group_id
                logger.info(f"Grouped match: {m1.get('source')} <-> {m2.get('source')} | '{q1[:45]}' <-> '{q2[:45]}'")
                group_id += 1
                break
    
    return groups


def cluster_topic_titles(markets: list) -> None:
    """
    Tier 1 Topic Clustering: Unifies topic titles across platforms for related events
    (e.g., all Federal Reserve rate strikes or recession questions share an umbrella topic).
    """
    topics = []
    for m in markets:
        raw_topic = m.get('topic_title') or m.get('question') or "General Forecasts"
        # Clean up question marks or boilerplate
        clean_topic = raw_topic.strip().rstrip('?')
        m['topic_title'] = clean_topic
        topics.append(clean_topic)


async def main():
    """Run data pipeline: fetch from both Polymarket and Kalshi concurrently → detect duplicates → store.
    
    Flow:
    1. Import fetchers (polymarket_api, kalshi_api)
    2. Fetch from both APIs concurrently using asyncio.gather()
    3. Handle individual fetch failures gracefully (if one fails, other still proceeds)
    4. Tag each market with source: 'polymarket' or 'kalshi'
    5. Combine market lists
    6. Call insert_markets() which detects duplicates by question similarity and UPSERTs to database
    7. Delete any markets not in current fetch (resolved/delisted)
    
    Cache fallback: If both APIs fail and no markets fetched, try to serve database cache instead of failing.
    """
    logger.info("Starting pipeline...")
    
    try:
        # Import fetchers
        from fetchers.polymarket_api import fetch_all_markets as fetch_polymarket
        from fetchers.kalshi_api import fetch_all_markets as fetch_kalshi
        
        # Fetch from both sources concurrently
        logger.info("Fetching from Polymarket and Kalshi...")
        pm_markets, k_markets = await asyncio.gather(
            fetch_polymarket(),
            fetch_kalshi(),
            return_exceptions=True
        )
        
        # Handle exceptions from individual fetches
        if isinstance(pm_markets, Exception):
            logger.error(f"Polymarket fetch failed: {pm_markets}")
            pm_markets = []
        
        if isinstance(k_markets, Exception):
            logger.error(f"Kalshi fetch failed: {k_markets}")
            k_markets = []
        
        # Tag each market with its source
        for m in pm_markets:
            m['source'] = 'polymarket'
        for m in k_markets:
            m['source'] = 'kalshi'
        
        # Combine markets from both sources
        markets = pm_markets + k_markets
        logger.info(f"Fetched {len(pm_markets)} Polymarket + {len(k_markets)} Kalshi = {len(markets)} total")
        
        if not markets:
            logger.warning("No markets fetched from either source. Checking cache...")
            db = DatabaseManager()
            db.connect()
            cached = db.load_cached_markets()
            db.close()
            if cached:
                logger.info(f"Serving {len(cached)} cached markets")
                return 0
            else:
                logger.error("No cached markets available")
                return 1
        
        # Store in database
        db = DatabaseManager()
        db.connect()
        db.init_schema()
        
        # Tier 1: Cluster topics across markets
        cluster_topic_titles(markets)

        # Tier 2: Detect exact contract matches
        duplicate_groups = find_duplicate_groups(markets)
        db.insert_markets(markets, duplicate_groups)
        db.close()
        
        logger.info(f"Pipeline completed: {len(markets)} markets stored")
        return 0
        
    except Exception as e:
        logger.error(f"Pipeline failed: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    asyncio.run(main())
