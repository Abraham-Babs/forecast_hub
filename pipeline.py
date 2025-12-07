#!/usr/bin/env python
"""
Polymarket BI - Async Data Pipeline
Fetches markets from Polymarket API, normalizes, validates, and stores in SQLite.
"""

import asyncio
import json
import sqlite3
import logging
from datetime import datetime
from typing import Any
import aiohttp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_BASE = "https://gamma-api.polymarket.com/markets"

# Business-relevant prediction market categories with Polymarket tag_ids
# From README: 13 categories with specific tag_id values
CATEGORIES = {
    "business": 107,
    "business_news": 100039,
    "crypto": 21,
    "politics": 2,
    "tech": 1401,
    "finance": 120,
    "economy": 100328,
    "stocks": 604,
    "market_cap": 1095,
    "banking": 100040,
    "prices": 1384,
    "financial_forecast": 619,
    "unemployment": 1624,
}


class DataNormalizer:
    """Validate and normalize market data."""
    
    @staticmethod
    def validate_volume(volume: float, min_volume: float = 100000) -> bool:
        """Ensure minimum volume threshold."""
        try:
            vol = float(volume) if volume else 0
            return vol >= min_volume
        except:
            return False
    
    @staticmethod
    def validate_outcome_prices(outcome_prices: Any) -> bool:
        """Ensure outcome_prices is valid JSON array with decimals 0-1."""
        try:
            if isinstance(outcome_prices, str):
                prices = json.loads(outcome_prices)
            else:
                prices = outcome_prices
            
            if not isinstance(prices, list) or len(prices) == 0:
                return False
            
            # Prices can be numbers or strings - convert to float and validate range
            for p in prices:
                try:
                    float_p = float(p)
                    if not (0 <= float_p <= 1):
                        return False
                except (ValueError, TypeError):
                    return False
            
            return True
        except:
            return False
    
    @staticmethod
    def normalize(market: dict, min_volume: float = 100000) -> dict | None:
        """Normalize and validate a single market."""
        # Extract required fields
        end_date = market.get('endDate') or market.get('end_date')
        # API can have liquidity or liquidityAmm
        liquidity = float(market.get('liquidity') or market.get('liquidityAmm', 0) or 0)
        volume = float(market.get('volume', 0) or 0)
        condition_id = market.get('conditionId')
        outcome_prices = market.get('outcomePrices') or market.get('outcome_prices')
        outcomes = market.get('outcomes')
        
        # Validate fields - filter by volume instead of liquidity
        if not DataNormalizer.validate_volume(volume, min_volume):
            return None
        if not DataNormalizer.validate_outcome_prices(outcome_prices):
            return None
        if not condition_id:
            return None
        
        # Ensure outcome_prices is stored as JSON string
        if isinstance(outcome_prices, list):
            outcome_prices_list = outcome_prices
            outcome_prices_str = json.dumps(outcome_prices)
        else:
            outcome_prices_str = outcome_prices
            outcome_prices_list = json.loads(outcome_prices)
        
        # Ensure outcomes is stored as JSON string
        if isinstance(outcomes, list):
            outcomes_str = json.dumps(outcomes)
            outcomes_list = outcomes
        else:
            outcomes_str = outcomes
            outcomes_list = json.loads(outcomes) if outcomes else []
        
        # Calculate probability as "Yes" outcome price in percent
        # The outcomes array is positionally mapped to outcome_prices
        # e.g., ["Yes", "No"] with [0.25, 0.75] means Yes=25%, No=75%
        probability = 0.0
        if outcomes_list and outcome_prices_list:
            try:
                yes_index = outcomes_list.index("Yes")
                probability = float(outcome_prices_list[yes_index]) * 100
            except (ValueError, IndexError):
                # If "Yes" not found, default to 0
                probability = 0.0
        
        return {
            'id': market.get('id'),
            'question': market.get('question'),
            'condition_id': condition_id,
            'liquidity': liquidity,
            'volume': market.get('volume', 0),
            'end_date': end_date,
            'active': market.get('active', True),
            'outcomes': outcomes_str,
            'outcome_prices': outcome_prices_str,
            'probability': probability,
        }


