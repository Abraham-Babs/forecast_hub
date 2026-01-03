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


def find_duplicate_groups(markets: list, threshold: float = 0.85) -> dict:
    """
    Find overlapping markets (same question on different platforms).
    Only creates a group if markets have ≥85% similar questions AND come from different sources.
    Each overlap group will have exactly one market from Polymarket and one from Kalshi.
    
    Args:
        markets: List of market dicts with 'id', 'question', and 'source' keys
        threshold: Similarity threshold (0-1); default 0.85 = 85% match
    
    Returns:
        Dict mapping market_id -> group_id. Only includes markets that overlap across platforms.
        Example: {poly_market_id: 0, kalshi_market_id: 0} = same question on both platforms
    """
    groups = {}  # market_id -> group_id
    group_id = 0
    
    for i, m1 in enumerate(markets):
        if m1['id'] in groups:
            continue
        
        # Find matches from DIFFERENT platforms only
        for m2 in markets[i+1:]:
            if m2['id'] in groups:
                continue
            
            # Skip if same platform
            if m1['source'] == m2['source']:
                continue
            
            # Check question similarity
            ratio = SequenceMatcher(None, m1['question'].lower(), m2['question'].lower()).ratio()
            if ratio >= threshold:
                # Found an overlap: same question, different platforms
                groups[m1['id']] = group_id
                groups[m2['id']] = group_id
                logger.info(f"Found overlap: {m1['source']} ↔ {m2['source']} | {m1['question'][:60]}...")
                group_id += 1
                break  # m1 matched, move to next
    
    return groups


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
        
        # Detect duplicates
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
