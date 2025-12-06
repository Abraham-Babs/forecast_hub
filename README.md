# Polymarket Business Intelligence Project

## Overview
Business intelligence project leveraging Polymarket prediction market data to inform real-world business decisions.

## Focus Market Categories

This project focuses on market categories with direct business relevance:

1. **Business** — Company performance, acquisitions, IPOs, competitive intelligence
2. **Business News** — Corporate announcements, press releases, industry updates
3. **Crypto** — Protocol adoption, regulatory outcomes
4. **Politics** — Geopolitical/regulatory risk assessment, election outcomes
5. **Tech** — AI model leadership, product launches, competitive positioning
6. **Finance** — Interest rates, inflation, financial market indicators
7. **Economy** — Economic growth, macroeconomic forecasts, GDP, unemployment
8. **Stocks** — Stock market performance, equity valuations
9. **Stocks & Market Cap** — Market capitalization trends, company valuations
10. **Banking** — Banking sector performance, financial institutions
11. **Prices** — Price movements across assets and commodities
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

- **Method:** Polling (hourly snapshots) via REST API
- **No WebSockets:** Not needed for BI use-case
- **Database:** SQLite (simple, file-based, sufficient for time-series snapshots)
  - Schema: market_id, question, tag_id, liquidity, volume, outcome_prices, timestamp
  - Retention: Full history for trend analysis and probability shifts
- **Dashboard:** Streamlit (reads from database, displays trends/comparisons)


