import os
"""
ClickHouse schema creation and data seeding for SB5 AI Reporting.

Creates the dwh (data warehouse) database with 5 fact/dimension tables
matching the DATA_DOMAINS in config.py, then seeds realistic banking data.

Tables:
    dwh.fact_loans        — Loan portfolio metrics by branch/product/segment/period
    dwh.fact_deposits     — Deposit metrics by branch/account_type/segment/period
    dwh.fact_transactions — Transaction metrics by channel/type/branch/period
    dwh.dim_customers     — Customer metrics by segment/branch/channel/period
    dwh.dim_branches      — Branch performance metrics by region/type/period

Run:
    python -m ex.sb5_ai_reporting.seed_clickhouse
"""

from __future__ import annotations

import hashlib
from typing import Any

from .clickhouse_client import ClickHouseCloud

# ClickHouse Cloud credentials
CH_HOST = os.environ.get("CH_HOST", "localhost")
CH_PASSWORD = os.environ.get("CH_PASSWORD", "")


def get_client() -> ClickHouseCloud:
    return ClickHouseCloud(host=CH_HOST, password=CH_PASSWORD)


# =============================================================================
# Schema DDL
# =============================================================================

SCHEMAS = {
    "fact_loans": """
        CREATE TABLE IF NOT EXISTS dwh.fact_loans (
            branch              String,
            product_type        String,
            customer_segment    String,
            period              String,
            total_disbursed     Float64,
            outstanding_balance Float64,
            npl_ratio           Float64,
            avg_interest_rate   Float64
        ) ENGINE = MergeTree()
        ORDER BY (period, branch)
    """,
    "fact_deposits": """
        CREATE TABLE IF NOT EXISTS dwh.fact_deposits (
            branch           String,
            account_type     String,
            customer_segment String,
            period           String,
            total_deposits   Float64,
            avg_balance      Float64,
            growth_rate      Float64,
            cost_of_funds    Float64
        ) ENGINE = MergeTree()
        ORDER BY (period, branch)
    """,
    "fact_transactions": """
        CREATE TABLE IF NOT EXISTS dwh.fact_transactions (
            channel          String,
            transaction_type String,
            branch           String,
            period           String,
            volume           UInt64,
            total_amount     Float64,
            avg_amount       Float64,
            fee_revenue      Float64
        ) ENGINE = MergeTree()
        ORDER BY (period, channel)
    """,
    "dim_customers": """
        CREATE TABLE IF NOT EXISTS dwh.dim_customers (
            segment             String,
            branch              String,
            acquisition_channel String,
            period              String,
            total_customers     UInt64,
            new_customers       UInt64,
            churn_rate          Float64,
            avg_lifetime_value  Float64
        ) ENGINE = MergeTree()
        ORDER BY (period, segment)
    """,
    "dim_branches": """
        CREATE TABLE IF NOT EXISTS dwh.dim_branches (
            region           String,
            branch_type      String,
            branch           String,
            period           String,
            profit           Float64,
            cost_income_ratio Float64,
            staff_count      UInt32,
            efficiency_score Float64
        ) ENGINE = MergeTree()
        ORDER BY (period, region)
    """,
}

# Report tracking table for persisting pipeline results
REPORT_TRACKING_SCHEMA = """
    CREATE TABLE IF NOT EXISTS dwh.report_tracking (
        request_id       String,
        requester_id     String,
        department       String,
        query_text       String,
        report_type      String,
        status           String,
        report_title     String,
        chart_count      UInt32,
        compliance_score Float64,
        compliance_passed UInt8,
        created_at       DateTime DEFAULT now(),
        completed_at     Nullable(DateTime)
    ) ENGINE = MergeTree()
    ORDER BY (created_at, request_id)
"""


# =============================================================================
# Data generation
# =============================================================================

def _det_float(seed: str, lo: float, hi: float) -> float:
    """Deterministic float from a seed."""
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return round(lo + (h % 10000) / 10000 * (hi - lo), 2)


def _det_int(seed: str, lo: int, hi: int) -> int:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return lo + (h % (hi - lo))


