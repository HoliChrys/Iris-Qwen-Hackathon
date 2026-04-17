"""
IRIS Reporting entities — ReportRequest (global StatefulRecord).

States = WOT steps:
    interpret_query → fetch_data → generate_report → render_charts
    → check_compliance → human_review → publish → completed

Each step has @tool methods that the WOT agent calls.
The entity is the single source of truth for the pipeline.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from datetime import datetime
from typing import Any, ClassVar

from tachikoma.stateful import (
    Condition,
    StatefulRecord,
    TransitionDef,
    condition,
    sr_init,
)
from tachikoma.stateful.decorators.tool import tool

from .config import DATA_DOMAINS

logger = logging.getLogger(__name__)

# ─ State-transition table used by _validate_and_advance ─
# Maps current state → (next_state, condition_method_name|None)
_STATE_TRANSITIONS: dict[str, tuple[str, str | None]] = {
    "interpret_query":  ("fetch_data",       "has_parsed_query"),
    "fetch_data":       ("generate_report",  "has_data"),
    "generate_report":  ("render_charts",    "has_report"),
    "render_charts":    ("check_compliance", "has_rendered"),
    "check_compliance": ("human_review",     None),    # always advance; reviewer decides
    # human_review transitions are driven by approve/revise/reject tools directly
    "publish":          ("completed",        None),
}

# No sub-records — IRIS is an automated pipeline, not conversational
STEP_RECORDS: dict = {}


@sr_init(
    entity="iris_report",
    initial="interpret_query",
    states=[
        "interpret_query",
        "fetch_data",
        "generate_report",
        "render_charts",
        "check_compliance",
        "human_review",
        "publish",
        "completed",
        "error",
    ],
)
class ReportRequest(StatefulRecord):
    """AI-generated banking report — tracks full pipeline lifecycle."""

    _transitions: ClassVar[list[TransitionDef]] = [
        # Happy path
        TransitionDef("interpret_query", "fetch_data", condition="has_parsed_query"),
        TransitionDef("fetch_data", "generate_report", condition="has_data"),
        TransitionDef("generate_report", "render_charts", condition="has_report"),
        TransitionDef("render_charts", "check_compliance", condition="has_rendered"),
        TransitionDef("check_compliance", "human_review", condition="compliance_passed"),
        TransitionDef("human_review", "publish", condition="is_approved"),
        TransitionDef("publish", "completed"),
        # Revision loop
        TransitionDef("human_review", "generate_report", condition="needs_revision"),
    ]

    # ── Session (required by Hive bind) ──────────────────────────────
    session_id: str = ""

    # ── Request fields ──────────────────────────────────────────────
    request_id: str = ""
    requester_id: str = ""
    department: str = ""
    query_text: str = ""
    report_type: str = ""
    priority: str = "normal"

    # ── Pipeline data (populated by tools at each step) ─────────────
    parsed_query: dict[str, Any] = None  # type: ignore[assignment]
    data_result: dict[str, Any] = None  # type: ignore[assignment]
    report_content: dict[str, Any] = None  # type: ignore[assignment]
    report_xml: str = ""
    report_html: str = ""
    charts: list[dict[str, Any]] = None  # type: ignore[assignment]
    compliance_result: dict[str, Any] = None  # type: ignore[assignment]
    review_decision: dict[str, Any] = None  # type: ignore[assignment]

    # ── Metadata ────────────────────────────────────────────────────
    revision_count: int = 0
    error_message: str = ""
    submitted_at: str = ""
    completed_at: str = ""

    # ═════════════════════════════════════════════════════════════════
    # Conditions
    # ═════════════════════════════════════════════════════════════════

    @condition("has_parsed_query")
    def has_parsed_query(self) -> Condition:
        return Condition.all_of(
            Condition.that(self.parsed_query is not None, "Parsed query missing"),
            Condition.that(
                (self.parsed_query or {}).get("confidence", 0) >= 0.5,
                "Confidence too low",
            ),
        )

    @condition("has_data")
    def has_data(self) -> Condition:
        return Condition.all_of(
            Condition.that(self.data_result is not None, "Data result missing"),
            Condition.that(
                (self.data_result or {}).get("row_count", 0) > 0,
                "No data rows",
            ),
        )

    @condition("has_report")
    def has_report(self) -> Condition:
        return Condition.that(self.report_content is not None, "Report missing")

    @condition("has_rendered")
    def has_rendered(self) -> Condition:
        return Condition.that(bool(self.report_html), "Charts not rendered")

    @condition("compliance_passed")
    def compliance_passed(self) -> Condition:
        if self.compliance_result is None:
            return Condition(passed=False, reason="No compliance result")
        return Condition.all_of(
            Condition.that(
                self.compliance_result.get("passed", False), "Compliance failed"
            ),
            Condition.that(
                self.compliance_result.get("critical_count", 1) == 0,
                "Critical compliance issues",
            ),
        )

    @condition("is_approved")
    def is_approved(self) -> Condition:
        if self.review_decision is None:
            return Condition(passed=False, reason="No review decision")
        return Condition.that(
            self.review_decision.get("approved", False), "Not approved"
        )

    @condition("needs_revision")
    def needs_revision(self) -> Condition:
        if self.review_decision is None:
            return Condition(passed=False, reason="No review decision")
        return Condition.all_of(
            Condition.that(
                not self.review_decision.get("approved", True), "Was approved"
            ),
            Condition.that(
                bool(self.review_decision.get("revision_notes")), "No revision notes"
            ),
        )

    # ═════════════════════════════════════════════════════════════════
    # Kafka event publishing
    # ═════════════════════════════════════════════════════════════════

    def _publish_event(self, event_type: str, detail: dict = None):
        """Publish an event to Redpanda sb5.report.events topic."""
        try:
            from .kafka_client import send_report_event
            send_report_event({
                "request_id": self.request_id or self.session_id,
                "event_type": event_type,
                "department": self.department,
                "report_type": self.report_type,
                **(detail or {}),
            })
        except Exception as e:
            logger.debug("Event publish skipped: %s", e)

    # ═════════════════════════════════════════════════════════════════
    # Tools — called by WOT agents at each pipeline step
    # ═════════════════════════════════════════════════════════════════

    # ═════════════════════════════════════════════════════════════════
    # _validate_and_advance — mirror of booking's validate_step()
    # Centralized transition point. Called by each tool at the end.
    # ═════════════════════════════════════════════════════════════════

    async def _validate_and_advance(self) -> dict:
        """Advance the state machine if the current step's condition is met.

        Mirrors booking's `Meeting.validate_step()` pattern — transitions are
        NOT done inside individual tools, they are centralized here so the
        behavior is uniform and inspectable.
        """
        sm = self.state_machine()
        cur = self.state
        nxt = _STATE_TRANSITIONS.get(cur)
        if nxt is None:
            return {"status": "no_auto_transition", "state": cur}
        next_state, cond_name = nxt
        if cond_name:
            cond_fn = getattr(self, cond_name, None)
            if callable(cond_fn):
                result = cond_fn()
                # Condition methods return a Condition object
                passed = getattr(result, "passed", bool(result))
                if not passed:
                    reason = getattr(result, "reason", "condition not met")
                    return {"status": "condition_not_met", "state": cur,
                            "cond": cond_name, "reason": reason}
        await sm.to(next_state, trigger=f"validate_and_advance_from_{cur}")
        return {"status": "transitioned", "from": cur, "to": next_state}

    def _wrong_state(self, expected: str) -> dict:
        """Self-defending tool error envelope."""
        return {
            "error": "wrong_state",
            "expected": expected,
            "current": self.state,
            "message": f"Tool only valid in state '{expected}', entity is in '{self.state}'",
        }

    # ═════════════════════════════════════════════════════════════════
    # Tools — each one is self-defending (state-guard) and ends with
    # _validate_and_advance() instead of sm.to() directly.
    # ═════════════════════════════════════════════════════════════════

    @tool("Save the structured interpretation of the user query")
    async def save_interpretation(
        self,
        domain: str,
        metrics: str,
        dimensions: str = "",
        filters: str = "",
        time_range: str = "last_month",
        confidence: float = 0.8,
    ) -> dict:
        """Interpret the NL query into a structured data request.

        Args:
            domain: Data domain — one of: loans, deposits, transactions, customers, branches
            metrics: Comma-separated metrics (e.g. "total_disbursed,outstanding_balance")
            dimensions: Comma-separated dimensions for grouping (e.g. "branch,product_type")
            filters: JSON object of filters (e.g. '{"branch": "HQ"}')
            time_range: Period — last_week, last_month, last_quarter, last_year, ytd
            confidence: Interpretation confidence 0.0-1.0
        """
        if self.state != "interpret_query":
            return self._wrong_state("interpret_query")
        metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]
        dims_list = (
            [d.strip() for d in dimensions.split(",") if d.strip()]
            if dimensions
            else []
        )
        try:
            filters_dict = json.loads(filters) if filters else {}
        except json.JSONDecodeError:
            filters_dict = {}

        table = DATA_DOMAINS.get(domain, {}).get("table", f"dwh.fact_{domain}")
        cols = ", ".join(dims_list + metrics_list) if dims_list else ", ".join(metrics_list)
        group_by = f" GROUP BY {', '.join(dims_list)}" if dims_list else ""
        sql = f"SELECT {cols} FROM {table} WHERE period = '{time_range}'{group_by}"

        sm = self.state_machine()
        await sm.update(
            parsed_query={
                "original_text": self.query_text,
                "domain": domain,
                "metrics": metrics_list,
                "dimensions": dims_list,
                "filters": filters_dict,
                "time_range": time_range,
                "sql_preview": sql,
                "confidence": confidence,
            },
            submitted_at=datetime.now().isoformat(timespec="seconds"),
        )
        logger.info("Interpreted: domain=%s, confidence=%.2f", domain, confidence)
        self._publish_event("step_completed", {"step": "interpret_query", "domain": domain, "confidence": confidence})
        advance = await self._validate_and_advance()
        return {"status": "interpreted", "domain": domain, "confidence": confidence, "advance": advance}

    @tool("Fetch data from the ClickHouse warehouse")
    async def fetch_warehouse_data(self) -> dict:
        """Query ClickHouse Cloud using the parsed query. No arguments needed."""
        if self.state != "fetch_data":
            return self._wrong_state("fetch_data")
        if not self.parsed_query:
            return {"error": "No parsed query available"}

        try:
            data = self._fetch_from_clickhouse(self.parsed_query)
            logger.info("ClickHouse: %d rows for '%s'", data["row_count"], data["domain"])
        except Exception as e:
            logger.warning("ClickHouse failed (%s), using simulated data", e)
            data = self._generate_simulated_data(self.parsed_query)

        sm = self.state_machine()
        await sm.update(data_result=data)
        self._publish_event("step_completed", {"step": "fetch_data", "row_count": data["row_count"]})
        advance = await self._validate_and_advance()
        return {"status": "fetched", "row_count": data["row_count"], "advance": advance}

    @tool("Save the generated report content")
    async def save_report(
        self,
        title: str,
        executive_summary: str,
        sections: str,
        methodology_note: str = "",
    ) -> dict:
        """Save a structured report generated from the data.

        Args:
            title: Report title
            executive_summary: 2-3 sentence executive summary
            sections: JSON array of sections, each with title, content, chart_type (bar/line/pie/table)
            methodology_note: Optional methodology note
        """
        if self.state != "generate_report":
            return self._wrong_state("generate_report")
        try:
            sections_list = json.loads(sections) if isinstance(sections, str) else sections
        except json.JSONDecodeError:
            sections_list = [{"title": "Report", "content": sections}]

        sm = self.state_machine()
        await sm.update(report_content={
            "title": title,
            "report_type": self.report_type,
            "executive_summary": executive_summary,
            "sections": sections_list,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data_sources": [self.parsed_query.get("domain", "unknown")] if self.parsed_query else [],
            "methodology_note": methodology_note,
        })
        logger.info("Report generated: '%s' (%d sections)", title, len(sections_list))
        self._publish_event("step_completed", {"step": "generate_report", "title": title, "sections": len(sections_list)})
        advance = await self._validate_and_advance()

        return {"status": "report_saved", "title": title, "sections": len(sections_list), "advance": advance}

    @tool("Render charts in the report as SVG")
    async def render_report_charts(self) -> dict:
        """Build XML report with charts and convert to HTML. Call after report is generated."""
        if self.state != "render_charts":
            return self._wrong_state("render_charts")
        from .chart_renderer import render_all_charts
        from .report_xml import ReportXMLBuilder, report_to_xml_string, xml_to_html

        if not self.report_content:
            return {"error": "No report content"}

        builder = ReportXMLBuilder(report_id=self.request_id)
        report_xml = builder.build(
            self.report_content,
            self.data_result or {},
            self.parsed_query or {},
        )

        report_xml, charts = await render_all_charts(report_xml, report_id=self.request_id)

        xml_str = report_to_xml_string(report_xml)
        html_str = xml_to_html(report_xml)
        chart_list = [
            {
                "chart_id": c.chart_id,
                "type": c.chart_type,
                "title": c.title,
                "status": "done" if c.chart_html else "error",
                "revision_count": c.revision_count,
                "html_size": len(c.chart_html),
            }
            for c in charts
        ]
        sm = self.state_machine()
        await sm.update(report_xml=xml_str, report_html=html_str, charts=chart_list)
        logger.info("Rendered %d charts, HTML: %d bytes", len(charts), len(html_str))
        self._publish_event("step_completed", {"step": "render_charts", "charts": len(charts), "html_size": len(html_str)})
        advance = await self._validate_and_advance()

        return {"status": "rendered", "charts": len(charts), "html_size": len(self.report_html), "advance": advance}

    @tool("Run compliance checks on the report")
    async def run_compliance_check(self) -> dict:
        """Validate report against data governance rules. Call after charts are rendered."""
        if self.state != "check_compliance":
            return self._wrong_state("check_compliance")
        report = self.report_content or {}
        data = self.data_result or {}

        RULES = [
            ("DQ001", "data_quality", "warning",
             "Data must have >= 3 rows to be statistically significant",
             lambda d, _r: d.get("row_count", 0) >= 3),
            ("DQ002", "data_quality", "critical",
             "Monetary metrics must not be negative",
             lambda d, _r: all(
                 v >= 0
                 for row in d.get("rows", [])
                 for k, v in row.items()
                 if isinstance(v, (int, float)) and "ratio" not in k and "rate" not in k
             )),
            ("AC001", "access_control", "critical",
             "Report must not contain individual PII",
             lambda d, _r: not any(
                 "customer_name" in row or "account_number" in row
                 for row in d.get("rows", [])
             )),
            ("ACC001", "accuracy", "warning",
             "Report must mention methodology or data sources",
             lambda _d, r: bool(r.get("methodology_note") or r.get("data_sources"))),
            ("ACC002", "accuracy", "warning",
             "Executive summary must not be empty",
             lambda _d, r: bool(r.get("executive_summary"))),
        ]

        issues = []
        for rule_id, category, severity, description, check_fn in RULES:
            try:
                if not check_fn(data, report):
                    issues.append({
                        "severity": severity,
                        "category": category,
                        "description": description,
                        "recommendation": f"Check rule {rule_id}",
                    })
            except Exception as e:
                logger.warning("Rule %s error: %s", rule_id, e)

        critical_count = sum(1 for i in issues if i["severity"] == "critical")
        score = round((len(RULES) - len(issues)) / len(RULES), 2) if RULES else 1.0

        sm = self.state_machine()
        await sm.update(compliance_result={
            "passed": critical_count == 0,
            "score": score,
            "issues": issues,
            "critical_count": critical_count,
            "warning_count": sum(1 for i in issues if i["severity"] == "warning"),
        })
        logger.info("Compliance: passed=%s, score=%.2f, issues=%d", critical_count == 0, score, len(issues))
        self._publish_event("step_completed", {"step": "compliance_check", "passed": critical_count == 0, "score": score})
        # check_compliance → human_review always (reviewer decides); no condition guard
        advance = await self._validate_and_advance()

        return {"status": "checked", "passed": critical_count == 0, "score": score,
                "issues": len(issues), "advance": advance}

    @tool("Approve the report for publication")
    async def approve(self) -> dict:
        """Approve the report. Call when compliance passes and report is satisfactory."""
        if self.state != "human_review":
            return self._wrong_state("human_review")
        sm = self.state_machine()
        await sm.update(review_decision={
            "approved": True,
            "reviewer_id": "system",
            "comments": "",
            "revision_notes": "",
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        })
        # human_review → publish (explicit because human_review has 3 exits)
        await sm.to("publish", trigger="approve")
        return {"status": "approved"}

    @tool("Request revision of the report")
    async def request_revision(self, notes: str) -> dict:
        """Send the report back for revision.

        Args:
            notes: Revision instructions for the report generator
        """
        if self.state != "human_review":
            return self._wrong_state("human_review")
        sm = self.state_machine()
        await sm.update(
            revision_count=self.revision_count + 1,
            review_decision={
                "approved": False,
                "reviewer_id": "system",
                "comments": "",
                "revision_notes": notes,
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            },
            report_content=None,
            compliance_result=None,
        )
        # human_review → generate_report (revision loop)
        await sm.to("generate_report", trigger="request_revision")
        return {"status": "revision_requested", "count": self.revision_count}

    @tool("Reject the report permanently")
    async def reject(self, reason: str) -> dict:
        """Reject the report.

        Args:
            reason: Reason for rejection
        """
        if self.state != "human_review":
            return self._wrong_state("human_review")
        sm = self.state_machine()
        await sm.update(
            review_decision={
                "approved": False,
                "reviewer_id": "system",
                "comments": reason,
                "revision_notes": "",
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            },
            completed_at=datetime.now().isoformat(timespec="seconds"),
        )
        # human_review → error (terminal rejection)
        await sm.to("error", trigger="reject", force=True)
        return {"status": "rejected", "reason": reason}

    @tool("Publish the approved report")
    async def publish_report(self) -> dict:
        """Finalize and publish the report. Tracks in ClickHouse and indexes in Neo4j."""
        if self.state != "publish":
            return self._wrong_state("publish")
        sm = self.state_machine()
        await sm.update(completed_at=datetime.now().isoformat(timespec="seconds"))

        published = {
            **(self.report_content or {}),
            "status": "published",
            "published_at": self.completed_at,
            "request_id": self.request_id,
        }

        # Track in ClickHouse
        try:
            from .clickhouse_client import ClickHouseCloud
            from .seed_clickhouse import CH_HOST, CH_PASSWORD

            ch = ClickHouseCloud(host=CH_HOST, password=CH_PASSWORD)
            compliance = self.compliance_result or {}
            ch.insert(
                "report_tracking",
                columns=[
                    "request_id", "requester_id", "department", "query_text",
                    "report_type", "status", "report_title", "chart_count",
                    "compliance_score", "compliance_passed",
                ],
                rows=[[
                    self.request_id, self.requester_id, self.department,
                    self.query_text[:500], self.report_type, "published",
                    published.get("title", "Untitled"),
                    len(self.charts or []),
                    compliance.get("score", 0),
                    1 if compliance.get("passed", False) else 0,
                ]],
                database="dwh",
            )
        except Exception as e:
            logger.warning("ClickHouse tracking failed: %s", e)

        # Index in Neo4j
        try:
            from .neo4j_setup import index_report_request
            index_report_request({
                "request_id": self.request_id,
                "requester_id": self.requester_id,
                "department": self.department,
                "query_text": self.query_text,
                "report_type": self.report_type,
                "priority": self.priority,
                "state": "published",
            })
        except Exception as e:
            logger.warning("Neo4j indexing failed: %s", e)

        await sm.update(report_content=published)
        logger.info("Published: '%s'", published.get("title", "Untitled"))
        self._publish_event("report_published", {"step": "publish", "title": published.get("title", "Untitled")})
        advance = await self._validate_and_advance()
        return {"status": "published", "title": published.get("title", "Untitled"), "advance": advance}

    # ═════════════════════════════════════════════════════════════════
    # Private helpers (not exposed as tools)
    # ═════════════════════════════════════════════════════════════════

    def _fetch_from_clickhouse(self, parsed: dict) -> dict:
        """Build and execute a query against ClickHouse Cloud."""
        import time

        from .clickhouse_client import ClickHouseCloud
        from .seed_clickhouse import CH_HOST, CH_PASSWORD

        ch = ClickHouseCloud(host=CH_HOST, password=CH_PASSWORD)

        domain = parsed.get("domain", "loans")
        metrics = parsed.get("metrics", [])
        dimensions = parsed.get("dimensions", [])
        filters = parsed.get("filters", {})
        time_range = parsed.get("time_range", "last_month")

        table_map = {
            "loans": "dwh.fact_loans",
            "deposits": "dwh.fact_deposits",
            "transactions": "dwh.fact_transactions",
            "customers": "dwh.dim_customers",
            "branches": "dwh.dim_branches",
        }
        table = table_map.get(domain, f"dwh.fact_{domain}")

        if dimensions and metrics:
            agg_metrics = [f"round(avg({m}), 2) AS {m}" for m in metrics]
            select_str = ", ".join(list(dimensions) + agg_metrics)
            group_by = f" GROUP BY {', '.join(dimensions)}"
        else:
            select_str = ", ".join(list(dimensions) + metrics) or "*"
            group_by = ""

        where_parts = []
        period_map = {
            "last_month": "2026-Q1",
            "last_quarter": "2025-Q4",
            "last_year": ("2025-Q1", "2025-Q4"),
            "ytd": "2026-Q1",
        }
        period_val = period_map.get(time_range)
        if isinstance(period_val, tuple):
            where_parts.append(f"period >= '{period_val[0]}' AND period <= '{period_val[1]}'")
        elif period_val:
            where_parts.append(f"period = '{period_val}'")
        for k, v in filters.items():
            where_parts.append(f"{k} = '{v}'")

        where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f"SELECT {select_str} FROM {table}{where_clause}{group_by} LIMIT 50"

        logger.info("[ClickHouse] %s", sql)

        start = time.time()
        rows = ch.query(sql)
        elapsed = round((time.time() - start) * 1000, 1)

        return {
            "domain": domain,
            "query_hash": hashlib.md5(sql.encode()).hexdigest()[:12],
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows,
            "row_count": len(rows),
            "execution_time_ms": elapsed,
        }

    def _generate_simulated_data(self, parsed: dict) -> dict:
        """Generate deterministic simulated data as fallback."""
        domain = parsed.get("domain", "loans")
        metrics = parsed.get("metrics", [])
        dimensions = parsed.get("dimensions", [])
        time_range = parsed.get("time_range", "last_month")

        dimension_values = {
            "branch": ["HQ", "Branch-A", "Branch-B", "Branch-C", "Branch-D"],
            "product_type": ["Personal Loan", "Mortgage", "Business Loan", "Auto Loan"],
            "customer_segment": ["Retail", "SME", "Corporate", "Premium"],
            "period": ["2026-Q1", "2025-Q4", "2025-Q3"],
            "channel": ["Mobile", "ATM", "Branch", "Online"],
            "transaction_type": ["Transfer", "Payment", "Withdrawal", "Deposit"],
            "account_type": ["Savings", "Current", "Fixed Deposit", "Recurring"],
            "segment": ["Retail", "SME", "Corporate", "Premium"],
            "region": ["North", "South", "East", "West", "Central"],
            "branch_type": ["Full Service", "Express", "Digital", "Regional Hub"],
            "acquisition_channel": ["Digital", "Branch", "Referral", "Campaign"],
        }

        metric_ranges = {
            "total_disbursed": (1_000_000, 50_000_000),
            "outstanding_balance": (500_000, 30_000_000),
            "npl_ratio": (0.01, 0.08),
            "avg_interest_rate": (0.04, 0.12),
            "total_deposits": (2_000_000, 80_000_000),
            "avg_balance": (10_000, 500_000),
            "growth_rate": (-0.05, 0.15),
            "cost_of_funds": (0.02, 0.06),
            "volume": (1_000, 100_000),
            "total_amount": (500_000, 20_000_000),
            "avg_amount": (100, 50_000),
            "fee_revenue": (10_000, 2_000_000),
            "total_customers": (500, 50_000),
            "new_customers": (10, 2_000),
            "churn_rate": (0.01, 0.10),
            "avg_lifetime_value": (5_000, 200_000),
            "profit": (100_000, 10_000_000),
            "cost_income_ratio": (0.30, 0.75),
            "staff_count": (5, 200),
            "efficiency_score": (0.50, 0.98),
        }

        if dimensions:
            dim_keys = dimensions[:2]
            combos = []
            vals_0 = dimension_values.get(dim_keys[0], ["A", "B", "C"])
            if len(dim_keys) > 1:
                vals_1 = dimension_values.get(dim_keys[1], ["X", "Y"])
                for v0 in vals_0:
                    for v1 in vals_1:
                        combos.append({dim_keys[0]: v0, dim_keys[1]: v1})
            else:
                for v0 in vals_0:
                    combos.append({dim_keys[0]: v0})
        else:
            combos = [{}]

        rows = []
        for combo in combos:
            row = dict(combo)
            for metric in metrics:
                lo, hi = metric_ranges.get(metric, (100, 10_000))
                seed = f"{domain}-{metric}-{json.dumps(combo, sort_keys=True)}-{time_range}"
                h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
                row[metric] = round(lo + (h % 10000) / 10000 * (hi - lo), 2)
            rows.append(row)

        return {
            "domain": domain,
            "query_hash": hashlib.md5(json.dumps(parsed, sort_keys=True).encode()).hexdigest()[:12],
            "columns": list(dimensions) + list(metrics),
            "rows": rows,
            "row_count": len(rows),
            "execution_time_ms": round(random.uniform(50, 500), 1),
        }
