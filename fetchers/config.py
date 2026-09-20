"""
Configuration for API fetchers (Polymarket, Kalshi).
"""

# ============================================================================
# POLYMARKET
# ============================================================================

POLYMARKET_API_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_MARKETS_ENDPOINT = f"{POLYMARKET_API_BASE}/markets"
POLYMARKET_OI_ENDPOINT = "https://data-api.polymarket.com/oi"

POLYMARKET_DEFAULT_LIMIT = 500 # Number of items to fetch per request
POLYMARKET_DEFAULT_OFFSET = 0  # Starting offset for pagination
POLYMARKET_CLOSED = "false"   # Fetch only active markets
POLYMARKET_VOLUME_NUM_MIN = 100000 # Volume minimum threshold ($100k)
POLYMARKET_LIQUIDITY_NUM_MIN = 0 # Liquidity minimum threshold (disabled)
POLYMARKET_OI_MIN = 100000 # Open Interest minimum threshold ($100k)
POLYMARKET_ACTIVE = "true" # Fetch only active markets

HTTP_TIMEOUT = 10.0 # Timeout for HTTP requests
OI_TIMEOUT = 10.0   # Timeout for Open Interest requests
API_RATE_LIMIT_PER_HOST = 20 # Max concurrent connections per host
API_RATE_LIMIT_TOTAL = 100 # Max total concurrent connections

POLYMARKET_CATEGORIES = {
    "business": 107,
    "business_news": 100039,
    "politics": 2,
    "tech": 1401,
    "finance": 120,
    "economy": 100328,
    "stocks": 604,
    "market_cap": 1095,
    "banking": 100040,
    "financial_forecast": 619,
    "unemployment": 1624,
    "world": 101970,
    "science": 74
}       # Mapping of category names to tag IDs (pure crypto speculation tag excluded)

# ============================================================================
# KALSHI
# ============================================================================

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_EVENTS_ENDPOINT = f"{KALSHI_BASE}/events"

KALSHI_DEFAULT_LIMIT = 200  # Number of events per request
KALSHI_MIN_OPEN_INTEREST = 10000  # Calibrated active open interest threshold ($10k)
KALSHI_MIN_VOLUME = 25000  # Minimum cumulative volume threshold ($25k)
KALSHI_TIMEOUT = 30.0  # Timeout for Kalshi API requests

KALSHI_CATEGORIES = {
    "economics",
    "financials",
    "politics",
    "science and technology",
    "world",
    "social",
    "elections",
    "companies"
}  # High-signal categories of interest for Kalshi markets
