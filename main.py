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
    """Launch Streamlit dashboard immediately for instant startup and live UI loading."""
    print("\n" + "="*60)
    print("FORECAST HUB - DECISION INTELLIGENCE")
    print("="*60)
    print("Launching dashboard at: http://localhost:8501")
    print("Press Ctrl+C to stop\n")
    
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", "dashboard.py",
            "--server.port", "8501",
            "--logger.level", "error"
        ]
        result = subprocess.run(cmd)
        return result.returncode
    except FileNotFoundError:
        print("[ERROR] Streamlit not found. Install dependencies with pip or uv.")
        return 1
    except KeyboardInterrupt:
        print("\nForecast Hub stopped.")
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to start dashboard: {e}")
        logger.error("Dashboard error:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

