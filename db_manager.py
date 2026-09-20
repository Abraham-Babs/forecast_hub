#!/usr/bin/env python
"""
Database management for markets, snapshots, and metadata.
Handles schema creation, UPSERT operations, and concurrent access.
"""

import sqlite3
import logging
import os
from datetime import datetime, timezone
from db_utils import retry_on_db_lock

logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "Markets_database.db")

CATEGORY_MAPPING = {
    "economy": "Economy & Macro",
    "economics": "Economy & Macro",
    "unemployment": "Economy & Macro",
    "financial_forecast": "Economy & Macro",
    "finance": "Finance & Markets",
    "financials": "Finance & Markets",
    "stocks": "Finance & Markets",
    "banking": "Finance & Markets",
    "market_cap": "Finance & Markets",
    "politics": "Politics & Governance",
    "elections": "Politics & Governance",
    "business": "Companies & Business",
    "business_news": "Companies & Business",
    "companies": "Companies & Business",
    "tech": "Technology & Science",
    "science": "Technology & Science",
    "science and technology": "Technology & Science",
    "world": "Global Affairs",
    "social": "Culture & Society",
}


def normalize_category(cat: str | None) -> str:
    """Normalize raw API category strings into unified canonical taxonomy."""
    if not cat:
        return "General"
    cleaned = cat.strip().lower()
    return CATEGORY_MAPPING.get(cleaned, cleaned.replace("_", " ").title())



