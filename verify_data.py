#!/usr/bin/env python
"""Verify database data is correct."""

import sqlite3
import json

conn = sqlite3.connect('polymarket_bi.db')
cursor = conn.cursor()

# Check a sample market
cursor.execute('SELECT id, question, liquidity, probability, outcomes, outcome_prices FROM markets LIMIT 3')
rows = cursor.fetchall()

for row in rows:
    market_id, question, liquidity, probability, outcomes, outcome_prices = row
    outcomes_list = json.loads(outcomes)
    prices_list = json.loads(outcome_prices)
    
    print(f'Question: {question}')
    print(f'Liquidity: ${liquidity:,.2f}')
    print(f'Probability: {probability:.2f}%')
    print(f'Outcomes: {outcomes_list}')
    print(f'Prices: {prices_list}')
    print()

# Count total
cursor.execute('SELECT COUNT(*) FROM markets')
total = cursor.fetchone()[0]
print(f'Total markets in database: {total}')

conn.close()
