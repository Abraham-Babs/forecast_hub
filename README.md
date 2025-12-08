# Polymarket BI — Business Intelligence for Prediction Markets

**Real-time consensus analysis for strategic decision-making**

Use crowd-powered forecasts from Polymarket to improve business decisions. Companies rely on prediction markets as a signal for what sophisticated predictors think will happen across economy, technology, politics, and more.

## What This Tool Does

Polymarket BI aggregates high-quality prediction market data and surfaces it in an actionable dashboard. Instead of manually checking Polymarket, you get:

- **Filtered markets that matter**: Only shows markets with real capital at stake ($100K+ volume, $50K+ open interest) to eliminate noise and manipulation risk
- **Data freshness transparency**: Displays when data was last updated; manual refresh button available
- **Easy discovery**: Search, filter by category, sort by conviction/liquidity/resolution timeline
- **Watchlist/favorites**: Save important markets for tracking across sessions
- **Historical trends**: See how probabilities have changed over time
- **Business insights**: Pre-calculated consensus strength, disagreement zones, and imminent resolutions

## Quick Start

```bash
uv sync
python main.py
```

This fetches market data and launches the dashboard at `http://localhost:8501`.

## Product Philosophy

**Target Users**: Companies making business decisions (forecasting, risk analysis, hedging, timing)

**Core Value Proposition**: Use prediction market signals to validate internal forecasts, discover blind spots, and quantify conviction across complex outcomes

**Key Design Decisions**:

1. **High-signal markets only** — Filters for volume + open interest ensure capital is actually at risk. Eliminates the long tail of low-liquidity, potentially manipulated markets.

2. **Data quality is paramount** — Shows when data is stale, allows manual refresh, surface missing data. Companies can't make decisions on data they don't trust.

3. **Category-based navigation** — 13 categories (Economy, Finance, Tech, Crypto, Politics, etc.) because prediction markets are extremely dynamic. Markets appear/disappear by category; filtering helps users find signals in their domain.

4. **Multiple entry points** — Search for specific questions, filter by probability conviction/timeline, or browse curated "strongest consensus" / "high disagreement" / "resolution imminent" sections.

5. **Persistent watchlists** — Saved to database so users can track specific outcomes across sessions.

6. **Historical probability tracking** — Snapshots at each refresh let users see how consensus has shifted.

## How It Works

- **pipeline.py** — Async fetches 13 market categories from Polymarket API + Open Interest API, validates data quality, stores in SQLite with snapshots for trend tracking
- **dashboard.py** — Streamlit interface for search, discovery, filtering, and decision-making
- **main.py** — Single entry point; runs pipeline, then launches dashboard with automatic background refreshes every 6 hours

## Setup

```bash
uv sync                 # Install dependencies (one-time)
python main.py          # Full pipeline + dashboard
```

### Dashboard Only (using existing data)

```bash
streamlit run dashboard.py
```

### Pipeline Only (no dashboard)

```bash
python pipeline.py
```

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

The Streamlit dashboard provides real-time visualization of market data:

- **Key Metrics:** 
  - Total markets in database
  - Average liquidity
  - Total volume
  - Active market count

- **Market Discovery:**
  - Search markets by keyword/question
  - Filter by minimum volume and OI thresholds
  - View market details and probabilities

- **Visualizations:**
  - Liquidity distribution histogram
  - Volume vs Liquidity scatter plot

- **Market Details:**
  - Question text and market ID
  - Liquidity and volume
  - End date and active status
  - Outcome probabilities

## Running

### Full Pipeline + Dashboard

```bash
python main.py
```

Fetches markets meeting filtering criteria (volume ≥ $100k, OI ≥ $50k) from all 13 categories, stores in SQLite, and launches dashboard at `http://localhost:8501`.

### Dashboard Only

```bash
uv run streamlit run dashboard.py
```

Uses existing data from database (no API fetch).

### Pipeline Only

```bash
uv run python pipeline.py
```

Fetches and stores data without launching dashboard.

## Project Structure

```
polymarket/
├── pipeline.py       # Async data fetching and normalization
├── dashboard.py      # Streamlit visualization
├── main.py          # Entry point (runs both)
├── verify_data.py   # Quick data validation utility
├── pyproject.toml   # Dependencies (managed by uv)
├── uv.lock          # Locked dependency versions
├── README.md        # This file
├── .gitignore       # Git ignore rules
└── polymarket_bi.db # SQLite database (auto-created)
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
uv sync                    # Install all dependencies
python main.py            # Run full pipeline + dashboard
uv run python verify_data.py  # Check database contents
```

## Notes

- First run creates `polymarket_bi.db` automatically
- Subsequent runs update markets and add snapshots
- Database persists across runs for trend analysis
- Dashboard refreshes data with "Fetch Market Data" button