BRANCHES = ["HQ", "Branch-A", "Branch-B", "Branch-C", "Branch-D",
            "Branch-E", "Branch-F", "Branch-G"]
PRODUCTS = ["Personal Loan", "Mortgage", "Business Loan", "Auto Loan"]
SEGMENTS = ["Retail", "SME", "Corporate", "Premium"]
PERIODS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"]
CHANNELS = ["Mobile", "ATM", "Branch", "Online"]
TX_TYPES = ["Transfer", "Payment", "Withdrawal", "Deposit"]
ACCOUNT_TYPES = ["Savings", "Current", "Fixed Deposit", "Recurring"]
REGIONS = ["North", "South", "East", "West", "Central"]
BRANCH_TYPES = ["Full Service", "Express", "Digital", "Regional Hub"]
ACQ_CHANNELS = ["Digital", "Branch", "Referral", "Campaign"]


def generate_loans() -> tuple[list[str], list[list[Any]]]:
    cols = ["branch", "product_type", "customer_segment", "period",
            "total_disbursed", "outstanding_balance", "npl_ratio", "avg_interest_rate"]
    rows = []
    for branch in BRANCHES:
        for product in PRODUCTS:
            for segment in SEGMENTS:
                for period in PERIODS:
                    seed = f"loans-{branch}-{product}-{segment}-{period}"
                    rows.append([
                        branch, product, segment, period,
                        _det_float(seed + "-disb", 500_000, 50_000_000),
                        _det_float(seed + "-bal", 200_000, 30_000_000),
                        _det_float(seed + "-npl", 0.01, 0.08),
                        _det_float(seed + "-rate", 0.04, 0.12),
                    ])
    return cols, rows


def generate_deposits() -> tuple[list[str], list[list[Any]]]:
    cols = ["branch", "account_type", "customer_segment", "period",
            "total_deposits", "avg_balance", "growth_rate", "cost_of_funds"]
    rows = []
    for branch in BRANCHES:
        for acct in ACCOUNT_TYPES:
            for segment in SEGMENTS:
                for period in PERIODS:
                    seed = f"dep-{branch}-{acct}-{segment}-{period}"
                    rows.append([
                        branch, acct, segment, period,
                        _det_float(seed + "-dep", 1_000_000, 80_000_000),
                        _det_float(seed + "-avg", 5_000, 500_000),
                        _det_float(seed + "-gr", -0.05, 0.15),
                        _det_float(seed + "-cof", 0.02, 0.06),
                    ])
    return cols, rows


def generate_transactions() -> tuple[list[str], list[list[Any]]]:
    cols = ["channel", "transaction_type", "branch", "period",
            "volume", "total_amount", "avg_amount", "fee_revenue"]
    rows = []
    for channel in CHANNELS:
        for tx_type in TX_TYPES:
            for branch in BRANCHES:
                for period in PERIODS:
                    seed = f"tx-{channel}-{tx_type}-{branch}-{period}"
                    vol = _det_int(seed + "-vol", 1_000, 100_000)
                    total = _det_float(seed + "-total", 500_000, 20_000_000)
                    rows.append([
                        channel, tx_type, branch, period,
                        vol, total,
                        round(total / vol, 2) if vol > 0 else 0,
                        _det_float(seed + "-fee", 10_000, 2_000_000),
                    ])
    return cols, rows


def generate_customers() -> tuple[list[str], list[list[Any]]]:
    cols = ["segment", "branch", "acquisition_channel", "period",
            "total_customers", "new_customers", "churn_rate", "avg_lifetime_value"]
    rows = []
    for segment in SEGMENTS:
        for branch in BRANCHES:
            for acq in ACQ_CHANNELS:
                for period in PERIODS:
                    seed = f"cust-{segment}-{branch}-{acq}-{period}"
                    rows.append([
                        segment, branch, acq, period,
                        _det_int(seed + "-total", 100, 50_000),
                        _det_int(seed + "-new", 5, 2_000),
                        _det_float(seed + "-churn", 0.01, 0.10),
                        _det_float(seed + "-ltv", 5_000, 200_000),
                    ])
    return cols, rows


