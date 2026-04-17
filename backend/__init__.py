"""
IRIS — Intelligent Reporting & Insight System

AI-powered BI reporting platform built on Tachikoma.
Interprets natural-language queries, fetches data from ClickHouse,
generates reports with SVG charts, validates compliance, and
supports human-in-the-loop review before publishing.

Architecture:
    Uses Tachikoma Hive (WoT mode) + StatefulRecord for a serverless
    AI-driven reporting pipeline:

    1. User submits a natural-language query
    2. QueryInterpreter agent translates to structured data request
    3. DataFetcher retrieves data from ClickHouse Cloud
    4. ReportGenerator agent formats results into report
    5. ChartRenderer renders SVG charts from blackbox specs
    6. ComplianceChecker agent validates data governance rules
    7. Human reviewer approves or sends back for revision
    8. Approved report is published and indexed in ClickHouse + Neo4j
"""
__version__ = "0.3.0"
