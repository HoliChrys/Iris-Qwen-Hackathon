"""
Configuration for the AI Reporting & BI Automation example.
"""

# -- Infrastructure ----------------------------------------------------------

KAFKA_BROKER = "kafka://172.19.0.5:9092"
CLICKHOUSE_HOST = "localhost"
CLICKHOUSE_PORT = 9000
SERVICE_NAME = "iris-reporting"

# -- Topics ------------------------------------------------------------------

TOPIC_REPORT_REQUESTS = "sb5.report.requests"
TOPIC_REPORT_EVENTS = "sb5.report.events"
TOPIC_QUERY_RESULTS = "sb5.query.results"

# -- HITL (Human-in-the-Loop) -----------------------------------------------

HITL_REVIEW_TIMEOUT_SECONDS = 300.0  # 5 minutes default
HITL_DEFAULT_ROUTE = "approve"  # auto-approve on timeout

# -- Report states -----------------------------------------------------------

VALID_STATES = [
    "draft",
    "submitted",
    "interpreting",
    "fetching_data",
    "generating",
    "compliance_check",
    "pending_review",
    "revision_requested",
    "approved",
    "published",
    "rejected",
    "error",
]

# -- Supported report types --------------------------------------------------

REPORT_TYPES = [
    "daily_summary",
    "monthly_performance",
    "loan_portfolio",
    "branch_comparison",
    "risk_exposure",
    "customer_segmentation",
    "revenue_breakdown",
    "operational_kpi",
]

# -- Data domains (simulated warehouse tables) --------------------------------

DATA_DOMAINS = {
    "loans": {
        "table": "dwh.fact_loans",
        "metrics": ["total_disbursed", "outstanding_balance", "npl_ratio", "avg_interest_rate"],
        "dimensions": ["branch", "product_type", "customer_segment", "period"],
    },
    "deposits": {
        "table": "dwh.fact_deposits",
        "metrics": ["total_deposits", "avg_balance", "growth_rate", "cost_of_funds"],
        "dimensions": ["branch", "account_type", "customer_segment", "period"],
    },
    "transactions": {
        "table": "dwh.fact_transactions",
        "metrics": ["volume", "total_amount", "avg_amount", "fee_revenue"],
        "dimensions": ["channel", "transaction_type", "branch", "period"],
    },
    "customers": {
        "table": "dwh.dim_customers",
        "metrics": ["total_customers", "new_customers", "churn_rate", "avg_lifetime_value"],
        "dimensions": ["segment", "branch", "acquisition_channel", "period"],
    },
    "branches": {
        "table": "dwh.dim_branches",
        "metrics": ["profit", "cost_income_ratio", "staff_count", "efficiency_score"],
        "dimensions": ["region", "branch_type", "period"],
    },
}
