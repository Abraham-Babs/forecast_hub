# Polymarket BI — Business Intelligence for Prediction Markets

**Real-time consensus analysis for strategic decision-making**

Use crowd-powered forecasts from Polymarket to improve business decisions. Companies rely on prediction markets as a signal for what sophisticated predictors think will happen across economy, technology, politics, and more.

## What This Tool Does

Polymarket BI aggregates high-quality prediction market data and surfaces it in an actionable dashboard. Instead of manually checking Polymarket, you get:

- **Filtered markets that matter**: Only shows markets with real capital at stake ($100K+ volume, $50K+ open interest) to eliminate noise and manipulation risk
- **Data freshness transparency**: Displays when data was last updated; manual refresh button available
- **Multi-dimensional discovery**: Filter by category, probability conviction, open interest, and resolution timeline. Sort by liquidity, conviction level, or time to resolution
- **Expandable market details**: Click to view full market question text; compact display prevents UI clutter
- **Watchlist/favorites**: Save important markets for tracking across sessions (heart icon toggle)
- **Business metrics dashboard**: Pre-calculated consensus strength, balanced markets, imminent resolutions, and highly liquid markets
- **Quick browse filters**: "Strongest Consensus" and "Markets in Flux" buttons for rapid exploration

## Quick Start

```bash
uv sync
python main.py
```

This fetches market data from Polymarket API (13 categories), stores in SQLite, and launches the dashboard at `http://localhost:8501`. Data automatically refreshes every 6 hours in the background.

## Product Philosophy

**Target Users**: Companies making business decisions (forecasting, risk analysis, hedging, timing)

**Core Value Proposition**: Use prediction market signals to validate internal forecasts, discover blind spots, and quantify conviction across complex outcomes

**Key Design Decisions**:

1. **High-signal markets only** — Filters for volume + open interest ensure capital is actually at risk. Eliminates the long tail of low-liquidity, potentially manipulated markets.

2. **Data quality is paramount** — Shows when data is stale, allows manual refresh, surfaces missing data. Companies can't make decisions on data they don't trust.

3. **Category-based navigation** — 13 categories (Economy, Finance, Tech, Crypto, Politics, etc.) because prediction markets are extremely dynamic. Markets appear/disappear by category; filtering helps users find signals in their domain.

4. **Multi-filter exploration** — Users can combine filters: probability conviction range (40-60% = balanced, >80% = high consensus), OI thresholds, resolution timeline, and category. Sort by liquidity, probability, or time to resolution.

5. **Compact card layout** — Market probability shown prominently (large percentage). Questions are expandable (click to see full text). Watchlist heart icon always visible. Reduces cognitive load while enabling quick scanning.

6. **Persistent watchlists** — Saved to database so users can track specific outcomes across sessions.

7. **Historical probability tracking** — Snapshots at each refresh let users see how consensus has shifted.

## How It Works

- **pipeline.py** — Async fetches 13 market categories from Polymarket API + Open Interest API, validates data quality, stores in SQLite with snapshots for trend tracking
- **dashboard.py** — Streamlit interface for filtering, sorting, discovery, and decision-making; includes watchlist management and manual refresh button
- **main.py** — Single entry point; runs initial pipeline, then launches dashboard with automatic background refreshes every 6 hours

## Setup

```bash
uv sync                 # Install dependencies (one-time)
python main.py          # Fetch initial data + launch dashboard at http://localhost:8501
```

The dashboard will be available at `http://localhost:8501`. Data refreshes automatically every 6 hours in the background; use "Refresh Data Now" button for manual updates.

### Dashboard Only (using existing data)

```bash
streamlit run dashboard.py
```

Uses existing data from database without fetching from API.

### Pipeline Only (no dashboard)

```bash
python -m asyncio -c "from pipeline import main; import asyncio; asyncio.run(main())"
```

Fetches and stores data without launching dashboard.

## Data Sources

- **Markets API:** `https://gamma-api.polymarket.com/markets` (13 categories, 300 markets/category limit)
- **Open Interest API:** `https://data-api.polymarket.com/oi` (per-market capital at risk)

## Filtering Criteria

Markets are included if they meet **all** of:
- Volume ≥ $100,000 USD (proves real trading activity)
- Open Interest ≥ $50,000 USD (proves capital commitment; eliminates manipulation risk)
- Valid outcome prices (0.0-1.0 range)
- Condition ID present (unique market identifier)

**Rationale**: These thresholds ensure you're seeing markets where sophisticated participants have real money at stake. Prevents low-liquidity, potentially manipulated markets from polluting your decision signals.
8. **Stocks** — Individual stock and equity predictions
9. **Market Cap** — Market capitalization movements
10. **Banking** — Banking sector developments
11. **Prices** — Commodity and asset price movements
12. **Financial Forecast** — Forward-looking financial predictions
13. **Unemployment** — Employment data and labor statistics

## API Details

- **Endpoint:** `GET https://gamma-api.polymarket.com/markets`
- **Query Parameters:** `limit=300`, `closed=false`, `tag_id={category_id}`
- **Response Fields:** `id`, `question`, `liquidity`, `volume`, `endDate`, `outcomePrices`, `active`

### Category Tag IDs

Used in API requests:
- Business: 107
- Business News: 100039
- Crypto: 21
- Politics: 2
- Tech: 1401
- Finance: 120
- Economy: 100328
- Stocks: 604
- Market Cap: 1095
- Banking: 100040
- Prices: 1384
- Financial Forecast: 619
- Unemployment: 1624

## Data Quality

- **Volume Filter:** ≥ $100,000 USD (default, configurable)
- **Outcome Prices:** Validated as decimal values between 0-1
- **Deduplication:** Markets deduplicated by ID across categories

