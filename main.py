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
from pathlib import Path
from pipeline import main as ingest_main

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global flag for background thread
background_refresh_running = False


def run_refresh():
    """Run data refresh in background thread."""
    try:
        logger.info("[BACKGROUND] Starting data refresh...")
        exit_code = asyncio.run(ingest_main())
        if exit_code == 0:
            logger.info("[BACKGROUND] Data refresh completed successfully")
        else:
            logger.warning(f"[BACKGROUND] Data refresh failed with code {exit_code}")
    except Exception as e:
        logger.error(f"[BACKGROUND] Refresh error: {type(e).__name__}: {e}", exc_info=False)


def background_scheduler():
    """Run scheduler in background thread."""
    global background_refresh_running
    
    # Schedule refresh every 30 minutes
    schedule.every(30).minutes.do(run_refresh)
    logger.info("[BACKGROUND] Scheduler started - refreshing data every 30 minutes")
    
    while background_refresh_running:
        schedule.run_pending()
        threading.Event().wait(30)  # Check every 30 seconds


def main():
    """Fetch data, start background refresh, then launch dashboard."""
    global background_refresh_running
    
    print("\n" + "="*80)
    print("POLYMARKET BUSINESS INTELLIGENCE")
    print("="*80)
    
    # Step 1: Initial data fetch
    print("\n[1/3] Fetching initial market data from Polymarket API...\n")
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
    print("[2/3] Starting background data refresh (every 30 minutes)...\n")
    background_refresh_running = True
    refresh_thread = threading.Thread(target=background_scheduler, daemon=True)
    refresh_thread.start()
    logger.info("Background refresh thread started")
    
    # Step 3: Launch dashboard
    print("[3/3] Launching dashboard...\n")
    print("="*80)
    print("Dashboard running at: http://localhost:8501")
    print("Data refreshes automatically every 30 minutes")
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
        print("\n\nDashboard stopped by user.")
        background_refresh_running = False
        return 0
    except Exception as e:
        print(f"[ERROR] Dashboard failed: {type(e).__name__}: {e}")
        logger.error(f"Dashboard error:", exc_info=True)
        background_refresh_running = False
        return 1


if __name__ == "__main__":
    sys.exit(main())

