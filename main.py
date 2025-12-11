#!/usr/bin/env python
"""
Polymarket Business Intelligence - Single Entry Point
Fetches market data from Polymarket API, then launches interactive dashboard.
Automatically refreshes data every 30 minutes in background.

Usage:
    python main.py
"""

import sys
import asyncio
import subprocess
import logging
import threading
import schedule
from datetime import datetime
from pipeline import main as ingest_main
from config import validate_config, ConfigError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global flag for background thread
background_refresh_running = False
last_refresh_error = None
last_successful_refresh = None
refresh_thread = None  # Reference to thread for health checks


def run_refresh():
    """Run data refresh in background thread."""
    global last_refresh_error, last_successful_refresh
    
    try:
        logger.info("[BACKGROUND] Starting data refresh...")
        exit_code = asyncio.run(ingest_main())
        if exit_code == 0:
            logger.info("[BACKGROUND] Data refresh completed successfully")
            last_successful_refresh = datetime.now()
            last_refresh_error = None
        else:
            error_msg = f"Data refresh failed with code {exit_code}"
            logger.warning(f"[BACKGROUND] {error_msg}")
            last_refresh_error = error_msg
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"[BACKGROUND] Refresh error: {error_msg}", exc_info=False)
        last_refresh_error = error_msg


def is_refresh_thread_healthy() -> bool:
    """Check if background refresh thread is healthy and running."""
    global refresh_thread, last_successful_refresh
    
    if not refresh_thread or not refresh_thread.is_alive():
        return False
    
    # Check if refresh has completed at least once
    if last_successful_refresh is None:
        return False
    
    # Check if last refresh is too old (>7 hours = 6h refresh + 1h buffer)
    max_age_seconds = 7 * 3600
    age_seconds = (datetime.now() - last_successful_refresh).total_seconds()
    
    return age_seconds <= max_age_seconds


def background_scheduler():
    """Run scheduler in background thread with proper error handling."""
    global background_refresh_running
    
    # Schedule refresh every 6 hours (markets are event-based, resolve over days/weeks)
    schedule.every(6).hours.do(run_refresh)
    logger.info("[BACKGROUND] Scheduler started - refreshing data every 6 hours")
    
    while background_refresh_running:
        try:
            schedule.run_pending()
            # Use more reliable wait with timeout
            threading.Event().wait(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"[BACKGROUND] Scheduler error: {type(e).__name__}: {e}", exc_info=False)
            # Continue running despite errors
            threading.Event().wait(30)
    
    logger.info("[BACKGROUND] Scheduler stopped")


def main():
    """Fetch data, start background refresh, then launch dashboard."""
    global background_refresh_running
    
    print("\n" + "="*80)
    print("POLYMARKET BUSINESS INTELLIGENCE")
    print("="*80)
    
    # Step 0: Validate configuration
    print("\n[0/4] Validating configuration...\n")
    try:
        validate_config()
    except ConfigError as e:
        print(f"\n[ERROR] Configuration validation failed:\n{e}\n")
        return 1
    print("[OK] Configuration validated\n")
    print("[1/4] Fetching initial market data from Polymarket API...\n")
    try:
        exit_code = asyncio.run(ingest_main())
        if exit_code != 0:
            print(f"\n[ERROR] Initial data fetch failed with exit code {exit_code}\n")
            return 1
        print("\n[OK] Initial data ingestion completed\n")
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Data fetch cancelled by user.")
        return 130
    except Exception as e:
        print(f"\n[ERROR] Initial data fetch failed: {type(e).__name__}: {e}\n")
        logger.error(f"Pipeline error:", exc_info=True)
        return 1
    
    # Step 2: Start background refresh thread
    print("[2/4] Starting background data refresh (every 6 hours)...\n")
    background_refresh_running = True
    refresh_thread = threading.Thread(target=background_scheduler, daemon=True)
    refresh_thread.start()
    logger.info("Background refresh thread started")
    
    # Log initial health status
    if is_refresh_thread_healthy():
        logger.info("[HEALTH] Background refresh thread is healthy")
    else:
        logger.warning("[HEALTH] Background refresh thread is not yet healthy (initial state)")
    
    
    # Step 3: Launch dashboard
    print("[3/4] Launching dashboard...\n")
    print("="*80)
    print("Dashboard running at: http://localhost:8501")
    print("Data refreshes automatically every 6 hours")
    print("Press Ctrl+C to stop")
    print("="*80 + "\n")
    
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", "dashboard.py",
            "--server.port", "8501",
            "--logger.level", "error"
        ]
        result = subprocess.run(cmd)
        return result.returncode
    except FileNotFoundError:
        print("[ERROR] Streamlit not found. Install with: uv sync")
        return 1
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        background_refresh_running = False
        # Wait for background thread to stop
        refresh_thread.join(timeout=5)
        print("Dashboard stopped by user.")
        return 0
    except Exception as e:
        print(f"[ERROR] Dashboard failed: {type(e).__name__}: {e}")
        logger.error(f"Dashboard error:", exc_info=True)
        background_refresh_running = False
        return 1
    finally:
        # Ensure background thread is stopped
        background_refresh_running = False
        if refresh_thread.is_alive():
            refresh_thread.join(timeout=2)


if __name__ == "__main__":
    sys.exit(main())

