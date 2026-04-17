"""
IRIS Kanban — report cards as StatefulRecords on a board.

Each ReportCard is a StatefulRecord whose states = Kanban columns:
    to_do → interpreting → fetching → generating → rendering
    → compliance → review → published → archived

The ReportKanban board tracks all active cards and provides
actions for moving, filtering, and archiving.

When the IRIS pipeline advances a report, the corresponding
ReportCard transitions to the matching column state.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar

from tachikoma.stateful.record import (
    Condition,
    StatefulRecord,
    TransitionDef,
    action,
    condition,
    on_enter,
    sr_init,
)
from tachikoma.stateful.decorators.tool import tool

logger = logging.getLogger(__name__)


# ── Kanban column definitions ───────────────────────────────────

KANBAN_COLUMNS = [
    {"id": "to_do", "title": "To Do", "order": 0, "color": "#6b7280"},
    {"id": "interpreting", "title": "Interpreting", "order": 1, "color": "#8b5cf6"},
    {"id": "fetching", "title": "Fetching Data", "order": 2, "color": "#3b82f6"},
    {"id": "generating", "title": "Generating", "order": 3, "color": "#f59e0b"},
    {"id": "rendering", "title": "Rendering Charts", "order": 4, "color": "#ec4899"},
    {"id": "compliance", "title": "Compliance", "order": 5, "color": "#10b981"},
    {"id": "review", "title": "Human Review", "order": 6, "color": "#ef4444"},
    {"id": "published", "title": "Published", "order": 7, "color": "#22c55e"},
    {"id": "archived", "title": "Archived", "order": 8, "color": "#9ca3af"},
]

KANBAN_STATES = [c["id"] for c in KANBAN_COLUMNS]

# Map pipeline step names to kanban column IDs
STEP_TO_COLUMN = {
    "interpret_query": "interpreting",
    "fetch_data": "fetching",
    "generate_report": "generating",
    "render_charts": "rendering",
    "check_compliance": "compliance",
    "human_review": "review",
    "publish": "published",
}


# ═══════════════════════════════════════════════════════════════
# ReportCard — StatefulRecord per report, states = Kanban columns
# ═══════════════════════════════════════════════════════════════


@sr_init(
    entity="report_card",
    initial="to_do",
    states=KANBAN_STATES,
)
class ReportCard(StatefulRecord):
    """A report card on the Kanban board.

    Each card tracks a single report request through the pipeline.
    The state IS the current column.
    """

    _transitions: ClassVar[list[TransitionDef]] = [
        # Forward flow (pipeline-driven)
        TransitionDef("to_do", "interpreting"),
        TransitionDef("interpreting", "fetching"),
        TransitionDef("fetching", "generating"),
        TransitionDef("generating", "rendering"),
        TransitionDef("rendering", "compliance"),
        TransitionDef("compliance", "review"),
        TransitionDef("review", "published", condition="is_approved"),
        TransitionDef("published", "archived"),
        # Revision loop
        TransitionDef("review", "generating", condition="needs_revision"),
        # Manual override: any → to_do (reset)
        TransitionDef(
            ["interpreting", "fetching", "generating", "rendering", "compliance", "review"],
            "to_do",
        ),
        # Archive from any terminal state
        TransitionDef(["published", "review"], "archived"),
    ]

    # ── Card fields ─────────────────────────────────────────────

    card_id: str = ""           # Same as request_id
    title: str = ""             # Report title (updated as pipeline progresses)
    department: str = ""
    requester_id: str = ""
    report_type: str = ""
    priority: str = "normal"    # low, normal, high, urgent
    query_text: str = ""

    # Pipeline progress
    current_step: str = ""      # Last completed pipeline step
    chart_count: int = 0
    compliance_score: float = 0.0
    compliance_passed: bool = False
    html_size: int = 0

    # Review
    review_approved: bool = False
    review_notes: str = ""

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    # ── Conditions ──────────────────────────────────────────────

    @condition("is_approved")
    def is_approved(self) -> Condition:
        return Condition.that(self.review_approved, "Not approved by reviewer")

    @condition("needs_revision")
    def needs_revision(self) -> Condition:
        return Condition.all_of(
            Condition.that(not self.review_approved, "Already approved"),
            Condition.that(bool(self.review_notes), "No revision notes"),
        )

    # ── Lifecycle hooks ─────────────────────────────────────────

    @on_enter("to_do")
    def on_to_do(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    @on_enter("published")
    def on_published(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        logger.info("Card '%s' published", self.title)

    @on_enter("archived")
    def on_archived(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        logger.info("Card '%s' archived", self.title)

    # ── Tools (called by agents or pipeline hooks) ──────────────

    @tool("Move this card to the next pipeline step")
    async def advance_to(self, step_name: str) -> dict:
        """Move the card to the column matching a pipeline step.

        Args:
            step_name: Pipeline step name (interpret_query, fetch_data, etc.)
        """
        column = STEP_TO_COLUMN.get(step_name)
        if not column:
            return {"error": f"Unknown step: {step_name}"}

        self.current_step = step_name
        self.updated_at = datetime.now().isoformat(timespec="seconds")

        sm = self.state_machine()
        try:
            await sm.to(column)
            logger.info("Card '%s' → %s", self.card_id, column)
            return {"card_id": self.card_id, "column": column, "step": step_name}
        except Exception as e:
            logger.warning("Card '%s' transition to %s failed: %s", self.card_id, column, e)
            return {"error": str(e)}

    @tool("Update card with pipeline results")
    async def update_progress(
        self,
        title: str = "",
        chart_count: int = 0,
        compliance_score: float = 0.0,
        compliance_passed: bool = False,
        html_size: int = 0,
    ) -> dict:
        """Update the card with results from the pipeline.

        Args:
            title: Report title (from generate step)
            chart_count: Number of charts rendered
            compliance_score: Compliance score 0.0-1.0
            compliance_passed: Whether compliance passed
            html_size: Size of rendered HTML in bytes
        """
        if title:
            self.title = title
        if chart_count:
            self.chart_count = chart_count
        if compliance_score:
            self.compliance_score = compliance_score
        self.compliance_passed = compliance_passed
        if html_size:
            self.html_size = html_size
        self.updated_at = datetime.now().isoformat(timespec="seconds")

        return {"card_id": self.card_id, "updated": True}

    @tool("Approve this report for publication")
    async def approve_card(self) -> dict:
        """Mark the card as approved by the reviewer."""
        self.review_approved = True
        self.review_notes = ""
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        return {"card_id": self.card_id, "approved": True}

    @tool("Request revision of this report")
    async def request_revision(self, notes: str) -> dict:
        """Send the card back for revision.

        Args:
            notes: Revision instructions
        """
        self.review_approved = False
        self.review_notes = notes
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        return {"card_id": self.card_id, "revision_requested": True}

    @tool("Archive this card")
    async def archive_card(self) -> dict:
        """Archive the card (remove from active board)."""
        sm = self.state_machine()
        await sm.to("archived")
        return {"card_id": self.card_id, "archived": True}

    # ── Serialization ───────────────────────────────────────────

    def to_frontend_card(self) -> dict[str, Any]:
        """Serialize for the frontend Kanban UI."""
        return {
            "card_id": self.card_id,
            "title": self.title or self.query_text[:60],
            "department": self.department,
            "requester_id": self.requester_id,
            "report_type": self.report_type,
            "priority": self.priority,
            "column_id": self.state,
            "current_step": self.current_step,
            "chart_count": self.chart_count,
            "compliance_score": self.compliance_score,
            "compliance_passed": self.compliance_passed,
            "html_size": self.html_size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ═══════════════════════════════════════════════════════════════
# Helper: create a card from a report request
# ═══════════════════════════════════════════════════════════════


def card_from_request(
    request_id: str,
    query_text: str,
    department: str = "",
    requester_id: str = "",
    report_type: str = "",
    priority: str = "normal",
) -> ReportCard:
    """Create a new ReportCard from a report request."""
    return ReportCard(
        card_id=request_id,
        title=query_text[:80],
        department=department,
        requester_id=requester_id,
        report_type=report_type,
        priority=priority,
        query_text=query_text,
        created_at=datetime.now().isoformat(timespec="seconds"),
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )


# ═══════════════════════════════════════════════════════════════
# Board state helper (all columns + cards)
# ═══════════════════════════════════════════════════════════════


def board_state(cards: list[ReportCard]) -> dict[str, Any]:
    """Build the full Kanban board state for the frontend."""
    cards_by_column: dict[str, list[dict]] = {c["id"]: [] for c in KANBAN_COLUMNS}

    for card in cards:
        col = card.state if card.state in cards_by_column else "to_do"
        cards_by_column[col].append(card.to_frontend_card())

    return {
        "columns": [
            {
                **col,
                "cards": sorted(
                    cards_by_column[col["id"]],
                    key=lambda c: c.get("created_at", ""),
                ),
            }
            for col in KANBAN_COLUMNS
        ],
        "total_cards": len(cards),
        "counts": {col["id"]: len(cards_by_column[col["id"]]) for col in KANBAN_COLUMNS},
    }
