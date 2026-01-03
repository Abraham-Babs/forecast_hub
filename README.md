# Forecast Hub

**Harness collective Human intelligence to inform strategic business decisions**

*For business strategists, product managers, risk managers, traders, researchers, analysts, etc.*

Fetch prediction market data from Polymarket and Kalshi, detect overlapping markets across platforms (85% question similarity), and explore via interactive dashboard. No blockchain knowledge required.

## Quick Start

```bash
uv sync
uv run main.py
```

Dashboard launches at `http://localhost:8501`. Data fetches on startup; click "Refresh Data" for manual updates.

## Features

- **Dual-source data**: Polymarket (15 categories) + Kalshi (paginated events) fetched concurrently
- **Cross-platform overlaps**: Automatic detection groups same markets across platforms
- **Filtering & search**: By source, category, probability, open interest, watchlist
- **Source badges**: Color-coded (Blue=Polymarket, Green=Kalshi)
- **Side-by-side comparison**: View overlapping markets from both platforms
- **Persistent watchlist**: Save favorite markets across sessions
- **Manual & auto-refresh**: Dashboard button or configure via `fetchers/config.py`

## Installation

### Prerequisites
- Git installed ([download here](https://git-scm.com/))
- Python 3.10+ installed ([download here](https://www.python.org/))
- `uv` package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))

### Setup & Run

**macOS / Linux:**
```bash
git clone <your-repo-url>
cd forecast-hub
uv sync
uv run main.py
```

**Windows (PowerShell):**
```powershell
git clone <your-repo-url>
cd forecast-hub
uv sync
uv run main.py
```

Done. Dashboard opens at `http://localhost:8501`.

## Configuration

Edit `fetchers/config.py` to customize:
- **Thresholds**: `POLYMARKET_VOLUME_NUM_MIN` ($500K default), `POLYMARKET_OI_MIN` ($200K default)
- **Categories**: `POLYMARKET_CATEGORIES` (15 default), `KALSHI_CATEGORIES` (9 default)
- **API behavior**: `HTTP_TIMEOUT`, `API_RATE_LIMIT_TOTAL`, `API_RATE_LIMIT_PER_HOST`

Example: Lower volume threshold for smaller markets:
```python
POLYMARKET_VOLUME_NUM_MIN = 100000
```

## Commands

| Command | Purpose |
|---------|---------|
| `uv run main.py` | Full pipeline + dashboard |
| `uv run streamlit run dashboard.py` | Dashboard only (use existing data) |
| `uv run python -m asyncio -c "from pipeline import main; import asyncio; asyncio.run(main())"` | Pipeline only (no dashboard) |

## Project Structure

```
polymarket/
├── main.py                 # Entry point
├── pipeline.py             # Async fetching + duplicate detection
├── dashboard.py            # Streamlit UI
├── db_manager.py           # Database operations
├── db_utils.py             # Retry logic
├── tz_utils.py             # Time utilities
├── fetchers/
│   ├── config.py           # Thresholds, categories, API endpoints
│   ├── polymarket_api.py   # Polymarket client
│   └── kalshi_api.py       # Kalshi client
├── pyproject.toml          # Dependencies
└── Markets_database.db     # SQLite (auto-created)
```

## How It Works

**Pipeline** (async):
1. Fetch 15 Polymarket categories + Kalshi paginated events concurrently
2. Tag each market with source (`polymarket` | `kalshi`)
3. Detect overlaps: Markets with ≥85% similar questions grouped by `duplicate_group_id`
4. UPSERT active markets, DELETE resolved/delisted ones
5. Store in SQLite with snapshots for trend analysis

**Dashboard** (Streamlit):
- Filter by source, category, probability, open interest
- Search markets by question
- Sort by OI, volume, liquidity, probability
- View side-by-side comparison of overlapping markets
- Save favorites to watchlist
- Manual "Refresh Data" button

## Data Model

| Table | Fields |
|-------|--------|
| `markets` | `id`, `source` (polymarket\|kalshi), `question`, `probability`, `open_interest`, `volume`, `volume_24h`, `liquidity`, `category`, `duplicate_group_id` |
| `snapshots` | `market_id`, `probability`, `volume`, `timestamp` |
| `watchlist` | `market_id`, `added_at` |
| `metadata` | `key`, `value`, `updated_at` |

## Dependencies

- `httpx` — Async HTTP
- `pandas` — Data manipulation
- `streamlit` — Dashboard

See `pyproject.toml` for full list.

## Dashboard Quick Reference

A **Quick Reference** guide is available in the dashboard sidebar (📖 expand to see platform badges, probability colors, metric definitions, icons, and filter explanations).


