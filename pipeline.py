#!/usr/bin/env python
"""
Polymarket BI - Async Data Pipeline
Fetches markets from Polymarket API, normalizes, validates, and stores in SQLite.
"""

import asyncio
import json
import sqlite3
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from functools import wraps
from dotenv import load_dotenv
import aiohttp

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration from environment
API_BASE = os.getenv("API_BASE_URL", "https://gamma-api.polymarket.com/markets")
OI_API_BASE = os.getenv("OI_API_BASE_URL", "https://data-api.polymarket.com/oi")
DATABASE_PATH = os.getenv("DATABASE_PATH", "polymarket_bi.db")
API_TIMEOUT = int(os.getenv("API_TIMEOUT_SECONDS", "10"))
# OI endpoint needs longer timeout because it fetches for ALL markets sequentially
# Increased from 3s to 8s to ensure complete data retrieval on each market
OI_API_TIMEOUT = int(os.getenv("OI_API_TIMEOUT_SECONDS", "8"))
API_RATE_LIMIT_PER_HOST = int(os.getenv("API_RATE_LIMIT_PER_HOST", "20"))
API_RATE_LIMIT_TOTAL = int(os.getenv("API_RATE_LIMIT_TOTAL", "200"))

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
        except (ValueError, TypeError) as e:
            logger.debug(f"Volume validation error: {e}")
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
                except (ValueError, TypeError) as e:
                    logger.debug(f"Outcome price conversion error: {e}")
                    return False
            
            return True
        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode error in outcome_prices: {e}")
            return False
        except Exception as e:
            logger.debug(f"Unexpected error validating outcome prices: {e}")
            return False
    
    @staticmethod
    def validate_outcomes_and_prices_match(outcomes: Any, outcome_prices: Any) -> bool:
        """Ensure outcomes and outcome_prices arrays have matching lengths."""
        try:
            # Parse outcomes
            if isinstance(outcomes, str):
                outcomes_list = json.loads(outcomes) if outcomes else []
            else:
                outcomes_list = outcomes if outcomes else []
            
            # Parse prices
            if isinstance(outcome_prices, str):
                prices_list = json.loads(outcome_prices) if outcome_prices else []
            else:
                prices_list = outcome_prices if outcome_prices else []
            
            # Both must be non-empty and equal length
            if not outcomes_list or not prices_list:
                return False
            
            if len(outcomes_list) != len(prices_list):
                logger.debug(
                    f"Outcomes/prices mismatch: {len(outcomes_list)} outcomes vs "
                    f"{len(prices_list)} prices"
                )
                return False
            
            return True
        except Exception as e:
            logger.debug(f"Error validating outcomes/prices match: {e}")
            return False
    
    @staticmethod
    def validate_open_interest(oi: float, min_oi: float = 50000) -> bool:
        """Ensure minimum open interest threshold."""
        try:
            oi_val = float(oi) if oi else 0
            return oi_val >= min_oi
        except (ValueError, TypeError) as e:
            logger.debug(f"Open interest validation error: {e}")
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
        
        # Validate that outcomes and prices match in length
        if not DataNormalizer.validate_outcomes_and_prices_match(outcomes, outcome_prices):
            logger.debug(f"Market {market.get('id')}: outcomes/prices mismatch")
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
        probability = None
        if outcomes_list and outcome_prices_list:
            try:
                yes_index = outcomes_list.index("Yes")
                probability = float(outcome_prices_list[yes_index]) * 100
            except (ValueError, IndexError):
                # If "Yes" not found, use first outcome (for non-binary markets)
                # or reject the market as invalid during database insert
                logger.debug(
                    f"Market {market.get('id')}: 'Yes' outcome not found in {outcomes_list}. "
                    f"Using first outcome price instead."
                )
                try:
                    probability = float(outcome_prices_list[0]) * 100
                except (ValueError, IndexError, TypeError):
                    # Completely invalid; will be caught during validation
                    probability = None
        
        # If probability is None, the market lacks valid outcome data
        if probability is None:
            return None
        
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
            'open_interest': None,
        }


