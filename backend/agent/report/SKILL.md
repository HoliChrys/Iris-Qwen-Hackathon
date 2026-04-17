---
name: iris-report
description: Generate AI-powered banking reports from natural language queries
version: 1.0.0
tags: [report, pipeline, charts, compliance]
---

# Report Generation Pipeline

When the user requests a new report, this skill executes a 7-step pipeline:

## Pipeline Steps

### 1. Query Interpretation
Parse the natural language query into structured parameters:
- **domain**: loans, deposits, transactions, customers, branches
- **metrics**: total_disbursed, outstanding_balance, npl_ratio, etc.
- **dimensions**: branch, product_type, customer_segment, period, etc.
- **time_range**: last_month, last_quarter, last_year, ytd
- **confidence**: 0.0-1.0

### 2. Data Fetch
Query ClickHouse Cloud data warehouse:
- Host: `nl5th0k8zt.germanywestcentral.azure.clickhouse.cloud`
- Database: `dwh`
- Tables: `fact_loans`, `fact_deposits`, `fact_transactions`, `dim_customers`, `dim_branches`
- Returns rows with the requested metrics grouped by dimensions

### 3. Report Generation
Generate a structured report with:
- Title
- Executive summary (2-3 sentences)
- Data-driven sections with analysis
- Chart type suggestions per section (bar, line, pie)
- Methodology note

### 4. Chart Rendering
For each section with a chart type:
- Build XML report with `<blackbox tag="chart">` placeholders
- Run chart sub-pipeline: elaborate → implement (SVG) → test → verify
- Replace blackboxes with rendered `<chart>` elements
- Convert final XML to HTML

### 5. Compliance Check
Validate against banking data governance rules:
- DQ001: Minimum 3 data rows
- DQ002: No negative monetary values
- AC001: No PII exposure
- ACC001: Methodology mentioned
- ACC002: Executive summary present

### 6. Human Review
Auto-approve if compliance score >= 0.8. Otherwise request revision.

### 7. Publish
- Track in ClickHouse (`dwh.report_tracking`)
- Index in Neo4j Aura (graph relationships)
- Publish event to Redpanda (`sb5.report.events`)

## Available Data Domains

| Domain | Table | Key Metrics |
|--------|-------|-------------|
| loans | dwh.fact_loans | total_disbursed, outstanding_balance, npl_ratio, avg_interest_rate |
| deposits | dwh.fact_deposits | total_deposits, avg_balance, growth_rate, cost_of_funds |
| transactions | dwh.fact_transactions | volume, total_amount, avg_amount, fee_revenue |
| customers | dwh.dim_customers | total_customers, new_customers, churn_rate, avg_lifetime_value |
| branches | dwh.dim_branches | profit, cost_income_ratio, staff_count, efficiency_score |

## Output
The pipeline produces:
- HTML report with embedded SVG charts
- XML structured report
- Compliance score and issues
- Published status in ClickHouse + Neo4j