## Architecture

- **Async I/O:** Uses `asyncio` and `aiohttp` for concurrent API requests
- **Concurrent Fetching:** All 13 categories polled in parallel
- **Normalization:** Standardizes field names and validates data
- **Database:** SQLite with normalized schema (sources, markets, snapshots)
- **Dashboard:** Streamlit for interactive visualization

## Dashboard Features

The Streamlit dashboard provides real-time filtering and exploration of market data:

**Sidebar Controls:**
- Market category filtering (multi-select)
- Favorites-only toggle
- Minimum open interest threshold slider
- Probability conviction range (0-100%)
- Resolution timeline radio buttons (Today | This Week | Next 30 Days | All Markets)

**Market Discovery:**
- "Strongest Consensus" — Filter to markets >80% or <20% conviction
- "Markets in Flux" — Show balanced markets (40-60% probability range)
- Smart sorting: Highest OI, Most Likely, Least Likely, Resolving Soonest, Lowest OI

**Market Cards Display:**
- Probability (large, color-coded: green for YES >50%, red for NO <50%)
- Market question (expandable, prevents truncation)
- Open interest (formatted as K/M: $50K, $1.5M)
- Days to resolution
- Watchlist heart icon (click to save/unsave)

**Business Metrics:**
- High Conviction markets (>70% or <30%)
- Balanced View markets (40-60%)
- Resolutions This Week
- Highly Liquid markets (top 25% by OI)

**Manual Controls:**
- "Refresh Data Now" button (triggers pipeline fetch)
- Refresh status indicator (shows staleness)
- Active filter summary with "Clear All" option
- Pagination (20 markets per page, "Load More" button)

## Running

### Full Pipeline + Dashboard (Recommended)

```bash
python main.py
```

- Validates configuration
- Fetches markets from Polymarket API (all 13 categories)
- Stores in SQLite database
- Launches dashboard at `http://localhost:8501`
- Starts background refresh thread (every 6 hours)

Press Ctrl+C to stop. Background thread gracefully shuts down.

### Dashboard Only

```bash
streamlit run dashboard.py
```

Uses existing data from database. No API fetch. Useful for exploring data without network access.

### Manual Pipeline Refresh

Use the "Refresh Data Now" button in the dashboard sidebar (top right). Takes 5-10 minutes to fetch all 13 categories and OI data.

## Project Structure

```
polymarket/
├── main.py          # Entry point: validates config, runs pipeline, launches dashboard
├── pipeline.py      # Async data fetching, normalization, and storage
├── dashboard.py     # Streamlit UI with filtering, sorting, watchlist management
├── config.py        # Environment variable validation
├── tz_utils.py      # UTC timezone handling and time utilities
├── db_utils.py      # Shared database retry logic
├── pyproject.toml   # Dependencies (managed by uv)
├── uv.lock          # Locked dependency versions
├── README.md        # This file
├── .env.example     # Environment variable template
├── .gitignore       # Git ignore rules
└── polymarket_bi.db # SQLite database (auto-created on first run)
```

## Data Model

### Markets Table
- `id` — Market identifier
- `question` — Market question text
- `condition_id` — Polymarket condition ID (unique market identifier)
- `liquidity` — Available liquidity in USD
- `volume` — Total volume traded in USD
- `open_interest` — Open interest in USD
- `end_date` — Market expiration date
- `active` — Whether market is currently active
- `outcomes` — JSON array of outcome labels (e.g., ["Yes", "No"])
- `outcome_prices` — JSON array of outcome probabilities (0-1)
- `probability` — "Yes" outcome probability in percent

### Snapshots Table
Historical snapshots for trend analysis:
- `market_id` — Reference to market
- `outcome_prices` — Prices at time of snapshot
- `volume` — Volume at time of snapshot
- `timestamp` — When snapshot was taken

## Dependencies

Managed via `uv` in `pyproject.toml`:
- `aiohttp` — Async HTTP client
- `asyncpg` — Async database support
- `requests` — HTTP library
- `pandas` — Data manipulation
- `streamlit` — Web dashboard framework
- `plotly` — Interactive charts
- `sqlalchemy` — SQL toolkit (optional)
- `python-dotenv` — Environment variable loading

## Development

To set up development environment:

```bash
uv sync                    # Install all dependencies (includes dev dependencies)
python main.py            # Run full pipeline + dashboard locally
streamlit run dashboard.py # Run dashboard only (iterate on UI)
```

### Code Quality

The codebase follows the project philosophy:
- **No assumptions**: Validate configuration and data explicitly
- **Measure everything**: Logging throughout for debugging
- **Simple code**: <30 lines per function, clear variable names
- **Type hints**: Pydantic models for all data validation
- **Error handling**: Explicit error messages, no silent failures
- **No bloat**: Removed ~40 lines of dead code and duplication

### Key Files to Understand

1. **main.py** — Application lifecycle and background scheduling
2. **pipeline.py** — Data fetching, validation, and storage logic
3. **dashboard.py** — User interface and filtering logic
4. **tz_utils.py** — Time utilities (critical for "days until resolution")
5. **db_utils.py** — Shared database retry decorator

## Notes

- First run creates `polymarket_bi.db` automatically
- Subsequent runs update markets and add snapshots (preserves historical data)
- Database persists across runs for trend analysis
- Dashboard filters out resolved markets (negative days_left) automatically
- Open interest formatted as K (thousands) unless ≥ $1M (then M for millions)
- All timestamps in UTC to prevent daylight saving time issues
- Background refresh thread runs independently; Ctrl+C safely shuts down