class PolymarketPoller:
    """Async fetcher for Polymarket API."""
    
    @staticmethod
    async def fetch_category(session: aiohttp.ClientSession, category: str, tag_id: int, min_volume: float = 100000) -> list:
        """Fetch markets for a single category."""
        try:
            params = {
                "tag_id": tag_id,
                "closed": "false",
                "limit": 300,
            }
            async with session.get(API_BASE, params=params) as resp:
                if resp.status == 200:
                    markets = await resp.json()
                    normalized = []
                    for m in markets:
                        norm = DataNormalizer.normalize(m, min_volume)
                        if norm:
                            normalized.append(norm)
                    logger.info(f"{category} (tag_id={tag_id}): fetched {len(normalized)} valid markets")
                    return normalized
                else:
                    logger.warning(f"{category}: HTTP {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"{category}: {e}")
            return []
    
    @staticmethod
    async def fetch_all_categories(min_volume: float = 100000) -> list:
        """Fetch all categories concurrently."""
        async with aiohttp.ClientSession() as session:
            tasks = [
                PolymarketPoller.fetch_category(session, cat, tag_id, min_volume)
                for cat, tag_id in CATEGORIES.items()
            ]
            results = await asyncio.gather(*tasks)
            
        # Flatten and deduplicate by market ID
        all_markets = []
        seen_ids = set()
        for result in results:
            for market in result:
                if market['id'] not in seen_ids:
                    all_markets.append(market)
                    seen_ids.add(market['id'])
        
        return all_markets


class DatabaseManager:
    """SQLite database operations."""
    
    def __init__(self, db_path: str = "polymarket_bi.db"):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        logger.info(f"Connected to SQLite database: {self.db_path}")
    
    def init_schema(self):
        """Create tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Sources table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                api_endpoint TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Markets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS markets (
                id TEXT PRIMARY KEY,
                source_id INTEGER,
                question TEXT,
                condition_id TEXT,
                liquidity REAL,
                volume REAL,
                end_date TEXT,
                active BOOLEAN,
                outcomes TEXT,
                outcome_prices TEXT NOT NULL,
                probability REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            )
        """)
        
        # Snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY,
                market_id TEXT,
                question TEXT,
                outcome_prices TEXT,
                volume REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(market_id) REFERENCES markets(id)
            )
        """)
        
        # Insert Polymarket source
        cursor.execute("""
            INSERT OR IGNORE INTO sources (name, api_endpoint)
            VALUES (?, ?)
        """, ("Polymarket", API_BASE))
        
        self.conn.commit()
        logger.info("Database schema initialized")
    
    def insert_markets(self, markets: list) -> tuple:
        """UPSERT markets and snapshots. Returns (new_count, updated_count)."""
        cursor = self.conn.cursor()
        
        # Get source ID
        cursor.execute("SELECT id FROM sources WHERE name = ?", ("Polymarket",))
        source_id = cursor.fetchone()[0]
        
        new_count = 0
        updated_count = 0
        
        for market in markets:
            cursor.execute("""
                INSERT INTO markets (id, source_id, question, condition_id, liquidity, volume, end_date, active, outcomes, outcome_prices, probability)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    liquidity = excluded.liquidity,
                    volume = excluded.volume,
                    outcomes = excluded.outcomes,
                    outcome_prices = excluded.outcome_prices,
                    probability = excluded.probability
            """, (
                market['id'],
                source_id,
                market['question'],
                market['condition_id'],
                market['liquidity'],
                market['volume'],
                market['end_date'],
                market['active'],
                market['outcomes'],
                market['outcome_prices'],
                market['probability'],
            ))
            
            if cursor.rowcount == 1:
                new_count += 1
            else:
                updated_count += 1
            
            # Insert snapshot
            cursor.execute("""
                INSERT INTO snapshots (market_id, question, outcome_prices, volume)
                VALUES (?, ?, ?, ?)
            """, (
                market['id'],
                market['question'],
                market['outcome_prices'],
                market['volume'],
            ))
        
        self.conn.commit()
        return new_count, updated_count
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


async def main(min_volume: float = 100000):
    """Run the entire ingestion pipeline."""
    logger.info(f"Starting Polymarket BI ingestion pipeline (min_volume=${min_volume:,.0f})...")
    
    # Fetch markets
    markets = await PolymarketPoller.fetch_all_categories(min_volume)
    logger.info(f"Total valid markets fetched: {len(markets)}")
    
    # Store in database
    db = DatabaseManager()
    db.connect()
    db.init_schema()
    new, updated = db.insert_markets(markets)
    logger.info(f"Database: {new} new markets, {updated} updated")
    db.close()
    
    logger.info("Ingestion pipeline completed")


if __name__ == "__main__":
    asyncio.run(main())
