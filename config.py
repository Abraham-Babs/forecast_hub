#!/usr/bin/env python
"""
Configuration validation and initialization module.
Ensures all required environment variables are set and valid at startup.
"""

import os
import sys
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables first
load_dotenv()


class ConfigError(Exception):
    """Configuration error - raised when required settings are missing or invalid."""
    pass


def validate_config():
    """
    Validate all required environment variables and configuration.
    Raises ConfigError if validation fails.
    """
    errors = []
    
    # === REQUIRED API ENDPOINTS ===
    api_base = os.getenv("API_BASE_URL", "https://gamma-api.polymarket.com/markets")
    oi_api_base = os.getenv("OI_API_BASE_URL", "https://data-api.polymarket.com/oi")
    
    if not api_base.startswith(("http://", "https://")):
        errors.append(f"Invalid API_BASE_URL: {api_base} (must be valid HTTP/HTTPS URL)")
    if not oi_api_base.startswith(("http://", "https://")):
        errors.append(f"Invalid OI_API_BASE_URL: {oi_api_base} (must be valid HTTP/HTTPS URL)")
    
    # === DATABASE CONFIGURATION ===
    db_path = os.getenv("DATABASE_PATH", "polymarket_bi.db")
    db_dir = os.path.dirname(db_path) or "."
    
    if not os.path.isdir(db_dir):
        errors.append(f"Database directory does not exist: {db_dir}")
    if not os.access(db_dir, os.W_OK):
        errors.append(f"No write permission for database directory: {db_dir}")
    
    # === TIMEOUTS ===
    try:
        api_timeout = int(os.getenv("API_TIMEOUT_SECONDS", "10"))
        if api_timeout <= 0:
            errors.append("API_TIMEOUT_SECONDS must be > 0")
        if api_timeout > 60:
            errors.append("API_TIMEOUT_SECONDS > 60s is excessive; consider reducing")
    except ValueError:
        errors.append(f"Invalid API_TIMEOUT_SECONDS: {os.getenv('API_TIMEOUT_SECONDS')} (must be integer)")
    
    try:
        oi_timeout = int(os.getenv("OI_API_TIMEOUT_SECONDS", "8"))
        if oi_timeout <= 0:
            errors.append("OI_API_TIMEOUT_SECONDS must be > 0")
    except ValueError:
        errors.append(f"Invalid OI_API_TIMEOUT_SECONDS: {os.getenv('OI_API_TIMEOUT_SECONDS')} (must be integer)")
    
    # === VOLUME/OI THRESHOLDS ===
    try:
        min_volume = float(os.getenv("MIN_VOLUME_USD", "100000"))
        if min_volume < 0:
            errors.append("MIN_VOLUME_USD cannot be negative")
    except ValueError:
        errors.append(f"Invalid MIN_VOLUME_USD: {os.getenv('MIN_VOLUME_USD')} (must be numeric)")
    
    try:
        min_oi = float(os.getenv("MIN_OPEN_INTEREST_USD", "50000"))
        if min_oi < 0:
            errors.append("MIN_OPEN_INTEREST_USD cannot be negative")
    except ValueError:
        errors.append(f"Invalid MIN_OPEN_INTEREST_USD: {os.getenv('MIN_OPEN_INTEREST_USD')} (must be numeric)")
    
    # === RATE LIMITING ===
    try:
        per_host = int(os.getenv("API_RATE_LIMIT_PER_HOST", "20"))
        total = int(os.getenv("API_RATE_LIMIT_TOTAL", "200"))
        if per_host <= 0 or total <= 0:
            errors.append("API rate limits must be > 0")
        if per_host > total:
            errors.append(f"API_RATE_LIMIT_PER_HOST ({per_host}) cannot exceed API_RATE_LIMIT_TOTAL ({total})")
    except ValueError as e:
        errors.append(f"Invalid rate limit configuration: {e}")
    
    # === SNAPSHOT CLEANUP ===
    # Strategy: "market_active" = delete snapshots for inactive markets
    snapshot_cleanup = os.getenv("SNAPSHOT_CLEANUP_STRATEGY", "market_active").lower()
    if snapshot_cleanup not in ["market_active", "disabled"]:
        errors.append(f"Invalid SNAPSHOT_CLEANUP_STRATEGY: {snapshot_cleanup} (must be 'market_active' or 'disabled')")
    
    # === REPORT RESULTS ===
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  • {e}" for e in errors)
        logger.error(error_msg)
        raise ConfigError(error_msg)
    
    logger.info("✓ Configuration validation passed")
    return {
        "API_BASE": api_base,
        "OI_API_BASE": oi_api_base,
        "DATABASE_PATH": db_path,
        "API_TIMEOUT": api_timeout,
        "OI_API_TIMEOUT": oi_timeout,
        "MIN_VOLUME": min_volume,
        "MIN_OI": min_oi,
        "SNAPSHOT_CLEANUP_STRATEGY": snapshot_cleanup,
    }


def get_config():
    """Get validated configuration dictionary."""
    return validate_config()