class DatabaseManager:
    """SQLite database operations for markets, snapshots, and metadata. 
    Handles UPSERT with duplicate grouping, deletion of resolved markets, and concurrent access via WAL mode."""
    
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DATABASE_PATH
        self.conn = None
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def connect(self):
        """Connect to database with concurrency handling. Uses WAL mode for better concurrent read/write access."""
        # Set timeout to 10 seconds for concurrent access
        self.conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read/write performance
        self.conn.execute('PRAGMA journal_mode=WAL')
        # Increase cache size for better performance
        self.conn.execute('PRAGMA cache_size=-64000')
        logger.info(f"Connected to SQLite database (WAL mode, 10s timeout): {self.db_path}")
    
    def init_schema(self):
        """Create tables if they don't exist: sources, markets, snapshots, metadata.
        Markets table includes source (polymarket|kalshi) and duplicate_group_id for cross-platform matching.
        Uses indexes on probability, open_interest, source, and duplicate_group_id for fast queries."""
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
        
        # Markets table with source, topic title, and duplicate grouping
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS markets (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                topic_title TEXT,
                question TEXT,
                liquidity REAL,
                volume REAL,
                volume_24h REAL,
                open_interest REAL,
                probability REAL,
                category TEXT,
                end_date TEXT,
                rules TEXT,
                url TEXT,
                duplicate_group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Non-destructive migration: add new columns if table already existed
        cursor.execute("PRAGMA table_info(markets)")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        new_cols = {
            "topic_title": "TEXT",
            "end_date": "TEXT",
            "rules": "TEXT",
            "url": "TEXT"
        }
        for col_name, col_type in new_cols.items():
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE markets ADD COLUMN {col_name} {col_type}")
                logger.info(f"Migrated markets table: added {col_name} ({col_type})")

        # Standardize existing stored categories into canonical taxonomy
        cursor.execute("SELECT DISTINCT category FROM markets WHERE category IS NOT NULL")
        existing_categories = [row[0] for row in cursor.fetchall()]
        for cat in existing_categories:
            canonical = normalize_category(cat)
            if canonical != cat:
                cursor.execute("UPDATE markets SET category = ? WHERE category = ?", (canonical, cat))
        
        # Snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY,
                market_id TEXT,
                question TEXT,
                volume REAL,
                probability REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(market_id) REFERENCES markets(id)
            )
        """)
        
        # Metadata table (tracks last refresh)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Watchlist table (user favorites)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                market_id TEXT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(market_id) REFERENCES markets(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for fast filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_probability ON markets(probability)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_open_interest ON markets(open_interest)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_source ON markets(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_duplicate_group ON markets(duplicate_group_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_topic_title ON markets(topic_title)")
        
        # Insert Polymarket source
        cursor.execute("""
            INSERT OR IGNORE INTO sources (name, api_endpoint)
            VALUES (?, ?)
        """, ("Polymarket", "https://gamma-api.polymarket.com"))
        
        # Insert Kalshi source
        cursor.execute("""
            INSERT OR REPLACE INTO sources (name, api_endpoint)
            VALUES (?, ?)
        """, ("Kalshi", "https://external-api.kalshi.com/trade-api/v2"))
        
        self.conn.commit()
        logger.info("Database schema initialized with migrations")
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def insert_markets(self, markets: list, duplicate_groups: dict) -> tuple:
        """UPSERT markets with duplicate detection. DELETE markets not in current fetch (resolved/delisted).
        
        Args:
            markets: List of market dicts from fetchers
            duplicate_groups: Dict mapping market_id -> group_id (from find_duplicate_groups)
        
        Duplicate detection: Uses pre-computed duplicate_groups to assign group_id. 
        Markets are never deleted if duplicates; they're grouped instead.
        
        Resolved markets: Any markets in database but NOT in current fetch are deleted (assumed resolved/delisted).
        
        Returns:
            Tuple of (new_count, updated_count) for logging/monitoring.
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("BEGIN IMMEDIATE")
            
            new_count = 0
            updated_count = 0
            market_ids_current = set()
            
            for market in markets:
                market_id = market.get("id")
                market_ids_current.add(market_id)
                
                # Check if market already exists
                cursor.execute("SELECT id FROM markets WHERE id = ?", (market_id,))
                exists = cursor.fetchone() is not None
                
                # Get duplicate group if applicable
                dup_group = duplicate_groups.get(market_id)
                
                cursor.execute("""
                    INSERT INTO markets (
                        id, source, topic_title, question, liquidity, volume, volume_24h, 
                        open_interest, probability, category, end_date, rules, url, duplicate_group_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source = excluded.source,
                        topic_title = excluded.topic_title,
                        question = excluded.question,
                        liquidity = excluded.liquidity,
                        volume = excluded.volume,
                        volume_24h = excluded.volume_24h,
                        open_interest = excluded.open_interest,
                        probability = excluded.probability,
                        category = excluded.category,
                        end_date = excluded.end_date,
                        rules = excluded.rules,
                        url = excluded.url,
                        duplicate_group_id = excluded.duplicate_group_id
                """, (
                    market_id,
                    market.get("source", "unknown"),
                    market.get("topic_title") or market.get("question"),
                    market.get("question"),
                    market.get("liquidity"),
                    market.get("volume"),
                    market.get("volume_24h"),
                    market.get("open_interest"),
                    market.get("probability"),
                    normalize_category(market.get("category")),
                    market.get("end_date"),
                    market.get("rules"),
                    market.get("url"),
                    dup_group,
                ))
                
                if exists:
                    updated_count += 1
                else:
                    new_count += 1
                
                # Insert snapshot
                cursor.execute("""
                    INSERT INTO snapshots (market_id, question, volume, probability)
                    VALUES (?, ?, ?, ?)
                """, (
                    market_id,
                    market.get("question"),
                    market.get("volume"),
                    market.get("probability"),
                ))
            
            # Delete markets not in current fetch (resolved/delisted)
            cursor.execute("SELECT id FROM markets")
            db_ids = set(row[0] for row in cursor.fetchall())
            resolved_ids = db_ids - market_ids_current
            
            deleted_count = 0
            for resolved_id in resolved_ids:
                cursor.execute("DELETE FROM markets WHERE id = ?", (resolved_id,))
                deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} resolved/delisted markets")
            
            # Record last refresh timestamp
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("last_refresh", datetime.now(timezone.utc).isoformat())
            )
            
            cursor.execute("COMMIT")
            logger.info(f"Stored {new_count} new, {updated_count} updated, {deleted_count} deleted")
            return new_count, updated_count
            
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except:
                pass
            logger.error(f"Insert failed, transaction rolled back: {e}")
            raise
    
    @retry_on_db_lock(max_retries=3, initial_delay=0.1)
    def load_cached_markets(self) -> list | None:
        """Load all markets from database as cache fallback when APIs fail.
        Returns latest state only (current refresh's markets); snapshots not returned here.
        Used when pipeline detects fetch errors to serve existing data instead of failing hard."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, source, topic_title, question, liquidity, volume, volume_24h,
                       open_interest, probability, category, end_date, rules, url, duplicate_group_id
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

    def get_market_count(self) -> int:
        """Get total number of markets currently stored in the database."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM markets")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_last_refresh_time(self) -> str | None:
        """Get timestamp of the last successful data refresh."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_refresh'")
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

