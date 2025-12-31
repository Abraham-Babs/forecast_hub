import httpx
import asyncio
import logging
import config as cfg

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


async def stream_markets(client: httpx.AsyncClient):
    """Stream markets as they're fetched and filtered. Yields dicts one by one."""
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
                    yield {
                        'id': market.get('ticker'),
                        'question': market.get('title'),
                        'probability': float(market.get('last_price', 0)),
                        'volume': market.get('volume', 0),
                        'volume_24h': market.get('volume_24h', 0),
                        'liquidity': float(market.get('liquidity_dollars', 0)),
                        'open_interest': market.get('open_interest'),
                        'category': event_category
                    }
        
        if batch_count > 0:
            logger.info(f"Batch: {batch_count} markets | Total: {fetched_count}")
        
        cursor = data.get('cursor')
        if not cursor:
            break
    
    logger.info(f"Kalshi: {fetched_count} markets (OI >= ${cfg.KALSHI_MIN_OPEN_INTEREST:,})")


async def fetch_all_markets() -> list[dict]:
    """Fetch all markets with streaming. Caller can process concurrently."""
    connector = httpx.AsyncHTTPTransport(limits=httpx.Limits(
        max_connections=cfg.API_RATE_LIMIT_TOTAL,
        max_keepalive_connections=cfg.API_RATE_LIMIT_PER_HOST
    ))
    
    try:
        async with httpx.AsyncClient(transport=connector, timeout=cfg.KALSHI_TIMEOUT) as client:
            # Collect streamed markets; caller can also iterate async generator directly
            return [market async for market in stream_markets(client)]
    except asyncio.TimeoutError:
        logger.error(f"Kalshi fetch timeout after {cfg.KALSHI_TIMEOUT}s")
    except httpx.HTTPError as e:
        logger.error(f"Kalshi fetch HTTP error: {type(e).__name__}: {e}")
    except Exception as e:
        logger.error(f"Kalshi fetch failed: {type(e).__name__}: {e}")
    
    return []


if __name__ == "__main__":
    asyncio.run(fetch_all_markets())
