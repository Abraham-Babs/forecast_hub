import httpx
import asyncio
import logging
from fetchers import config as cfg

logger = logging.getLogger(__name__)


async def fetch_all_pages(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all paginated results sequentially (API constraint) and return complete list."""
    all_markets = []
    cursor = None
    fetched_count = 0
    
    while True:
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
            
            for market in event.get('markets', []):
                if market.get('open_interest', 0) >= cfg.KALSHI_MIN_OPEN_INTEREST:
                    batch_count += 1
                    fetched_count += 1
                    all_markets.append({
                        'id': market.get('ticker'),
                        'question': market.get('title'),
                        'probability': float(market.get('last_price', 0)),
                        'volume': market.get('volume', 0),
                        'volume_24h': market.get('volume_24h', 0),
                        'liquidity': float(market.get('liquidity_dollars', 0)),
                        'open_interest': float(market.get('open_interest', 0)),
                        'category': event_category
                    })
        
        if batch_count > 0:
            logger.info(f"Batch: {batch_count} markets | Total: {fetched_count}")
        
        cursor = data.get('cursor')
        if not cursor:
            break
    
    logger.info(f"Kalshi: {fetched_count} markets (OI >= ${cfg.KALSHI_MIN_OPEN_INTEREST:,})")
    return all_markets


async def stream_markets(client: httpx.AsyncClient):
    """Deprecated: use fetch_all_pages() directly. Kept for backward compatibility."""
    return await fetch_all_pages(client)


async def fetch_all_markets() -> list[dict]:
    """Fetch all markets from Kalshi API with pagination."""
    connector = httpx.AsyncHTTPTransport(limits=httpx.Limits(
        max_connections=cfg.API_RATE_LIMIT_TOTAL,
        max_keepalive_connections=cfg.API_RATE_LIMIT_PER_HOST
    ))
    
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
