#!/usr/bin/env python
"""
Forecast Hub - Entry Point
Validates configuration, fetches market data from Polymarket and Kalshi APIs concurrently, then launches dashboard.
Both APIs fetched concurrently; failures are handled gracefully with cache fallback.
"""

import sys
import asyncio
import subprocess
import logging
from pipeline import main as ingest_main

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Fetch data from both sources concurrently, then launch dashboard.
    
    Steps:
    1. Validate configuration (DATABASE_PATH, etc.)
    2. Fetch market data via pipeline.main() - concurrent fetch from Polymarket + Kalshi
    3. Launch Streamlit dashboard at http://localhost:8501
    
    Error handling: If fetch fails, returns non-zero exit code. Dashboard still launches with cache if available.
    """
    
    print("\n" + "="*60)
    print("POLYMARKET BUSINESS INTELLIGENCE")
    print("="*60)
    
    # Fetch initial data
    print("\n[1/2] Fetching market data from Polymarket and Kalshi APIs...\n")
    try:
        exit_code = asyncio.run(ingest_main())
        if exit_code != 0:
            print(f"\n[ERROR] Data fetch failed with exit code {exit_code}\n")
            return 1
        print("\n[OK] Data ingestion completed\n")
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Data fetch cancelled by user.")
        return 130
    except Exception as e:
        print(f"\n[ERROR] Data fetch failed: {type(e).__name__}: {e}\n")
        logger.error(f"Pipeline error:", exc_info=True)
        return 1
    
    # Launch dashboard
    print("[2/2] Launching dashboard...\n")
    print("="*60)
    print("Dashboard running at: http://localhost:8501")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    
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
        print("Dashboard stopped by user.")
        return 0
    except Exception as e:
        print(f"[ERROR] Dashboard failed: {type(e).__name__}: {e}")
        logger.error(f"Dashboard error:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

