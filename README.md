# Polymarket BI

Async data pipeline + dashboard for Polymarket prediction markets.

## Quick Start

```bash
python main.py
```

This fetches market data and launches the Streamlit dashboard at `http://localhost:8501`.

## How It Works

- **pipeline.py** — Async fetches 13 business-relevant market categories, validates (liquidity, dates), stores in SQLite
- **dashboard.py** — Streamlit visualization with metrics, charts, market search
- **main.py** — Single entry point that runs both

## Setup

```bash
uv sync
python main.py
```

## Data Source

Polymarket API: `https://gamma-api.polymarket.com/markets`

Markets are filtered by:
- Liquidity ≥ $500k
- End date in the future
- Valid outcome prices (0-1 decimals)

Database: SQLite (`polymarket_bi.db`)

12. **Financial Forecast** — Forward-looking financial predictions
13. **Unemployment** — Employment data, jobless claims, labor statistics

## Data Source & API

- **Markets Endpoint:** `GET https://gamma-api.polymarket.com/markets`
- **Query Params:** `limit=500`, `offset`, `liquidity_num_min=500000`, `closed=false`, `tag_id={category_id}`, `related_tags=true`
- **Category Filtering:** Use `tag_id` query parameter with category-specific IDs:
  - **Business**: `tag_id=107`
  - **Business News**: `tag_id=100039`
  - **Crypto**: `tag_id=21`
  - **Politics**: `tag_id=2`
  - **Tech**: `tag_id=1401`
  - **Finance**: `tag_id=120`
  - **Economy**: `tag_id=100328`
  - **Stocks**: `tag_id=604`
  - **Market Cap**: `tag_id=1095`
  - **Banking**: `tag_id=100040`
  - **Prices**: `tag_id=1384`
  - **Financial Forecast**: `tag_id=619`
  - **Unemployment**: `tag_id=1624`
- **Related Tags:** Set `related_tags=true` to include related markets when filtering by tag_id
- **Response Fields:** id, question, liquidity, volume, endDate, outcomePrices, active
- **Note:** Each market category can be filtered directly via API using tag_id parameter

## Data Quality Filters

- **Liquidity ≥ $500k** — High-confidence signal, excludes thin markets
- **Volume** — Secondary validation of market engagement

## Key Fields for Ingestion

- `id`, `question`, `liquidity` (USD), `volume` (USD), `endDate`, `outcomePrices` (array of probabilities), `active` (bool)
- **Note:** Category is determined via `tag_id` query parameter, not from response field

## Data Collection Strategy

- **Method:** Polling (hourly snapshots) via REST API from multiple sources
- **No WebSockets:** Not needed for BI use-case
- **Architecture:** Asynchronous ingestion and response processing
  - **Async I/O:** All API requests and response processing use async/await patterns (asyncio, aiohttp)
  - **Concurrent Network Requests:** Multiple API endpoints polled concurrently (13 Polymarket categories + Kalshi + third source)
  - **Bottleneck Optimization:** Async prevents blocking on network I/O; multiple requests execute in parallel
- **Database:** SQLite (lightweight, self-contained, ideal for single-instance development and testing)
  - Schema: Normalized tables for sources, markets, and snapshots to support cross-source comparison
  - Retention: Full history for trend analysis and probability shifts
- **Dashboard:** Streamlit (reads from database, displays trends/comparisons across sources)

## Dashboard Features

The Streamlit dashboard provides real-time visualization of market data:

- **Key Metrics:** Total markets, average liquidity, total volume, active markets count
- **Market Discovery:** 
  - Search markets by question/keyword
  - Filter by minimum liquidity threshold
  - Sort by liquidity, volume, or recency
- **Market Details:** 
  - View individual market probabilities (outcome prices)
  - Track market liquidity and volume
  - See end dates and active status
  - View snapshot history for selected markets
- **Visualizations:**
  - Liquidity distribution histogram
  - Volume vs Liquidity scatter plot

### Running the Dashboard

```bash
uv run streamlit run dashboard.py
```

Dashboard will open at: `http://localhost:8501`

## Quick Start

### Single Command to Run Everything

```bash
uv sync              # Install dependencies (one time)
python main.py       # Fetch data, then launch dashboard
```

That's it! The pipeline will:
1. Fetch ~50 markets from 13 Polymarket categories (async, concurrent)
2. Normalize and validate data
3. Store in SQLite
4. Launch interactive Streamlit dashboard at http://localhost:8501

### Alternative Options

```bash
python main.py --ingest-only      # Only fetch data, don't show dashboard
python main.py --dashboard-only    # Only show dashboard (use existing data)
python main.py --skip-ingest       # Skip fetching, go straight to dashboard
```

### Legacy Direct Commands

```bash
uv run ingest.py                    # Run ingestion pipeline only
uv run streamlit run dashboard.py   # Run dashboard only
```

## Project Structure

```
polymarket/
├── src/                    # Core pipeline modules
│   ├── __init__.py
│   ├── pipeline.py        # Main ingestion pipeline (async)
│   └── schema_sqlite.sql  # SQLite database schema
├── tests/                 # Test and debug scripts
├── data/                  # Reference data (tags, samples)
├── archive/               # Old/deprecated files
│── ingest.py             # Entry point for ingestion (wrapper)
│── dashboard.py          # Entry point for Streamlit dashboard
│── polymarket_bi.db      # SQLite database (auto-created)
├── pyproject.toml        # Dependencies (uv)
└── README.md
```

## Files Reference

- **ingest.py** / **dashboard.py** — Root-level entry points (call src modules)
- **src/pipeline.py** — Core async ingestion logic (normalized data, validation)
- **src/schema_sqlite.sql** — Database schema definition
- **polymarket_bi.db** — Live SQLite database (~65KB after first run)


