#!/usr/bin/env python
"""
Polymarket Business Intelligence - Single Entry Point
Fetches market data from Polymarket API, then launches interactive dashboard.

Usage:
    python main.py
"""

import sys
import asyncio
import subprocess

from pipeline import main as ingest_main


def main():
    """Fetch data, then launch dashboard."""
    print("\n" + "="*80)
    print("POLYMARKET BUSINESS INTELLIGENCE")
    print("="*80)
    
    # Step 1: Fetch data
    print("\n[1/2] Fetching market data from Polymarket API...\n")
    try:
        asyncio.run(ingest_main())
        print("\n[OK] Data ingestion completed\n")
    except Exception as e:
        print(f"\n[ERROR] Data fetch failed: {e}\n")
        return 1
    
    # Step 2: Launch dashboard
    print("[2/2] Launching dashboard...\n")
    print("="*80)
    print("Dashboard running at: http://localhost:8501")
    print("="*80 + "\n")
    
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", "dashboard.py",
            "--server.port", "8501",
            "--logger.level", "error"
        ]
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\nDashboard stopped.")
    except Exception as e:
        print(f"[ERROR] Dashboard failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

