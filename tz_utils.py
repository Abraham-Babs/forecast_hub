#!/usr/bin/env python
"""
Timezone utility functions for consistent UTC handling across the application.
All dates should be stored and compared in UTC to avoid daylight saving time issues.
"""

from datetime import datetime, timezone
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """Get current time in UTC."""
    return datetime.now(timezone.utc)


def parse_iso_datetime(date_str: str) -> datetime | None:
    """
    Parse ISO 8601 datetime string to UTC datetime object.
    Handles both aware and naive datetimes, converting to UTC.
    
    Args:
        date_str: ISO 8601 formatted date string
        
    Returns:
        datetime in UTC, or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        # Try parsing as ISO format first
        dt = pd.to_datetime(date_str, utc=True)
        return dt.to_pydatetime()
    except Exception as e:
        logger.warning(f"Failed to parse datetime '{date_str}': {e}")
        return None


def days_until(end_date: datetime) -> int:
    """
    Calculate days remaining until end_date.
    
    Args:
        end_date: datetime in UTC
        
    Returns:
        Number of days remaining (0-based, so same day = 0)
    """
    if not end_date:
        return None
    
    try:
        # Ensure end_date is timezone-aware
        if end_date.tzinfo is None:
            logger.warning(f"Naive datetime encountered: {end_date}. Assuming UTC.")
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        current = now_utc()
        delta = end_date - current
        return delta.days  # Return actual days (negative if past, allows filtering resolved markets)
    except Exception as e:
        logger.error(f"Error calculating days_until: {e}")
        return None


def format_relative_time(dt: datetime) -> str:
    """
    Format datetime as human-readable relative time (e.g., "2h ago", "just now").
    
    Args:
        dt: datetime in UTC
        
    Returns:
        Human-readable string
    """
    if not dt:
        return "Unknown"
    
    try:
        # Ensure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        current = now_utc()
        delta = current - dt
        
        seconds = delta.total_seconds()
        minutes = seconds / 60
        hours = minutes / 60
        days = hours / 24
        
        if seconds < 60:
            return "just now"
        elif minutes < 60:
            return f"{int(minutes)}m ago"
        elif hours < 24:
            return f"{int(hours)}h ago"
        elif days < 7:
            return f"{int(days)}d ago"
        else:
            return dt.strftime("%Y-%m-%d")
    except Exception as e:
        logger.error(f"Error formatting relative time: {e}")
        return "Unknown"
