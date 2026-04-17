---
name: iris-search
description: Search existing reports across Neo4j, ClickHouse, and Graphiti
version: 1.0.0
tags: [search, neo4j, clickhouse, graphiti]
---

# Report Search

When the user wants to find existing reports, this skill searches across multiple backends.

## Search Backends

### 1. Neo4j Aura (Graph Search)
- Host: `7ed108be.databases.neo4j.io`
- Searches: ReportRequest nodes, Department relationships, Chart relationships
- Query: Full-text match on query_text, report_type, department, entity_id
- Returns: report_id, state, query_text, report_type, department, chart_count

### 2. ClickHouse Cloud (SQL Search)
- Host: `nl5th0k8zt.germanywestcentral.azure.clickhouse.cloud`
- Table: `dwh.report_tracking`
- Query: LIKE match on report_title, department, report_type, query_text
- Returns: request_id, department, report_type, report_title, status, chart_count, compliance_score

### 3. Graphiti (Semantic Search) — future
- Semantic vector search across indexed StatefulRecords
- Finds reports by meaning, not just keywords
- Example: "reports about credit risk" finds reports titled "NPL Analysis"

## How to Search

Call the `search_reports` tool with:
- **query**: The user's search text
- **max_results**: Number of results (default 10)

The tool automatically:
1. Queries all available backends
2. Merges and deduplicates results by request_id
3. Returns results with source attribution

## Result Format

Each result includes:
- `source`: "neo4j" | "clickhouse" | "graphiti"
- `report_id` / `request_id`: Unique identifier
- `report_title` / `query_text`: What the report is about
- `department`: Which department requested it
- `report_type`: loan_portfolio, daily_summary, branch_comparison, etc.
- `status` / `state`: published, pending_review, etc.
- `chart_count`: Number of charts in the report
- `compliance_score`: Governance score (0.0-1.0)

## Search Tips
- Use domain-specific terms: "loans", "deposits", "transactions"
- Filter by department: "Strategy Division", "ICT", "DIC"
- Filter by type: "loan_portfolio", "daily_summary", "branch_comparison"
- Recent reports appear first (sorted by created_at DESC)
