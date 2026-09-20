import httpx
import asyncio
import logging
from fetchers import config as cfg

logger = logging.getLogger(__name__)


def _safe_float(val, default: float = 0.0) -> float:
    """Safely parse float from string or number."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


async def fetch_all_pages(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all paginated results sequentially from Kalshi API and return normalized market dicts."""
    all_markets = []
    cursor = None
    fetched_count = 0
    page_count = 0
    max_pages = 25  # Guard against unbounded pagination

    while page_count < max_pages:
        page_count += 1
        params = {
            "status": "open",
            "limit": cfg.KALSHI_DEFAULT_LIMIT,
            "with_nested_markets": "true"
        }
        if cursor:
            params['cursor'] = cursor

        response = await client.get(f"{cfg.KALSHI_BASE}/events", params=params)
        response.raise_for_status()
        data = response.json()
        events = data.get('events', [])

        if not events:
            break

        batch_count = 0
        for event in events:
            event_category = event.get('category', '').lower().strip()
            if event_category not in cfg.KALSHI_CATEGORIES:
                continue

            event_title = event.get('title') or ""

            for market in event.get('markets', []):
                oi = _safe_float(market.get('open_interest_fp'))
                vol = _safe_float(market.get('volume_fp'))
                vol_24h = _safe_float(market.get('volume_24h_fp'))

                # Filter by skin in the game threshold
                if oi < cfg.KALSHI_MIN_OPEN_INTEREST and vol < cfg.KALSHI_MIN_VOLUME:
                    continue

                # Determine likelihood percentage (0-100)
                prob = None
                last_price_str = market.get('last_price_dollars')
                if last_price_str is not None:
                    prob = _safe_float(last_price_str) * 100.0
                elif market.get('yes_bid_dollars') and market.get('yes_ask_dollars'):
                    bid = _safe_float(market.get('yes_bid_dollars'))
                    ask = _safe_float(market.get('yes_ask_dollars'))
                    prob = ((bid + ask) / 2.0) * 100.0

                ticker = market.get('ticker') or ""
                batch_count += 1
                fetched_count += 1

                all_markets.append({
                    'id': ticker,
                    'topic_title': event_title,
                    'question': market.get('title') or event_title,
                    'probability': prob,
                    'volume': vol,
                    'volume_24h': vol_24h,
                    'liquidity': _safe_float(market.get('liquidity_dollars')),
                    'open_interest': oi,
                    'category': event_category,
                    'end_date': market.get('expiration_time') or market.get('close_time'),
                    'rules': market.get('rules_primary') or event.get('sub_title') or "",
                    'url': f"https://kalshi.com/markets/{ticker.lower()}",
                    'source': 'kalshi'
                })

        if batch_count > 0:
            logger.info(f"Kalshi Batch {page_count}: {batch_count} markets | Cumulative: {fetched_count}")

        cursor = data.get('cursor')
        if not cursor:
            break

    logger.info(f"Kalshi Total: {fetched_count} markets (OI >= ${cfg.KALSHI_MIN_OPEN_INTEREST:,} or Vol >= ${cfg.KALSHI_MIN_VOLUME:,})")
    return all_markets


async def fetch_all_markets() -> list[dict]:
    """Fetch all markets from Kalshi API with pagination."""
    connector = httpx.AsyncHTTPTransport(
        limits=httpx.Limits(
            max_connections=cfg.API_RATE_LIMIT_TOTAL,
            max_keepalive_connections=cfg.API_RATE_LIMIT_PER_HOST
        ),
        http2=True
    )
    
    try:
        async with httpx.AsyncClient(transport=connector, timeout=cfg.KALSHI_TIMEOUT) as client:
            return await fetch_all_pages(client)
    except asyncio.TimeoutError:
        logger.error(f"Kalshi fetch timeout after {cfg.KALSHI_TIMEOUT}s")
    except httpx.HTTPError as e:
        logger.error(f"Kalshi fetch HTTP error: {type(e).__name__}: {e}")
    except Exception as e:
        logger.error(f"Kalshi fetch failed: {type(e).__name__}: {e}")
    
    return []


if __name__ == "__main__":
    asyncio.run(fetch_all_markets())