class PolymarketPoller:
    """Async fetcher for Polymarket API."""
    
    @staticmethod
    async def fetch_open_interest(session: aiohttp.ClientSession, condition_id: str) -> float | None:
        """Fetch open interest for a market by condition ID."""
        try:
            params = {"market": condition_id}
            # Use OI_API_TIMEOUT (8s) instead of 3s - OI fetch is slower due to sequential nature
            async with session.get(OI_API_BASE, params=params, timeout=aiohttp.ClientTimeout(total=OI_API_TIMEOUT)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # OI endpoint returns a list with one dict containing 'value'
                    if isinstance(data, list) and len(data) > 0:
                        oi = data[0].get('value')
                        if oi is not None:
                            return float(oi)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        return None
    
    @staticmethod
    async def fetch_category(session: aiohttp.ClientSession, category: str, tag_id: int, min_volume: float = 100000) -> list:
        """Fetch markets for a single category (raw, without OI filtering)."""
        try:
            params = {
                "tag_id": tag_id,
                "closed": "false",
                "limit": 300,
            }
            async with session.get(API_BASE, params=params, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as resp:
                if resp.status == 200:
                    markets = await resp.json()
                    normalized = []
                    for m in markets:
                        norm = DataNormalizer.normalize(m, min_volume)
                        if norm:
                            norm['category'] = category  # Add category tracking
                            normalized.append(norm)
                    logger.info(f"{category} (tag_id={tag_id}): fetched {len(normalized)} valid markets")
                    return normalized
                else:
                    logger.warning(f"{category}: HTTP {resp.status}")
                    return []
        except asyncio.TimeoutError:
            logger.error(f"{category}: Request timeout after {API_TIMEOUT}s")
            return []
        except aiohttp.ClientError as e:
            logger.error(f"{category}: HTTP client error - {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"{category}: Invalid JSON response - {e}")
            return []
        except Exception as e:
            logger.error(f"{category}: Unexpected error - {type(e).__name__}: {e}")
            return []
    
    @staticmethod
    async def fetch_all_categories(min_volume: float = 100000, min_oi: float = 50000) -> list:
        """Fetch all categories concurrently, then filter by OI across all markets."""
        connector = aiohttp.TCPConnector(limit_per_host=API_RATE_LIMIT_PER_HOST, limit=API_RATE_LIMIT_TOTAL)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Step 1: Fetch all category markets in parallel
            tasks = [
                PolymarketPoller.fetch_category(session, cat, tag_id, min_volume)
                for cat, tag_id in CATEGORIES.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            all_markets = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    category = list(CATEGORIES.keys())[i]
                    logger.error(f"Failed to fetch category {category}: {result}")
                else:
                    all_markets.extend(result)
            
            # Step 2: Fetch OI for ALL markets in parallel with proper indexing
            markets_with_oi = [m for m in all_markets if m.get('condition_id')]
            oi_tasks = [
                PolymarketPoller.fetch_open_interest(session, m.get('condition_id'))
                for m in markets_with_oi
            ]
            oi_values = await asyncio.gather(*oi_tasks, return_exceptions=True)
            
            # Step 3: Attach OI and filter by threshold (explicit indexing to avoid mismatch)
            filtered = []
            skipped_count = 0
            failed_oi_count = 0
            
            for market, oi_result in zip(markets_with_oi, oi_values):
                if isinstance(oi_result, Exception):
                    failed_oi_count += 1
                    logger.debug(f"Failed to fetch OI for market {market.get('id')}: {oi_result}")
                    continue
                
                oi = oi_result
                if oi is not None and DataNormalizer.validate_open_interest(oi, min_oi):
                    market['open_interest'] = oi
                    filtered.append(market)
                else:
                    skipped_count += 1
                    logger.debug(f"Market {market.get('id')} skipped: OI ${oi} below threshold ${min_oi}")
            
            # Log summary of OI filtering results
            if failed_oi_count > 0:
                logger.warning(
                    f"[OI FETCH] {failed_oi_count} markets had OI fetch failures "
                    f"(will retry on next refresh)"
                )
            if skipped_count > 0:
                logger.info(
                    f"[OI FILTER] {skipped_count} markets filtered out (OI < ${min_oi:,.0f})"
                )
            
            # Add markets without OI (may not have OI data available)
            markets_without_oi = [m for m in all_markets if not m.get('condition_id')]
            if markets_without_oi:
                logger.info(f"[NO CONDITION_ID] {len(markets_without_oi)} markets have no condition_id (OI unavailable)")
            filtered.extend(markets_without_oi)
            
            logger.info(
                f"[FINAL RESULTS] {len(filtered)} markets pass all filters "
                f"(from {len(all_markets)} fetched)"
            )
            
            return filtered


def retry_on_db_lock(max_retries: int = 3, initial_delay: float = 0.1):
    """Decorator to retry database operations on lock with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        last_error = e
                        if attempt < max_retries - 1:
                            logger.warning(f"[DB LOCK] Attempt {attempt + 1}/{max_retries}: retrying in {delay:.2f}s")
                            time.sleep(delay)
                            delay *= 2  # Exponential backoff
                        continue
                    raise
                except Exception:
                    raise
            # If all retries exhausted, raise last error
            logger.error(f"[DB LOCK] Failed after {max_retries} attempts: {last_error}")
            raise last_error
        return wrapper
    return decorator


class DatabaseManager:
    """SQLite database operations with concurrency handling."""
    
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DATABASE_PATH
        self.conn = None
    
    def connect(self):
        """Connect to database with concurrency handling."""
        # Set timeout to 10 seconds for concurrent access
        self.conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read/write performance
        self.conn.execute('PRAGMA journal_mode=WAL')
        # Increase cache size for better performance
        self.conn.execute('PRAGMA cache_size=-64000')
        logger.info(f"Connected to SQLite database (WAL mode, 10s timeout): {self.db_path}")
    
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
                open_interest REAL,
                end_date TEXT,
                active BOOLEAN,
                outcomes TEXT,
                outcome_prices TEXT NOT NULL,
                probability REAL,
                category TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            )
        """)
        
        # Watchlist table (user favorites)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT UNIQUE NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(market_id) REFERENCES markets(id) ON DELETE CASCADE
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
                probability REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(market_id) REFERENCES markets(id)
            )
        """)
        
        # Metadata table (tracks last refresh, counts, etc)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add missing columns to existing tables (schema migration)
        try:
            cursor.execute("ALTER TABLE markets ADD COLUMN category TEXT")
            logger.info("Added 'category' column to markets table")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            cursor.execute("ALTER TABLE snapshots ADD COLUMN probability REAL")
            logger.info("Added 'probability' column to snapshots table")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Insert Polymarket source
        cursor.execute("""
            INSERT OR IGNORE INTO sources (name, api_endpoint)
            VALUES (?, ?)
        """, ("Polymarket", API_BASE))
        
        # Create indexes for fast filtering queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_probability ON markets(probability)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_open_interest ON markets(open_interest)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_end_date ON markets(end_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_active ON markets(active)")
        
        self.conn.commit()
        logger.info("Database schema initialized")
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def insert_markets(self, markets: list) -> tuple:
        """UPSERT markets and snapshots. Returns (new_count, updated_count). Retries on DB lock."""
        cursor = self.conn.cursor()
        
        # Get source ID
        cursor.execute("SELECT id FROM sources WHERE name = ?", ("Polymarket",))
        source_id = cursor.fetchone()[0]
        
        new_count = 0
        updated_count = 0
        
        for market in markets:
            # Check if market already exists
            cursor.execute("SELECT id FROM markets WHERE id = ?", (market['id'],))
            exists = cursor.fetchone() is not None
            
            cursor.execute("""
                INSERT INTO markets (id, source_id, question, condition_id, liquidity, volume, open_interest, end_date, active, outcomes, outcome_prices, probability, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    liquidity = excluded.liquidity,
                    volume = excluded.volume,
                    open_interest = excluded.open_interest,
                    outcomes = excluded.outcomes,
                    outcome_prices = excluded.outcome_prices,
                    probability = excluded.probability,
                    category = excluded.category
            """, (
                market['id'],
                source_id,
                market['question'],
                market['condition_id'],
                market['liquidity'],
                market['volume'],
                market['open_interest'],
                market['end_date'],
                market['active'],
                market['outcomes'],
                market['outcome_prices'],
                market['probability'],
                market.get('category'),
            ))
            
            if exists:
                updated_count += 1
            else:
                new_count += 1
            
            # Insert snapshot
            cursor.execute("""
                INSERT INTO snapshots (market_id, question, outcome_prices, volume, probability)
                VALUES (?, ?, ?, ?, ?)
            """, (
                market['id'],
                market['question'],
                market['outcome_prices'],
                market['volume'],
                market['probability'],
            ))
        
        # Record last refresh timestamp
        cursor.execute("""
            INSERT OR REPLACE INTO metadata (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, ("last_refresh", datetime.now(timezone.utc).isoformat()))
        
        self.conn.commit()
        logger.info(f"Recorded refresh timestamp: {new_count} new, {updated_count} updated")
        return new_count, updated_count
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def purge_inactive_market_snapshots(self) -> int:
        """Delete snapshots for markets that are no longer active. Returns count of deleted snapshots."""
        try:
            cursor = self.conn.cursor()
            
            # Find inactive markets
            cursor.execute("SELECT id FROM markets WHERE active = 0")
            inactive_ids = [row[0] for row in cursor.fetchall()]
            
            if not inactive_ids:
                logger.debug("No inactive markets found; snapshot cleanup skipped")
                return 0
            
            # Delete snapshots for those markets
            deleted_count = 0
            for market_id in inactive_ids:
                cursor.execute("DELETE FROM snapshots WHERE market_id = ?", (market_id,))
                deleted_count += cursor.rowcount
            
            self.conn.commit()
            if deleted_count > 0:
                logger.info(f"[CLEANUP] Purged {deleted_count} snapshots for {len(inactive_ids)} inactive markets")
            return deleted_count
            
        except sqlite3.Error as e:
            logger.error(f"Failed to purge snapshots: {e}")
            return 0
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def add_to_watchlist(self, market_id: str) -> bool:
        """Add market to watchlist. Returns True if successful, False if already exists."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO watchlist (market_id)
                VALUES (?)
            """, (market_id,))
            self.conn.commit()
            logger.info(f"Added market {market_id} to watchlist")
            return True
        except sqlite3.IntegrityError:
            logger.debug(f"Market {market_id} already in watchlist")
            return False
        except sqlite3.Error as e:
            logger.error(f"Failed to add to watchlist: {e}")
            return False
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def remove_from_watchlist(self, market_id: str) -> bool:
        """Remove market from watchlist. Returns True if successful."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM watchlist WHERE market_id = ?", (market_id,))
            self.conn.commit()
            logger.info(f"Removed market {market_id} from watchlist")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to remove from watchlist: {e}")
            return False
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def get_watchlist(self) -> list:
        """Get all markets in watchlist."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT m.id, m.question, m.condition_id, m.liquidity, m.volume, 
                       m.open_interest, m.end_date, m.active, m.outcomes, m.outcome_prices, 
                       m.probability, m.category
                FROM markets m
                INNER JOIN watchlist w ON m.id = w.market_id
                ORDER BY w.added_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows] if rows else []
        except sqlite3.Error as e:
            logger.error(f"Failed to get watchlist: {e}")
            return []
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def get_last_refresh(self) -> str | None:
        """Get the last refresh timestamp from metadata."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_refresh'")
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get last refresh: {e}")
            return None
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def load_cached_markets(self) -> list | None:
        """Load all markets from cache (for API failure fallback). Retries on DB lock."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, source_id, question, condition_id, liquidity, volume, 
                       open_interest, end_date, active, outcomes, outcome_prices, probability, category
                FROM markets
                ORDER BY open_interest DESC
            """)
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning("No cached markets available in database")
                return None
            
            logger.info(f"Loaded {len(rows)} cached markets from database")
            return rows
        except sqlite3.Error as e:
            logger.error(f"Failed to load cached markets: {e}")
            return None


async def main(min_volume: float | None = None, min_oi: float | None = None):
    """Run the entire ingestion pipeline with graceful degradation."""
    # Use environment defaults if not provided
    if min_volume is None:
        min_volume = float(os.getenv("MIN_VOLUME_USD", "100000"))
    if min_oi is None:
        min_oi = float(os.getenv("MIN_OPEN_INTEREST_USD", "50000"))
    
    logger.info(f"Starting Polymarket BI ingestion pipeline (min_volume=${min_volume:,.0f}, min_oi=${min_oi:,.0f})...")
    
    try:
        # Fetch markets with error handling
        try:
            markets = await PolymarketPoller.fetch_all_categories(min_volume, min_oi)
            logger.info(f"Total valid markets fetched: {len(markets)}")
            
            if not markets:
                logger.warning("No markets fetched from API. Checking for cached data...")
                # Try to load cached data
                db = DatabaseManager()
                db.connect()
                db.init_schema()
                cached_markets = db.load_cached_markets()
                if cached_markets:
                    logger.info(f"Loaded {len(cached_markets)} markets from cache (API failure fallback)")
                    db.close()
                    return 0
                else:
                    logger.error("No cached data available. Pipeline completed with no data.")
                    db.close()
                    return 1
            
            # Store fresh data in database
            db = DatabaseManager()
            db.connect()
            db.init_schema()
            new, updated = db.insert_markets(markets)
            logger.info(f"Database: {new} new markets, {updated} updated")
            
            # Clean up snapshots for inactive markets if enabled
            cleanup_strategy = os.getenv("SNAPSHOT_CLEANUP_STRATEGY", "market_active").lower()
            if cleanup_strategy == "market_active":
                db.purge_inactive_market_snapshots()
            
            db.close()
            
            logger.info("Ingestion pipeline completed successfully")
            return 0
            
        except Exception as fetch_error:
            logger.error(f"API fetch failed: {type(fetch_error).__name__}: {fetch_error}", exc_info=False)
            logger.info("Attempting to use cached data as fallback...")
            
            # Try to load cached data when API fails
            try:
                db = DatabaseManager()
                db.connect()
                db.init_schema()
                cached_markets = db.load_cached_markets()
                if cached_markets:
                    logger.info(f"Gracefully degraded: Using {len(cached_markets)} markets from cache")
                    db.close()
                    return 0
                else:
                    logger.error("No cached data available for fallback")
                    db.close()
                    return 1
            except Exception as cache_error:
                logger.error(f"Cache fallback also failed: {type(cache_error).__name__}: {cache_error}")
                return 1
                
    except Exception as e:
        logger.error(f"Pipeline failed: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    asyncio.run(main())
