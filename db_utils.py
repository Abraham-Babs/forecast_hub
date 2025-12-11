#!/usr/bin/env python
"""
Shared database utility functions.
Centralized retry logic for database operations.
"""

import sqlite3
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


def retry_on_db_lock(max_retries: int = 3, initial_delay: float = 0.1):
    """
    Decorator to retry database operations on lock with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles on each retry)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        last_error = e
                        if attempt < max_retries - 1:
                            logger.warning(f"[DB LOCK] Attempt {attempt + 1}/{max_retries}: retrying in {delay:.2f}s")
                            time.sleep(delay)
                            delay *= 2  # Exponential backoff
                        continue
                    raise
                except Exception:
                    raise
            # If all retries exhausted, raise last error
            logger.error(f"[DB LOCK] Failed after {max_retries} attempts: {last_error}")
            raise last_error
        return wrapper
    return decorator
