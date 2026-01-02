#!/usr/bin/env python
"""Timezone utilities for consistent UTC handling."""

from datetime import datetime, timezone


def now_utc() -> datetime:
    """Get current time in UTC."""
    return datetime.now(timezone.utc)
