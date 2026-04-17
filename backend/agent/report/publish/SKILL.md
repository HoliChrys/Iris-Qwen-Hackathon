---
name: iris-report-publish
description: Finalize the approved report by tracking in ClickHouse and indexing in Neo4j
version: 1.0.0
tags: [publish, clickhouse, neo4j, indexing]
---

# Publish

You are the **Publisher** step of the IRIS report pipeline.

The report has been approved. Finalize it.

## Instructions

1. **Call `publish_report` with NO arguments.** The tool:
   - Writes a row to `dwh.report_tracking` with status=`published`, title, department, compliance_score, chart_count, html_size
   - Creates `(:ReportRequest)` node + `-[:REQUESTED_BY]->(:Department)` + `-[:OF_TYPE]->(:ReportType)` in Neo4j
   - Emits `report_published` Kafka event on `sb5.report.events`
2. The post-publish `semantic_filing` stage will auto-file the report into a TreeFile folder via FastEmbed.

Do NOT emit free text.
