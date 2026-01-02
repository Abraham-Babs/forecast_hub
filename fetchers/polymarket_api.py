import httpx
import asyncio
import json
import logging
from fetchers import config as cfg

logger = logging.getLogger(__name__)


async def fetch_markets(client: httpx.AsyncClient, tag_id: int) -> list:
    """Fetch markets for a tag with pagination. Returns raw market dicts."""
    all_markets, offset = [], 0
    try:
        while True:
            response = await client.get(
                cfg.POLYMARKET_MARKETS_ENDPOINT,
                params={
                    "limit": cfg.POLYMARKET_DEFAULT_LIMIT,
                    "offset": offset,
                    "closed": cfg.POLYMARKET_CLOSED,
                    "tag_id": tag_id,
                    "volume_num_min": cfg.POLYMARKET_VOLUME_NUM_MIN,
                    "liquidity_num_min": cfg.POLYMARKET_LIQUIDITY_NUM_MIN
                },
                timeout=httpx.Timeout(cfg.HTTP_TIMEOUT)
            )
            response.raise_for_status()
            markets = response.json()
            if not markets:
                break
            all_markets.extend(markets)
            if len(markets) < cfg.POLYMARKET_DEFAULT_LIMIT:
                break
            offset += cfg.POLYMARKET_DEFAULT_LIMIT
        return all_markets
    except asyncio.TimeoutError:
        logger.error(f"Market fetch timeout after {cfg.HTTP_TIMEOUT}s")
        return []
    except httpx.HTTPError as e:
        logger.error(f"Market fetch HTTP error: {type(e).__name__}: {e}")
        return []
    except Exception as e:
        logger.error(f"Market fetch failed: {type(e).__name__}: {e}")
        return []


async def fetch_oi(client: httpx.AsyncClient, condition_id: str) -> float | None:
    """Fetch open interest for a market. Returns float or None on failure."""
    try:
        response = await client.get(
            cfg.POLYMARKET_OI_ENDPOINT,
            params={"market": condition_id},
            timeout=httpx.Timeout(cfg.OI_TIMEOUT)
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and len(data) > 0 and data[0].get("value") is not None:
            return float(data[0]["value"])
        return None
    except Exception:
        return None


async def process_market(
    client: httpx.AsyncClient, 
    market: dict, 
    category: str, 
    seen: set, 
    lock: asyncio.Lock
) -> dict | None:
    """Process and enrich market with OI. Returns normalized dict or None."""
    cond_id = market.get("conditionId")
    if cond_id is None:
        return None
    
    async with lock:
        if cond_id in seen:
            return None
        seen.add(cond_id)
    
    oi = await fetch_oi(client, cond_id)
    if not oi or oi < cfg.POLYMARKET_OI_MIN:
        return None
    
    try:
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        
        prices = market.get("outcomePrices", [])
        if isinstance(prices, str):
            prices = json.loads(prices)
        
        prob = None
        if outcomes and prices and "Yes" in outcomes:
            prob = float(prices[outcomes.index("Yes")]) * 100
        
        return {
            "id": market["id"],
            "question": market["question"],
            "probability": prob,
            "volume": float(market.get("volume", 0)),
            "volume_24h": float(market.get("volume24hr", 0)),
            "open_interest": oi,
            "category": category,
            "liquidity": float(market.get("liquidity", 0)),
        }
    except Exception:
        return None


async def fetch_all_markets() -> list[dict]:
    """Fetch and process markets from all categories with streaming."""
    connector = httpx.AsyncHTTPTransport(limits=httpx.Limits(
        max_connections=cfg.API_RATE_LIMIT_TOTAL,
        max_keepalive_connections=cfg.API_RATE_LIMIT_PER_HOST
    ))
    
    async with httpx.AsyncClient(transport=connector, timeout=cfg.HTTP_TIMEOUT) as client:
        # Create all fetch tasks upfront
        tasks = [
            (asyncio.create_task(fetch_markets(client, tag_id)), cat)
            for cat, tag_id in cfg.POLYMARKET_CATEGORIES.items()
        ]
        
        logger.info(f"Starting fetch for {len(tasks)} categories")
        
        seen = set()
        lock = asyncio.Lock()
        process_tasks = []
        pending = {t for t, _ in tasks}
        task_to_cat = {t: cat for t, cat in tasks}
        fetched_count = 0
        
        # Stream: as each fetch completes, immediately queue processing
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                cat = task_to_cat[task]
                try:
                    markets = await task
                    fetched_count += len(markets)
                    logger.info(f"{cat}: {len(markets)} raw markets")
                    for market in markets:
                        process_tasks.append(process_market(client, market, cat, seen, lock))
                except Exception as e:
                    logger.error(f"{cat}: fetch failed - {type(e).__name__}")
        
        logger.info(f"[FETCH] Total {fetched_count} raw markets fetched")
        
        # Gather all process results while client still open
        process_results = await asyncio.gather(*process_tasks, return_exceptions=True)
        processed = [r for r in process_results if not isinstance(r, Exception) and r is not None]
        
        logger.info(f"[PROCESS] {len(processed)} markets passed OI filter (${cfg.POLYMARKET_OI_MIN:,})")
        
        return processed