def generate_branches() -> tuple[list[str], list[list[Any]]]:
    cols = ["region", "branch_type", "branch", "period",
            "profit", "cost_income_ratio", "staff_count", "efficiency_score"]
    rows = []
    for region in REGIONS:
        for btype in BRANCH_TYPES:
            for branch in BRANCHES:
                for period in PERIODS:
                    seed = f"br-{region}-{btype}-{branch}-{period}"
                    rows.append([
                        region, btype, branch, period,
                        _det_float(seed + "-profit", 100_000, 10_000_000),
                        _det_float(seed + "-cir", 0.30, 0.75),
                        _det_int(seed + "-staff", 5, 200),
                        _det_float(seed + "-eff", 0.50, 0.98),
                    ])
    return cols, rows


# =============================================================================
# Main seed function
# =============================================================================

GENERATORS = {
    "fact_loans": generate_loans,
    "fact_deposits": generate_deposits,
    "fact_transactions": generate_transactions,
    "dim_customers": generate_customers,
    "dim_branches": generate_branches,
}


def seed(drop_existing: bool = False) -> dict[str, int]:
    """Create schema and seed all tables.

    Args:
        drop_existing: If True, drop and recreate tables.

    Returns:
        Dict mapping table name to row count inserted.
    """
    ch = get_client()
    print(f"Connected to ClickHouse {ch.query_scalar('SELECT version()')}")

    # Create database
    ch.command("CREATE DATABASE IF NOT EXISTS dwh")
    print("Database 'dwh' ready")

    # Create report tracking table
    ch.command(REPORT_TRACKING_SCHEMA)
    print("Table 'dwh.report_tracking' ready")

    results = {}

    for table_name, ddl in SCHEMAS.items():
        if drop_existing:
            ch.command(f"DROP TABLE IF EXISTS dwh.{table_name}")
            print(f"  Dropped dwh.{table_name}")

        ch.command(ddl)
        print(f"  Created dwh.{table_name}")

        # Check if already seeded
        count = ch.query_scalar(f"SELECT count() FROM dwh.{table_name}")
        if count > 0 and not drop_existing:
            print(f"  Already has {count} rows, skipping seed")
            results[table_name] = count
            continue

        # Generate and insert data
        gen_fn = GENERATORS.get(table_name)
        if gen_fn is None:
            continue

        cols, rows = gen_fn()
        print(f"  Generated {len(rows)} rows...")

        # Insert in batches of 500
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            ch.insert(table_name, cols, batch, database="dwh")

        final_count = ch.query_scalar(f"SELECT count() FROM dwh.{table_name}")
        results[table_name] = final_count
        print(f"  Seeded: {final_count} rows")

    return results


def verify() -> None:
    """Verify all tables exist and show row counts."""
    ch = get_client()

    print("ClickHouse Cloud verification:")
    print(f"  Host: {ch.host}")
    print(f"  Version: {ch.query_scalar('SELECT version()')}")
    print()

    for table_name in SCHEMAS:
        try:
            count = ch.query_scalar(f"SELECT count() FROM dwh.{table_name}")
            sample = ch.query(f"SELECT * FROM dwh.{table_name} LIMIT 2")
            print(f"  dwh.{table_name}: {count} rows")
            if sample:
                cols = list(sample[0].keys())
                print(f"    Columns: {', '.join(cols)}")
        except Exception as e:
            print(f"  dwh.{table_name}: ERROR - {e}")

    # Check report tracking
    try:
        count = ch.query_scalar("SELECT count() FROM dwh.report_tracking")
        print(f"  dwh.report_tracking: {count} rows")
    except Exception as e:
        print(f"  dwh.report_tracking: ERROR - {e}")


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    import sys

    if "--verify" in sys.argv:
        verify()
    elif "--drop" in sys.argv:
        results = seed(drop_existing=True)
        print(f"\nDone! Tables seeded: {results}")
    else:
        results = seed()
        print(f"\nDone! Tables seeded: {results}")
