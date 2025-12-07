# Polymarket BI

Async data pipeline + dashboard for Polymarket prediction markets.

## Quick Start

```bash
uv sync
python main.py
```

This fetches market data and launches the Streamlit dashboard at `http://localhost:8501`.

## How It Works

- **pipeline.py** — Async fetches 13 business-relevant market categories from Polymarket API and OI API, validates (volume, OI, outcomes), stores in SQLite
- **dashboard.py** — Streamlit visualization with metrics, charts, market search, and filtering
- **main.py** — Single entry point that runs both pipeline and dashboard

## Setup

```bash
uv sync              # Install dependencies (one-time)
python main.py       # Fetch data, then launch dashboard
```

## Data Sources

- **Markets API:** `https://gamma-api.polymarket.com/markets`
- **Open Interest API:** `https://data-api.polymarket.com/oi`

Markets are fetched from 13 business-relevant categories and filtered by:
- Volume ≥ $100,000 (configurable, default)
- Open Interest ≥ $50,000 (configurable, default)
- Valid outcome prices (0-1 range)
- Condition ID present

Database: SQLite (`polymarket_bi.db`)

## Categories

The pipeline fetches from these 13 market categories:

1. **Business** — General business news and corporate events
2. **Business News** — Breaking business developments
3. **Crypto** — Cryptocurrency and blockchain predictions
4. **Politics** — Political elections and policy outcomes
5. **Tech** — Technology industry developments
6. **Finance** — Financial markets and institutions
7. **Economy** — Macroeconomic indicators and trends
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


