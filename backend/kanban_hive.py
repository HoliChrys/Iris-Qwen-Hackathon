"""
IRIS Kanban Hive — manages the report tracking board.

Two Hives:
1. kanban_hive (default mode): Stream handler for board CRUD actions
   - add_card, move_card, archive_card, get_board, approve_card, revise_card
2. Pipeline hooks: When IRIS WOT completes a step, the card auto-advances

The Kanban board persists ReportCard entities via EntityCluster (Faust Table).
SSE events are published on each card transition for real-time frontend sync.

Routes:
    POST /api/iris/kanban   — Board actions (add, move, archive, approve, etc.)
    GET  /api/iris/kanban   — Get full board state
"""
from __future__ import annotations

import json
import logging
from typing import Any

from tachikoma.hive import Hive

from .kanban import (
    KANBAN_COLUMNS,
    STEP_TO_COLUMN,
    ReportCard,
    board_state,
    card_from_request,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# In-memory card store + ClickHouse Cloud persistence
# ═══════════════════════════════════════════════════════════════

_cards: dict[str, ReportCard] = {}


def _get_ch():
    """Lazy ClickHouse Cloud client."""
    from .clickhouse_client import ClickHouseCloud
    from .seed_clickhouse import CH_HOST, CH_PASSWORD
    return ClickHouseCloud(host=CH_HOST, password=CH_PASSWORD)


def _ts(val) -> str:
    """Convert any timestamp to ClickHouse DateTime format."""
    if isinstance(val, (int, float)):
        from datetime import datetime
        return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val, str) and val:
        return val[:19].replace("T", " ")
    return "1970-01-01 00:00:00"


def _persist_card(card: ReportCard) -> None:
    """Upsert card state to dwh.kanban_cards (ReplacingMergeTree deduplicates)."""
    try:
        ch = _get_ch()
        ch.insert("kanban_cards", columns=[
            "card_id", "title", "department", "requester_id", "report_type",
            "priority", "query_text", "column_id", "current_step",
            "chart_count", "compliance_score", "compliance_passed",
            "html_size", "review_approved", "review_notes",
            "created_at", "updated_at",
        ], rows=[[
            card.card_id, card.title, card.department, card.requester_id,
            card.report_type, card.priority, card.query_text,
            card.state, card.current_step,
            card.chart_count, card.compliance_score,
            1 if card.compliance_passed else 0,
            card.html_size, 1 if card.review_approved else 0,
            card.review_notes,
            _ts(card.created_at), _ts(card.updated_at),
        ]], database="dwh")
    except Exception as e:
        import traceback
        logger.warning("Kanban card persist failed: %s\n%s", e, traceback.format_exc())


def _persist_event(card_id: str, event_type: str, from_col: str = "", to_col: str = "", detail: str = "") -> None:
    """Append event to dwh.kanban_events."""
    try:
        ch = _get_ch()
        import uuid
        ch.insert("kanban_events", columns=[
            "event_id", "card_id", "event_type", "from_column", "to_column", "detail",
        ], rows=[[
            str(uuid.uuid4()), card_id, event_type, from_col, to_col, detail,
        ]], database="dwh")
    except Exception as e:
        logger.warning("Kanban event persist failed: %s", e)


def get_card(card_id: str) -> ReportCard | None:
    return _cards.get(card_id)


def get_all_cards() -> list[ReportCard]:
    return list(_cards.values())


def get_board() -> dict[str, Any]:
    return board_state(get_all_cards())


# ═══════════════════════════════════════════════════════════════
# Action handlers
# ═══════════════════════════════════════════════════════════════


async def handle_add_card(
    request_id: str,
    query_text: str,
    department: str = "",
    requester_id: str = "",
    report_type: str = "",
    priority: str = "normal",
) -> dict[str, Any]:
    """Add a new card to the board in 'to_do' column."""
    if request_id in _cards:
        return {"error": f"Card {request_id} already exists", "card": _cards[request_id].to_frontend_card()}

    card = card_from_request(
        request_id=request_id,
        query_text=query_text,
        department=department,
        requester_id=requester_id,
        report_type=report_type,
        priority=priority,
    )
    _cards[request_id] = card
    _persist_card(card)
    _persist_event(request_id, "card_added", to_col="to_do", detail=query_text[:100])

    logger.info("Kanban: card added %s → to_do", request_id)
    return {"action": "card_added", "card": card.to_frontend_card()}


async def handle_move_card(card_id: str, to_column: str) -> dict[str, Any]:
    """Move a card to a specific column (manual drag-and-drop)."""
    card = get_card(card_id)
    if not card:
        return {"error": f"Card {card_id} not found"}

    from_column = card.state
    sm = card.state_machine()
    try:
        await sm.to(to_column)
    except Exception as e:
        return {"error": f"Cannot move {card_id} from {from_column} to {to_column}: {e}"}

    card.updated_at = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    _persist_card(card)
    _persist_event(card_id, "card_moved", from_col=from_column, to_col=to_column)

    logger.info("Kanban: card %s moved %s → %s", card_id, from_column, to_column)
    return {
        "action": "card_moved",
        "card_id": card_id,
        "from_column": from_column,
        "to_column": to_column,
        "card": card.to_frontend_card(),
    }


async def handle_archive_card(card_id: str) -> dict[str, Any]:
    """Archive a card (move to archived column)."""
    card = get_card(card_id)
    if not card:
        return {"error": f"Card {card_id} not found"}

    from_col = card.state
    await card.archive_card()
    _persist_card(card)
    _persist_event(card_id, "card_archived", from_col=from_col, to_col="archived")

    logger.info("Kanban: card %s archived", card_id)
    return {"action": "card_archived", "card_id": card_id}


async def handle_approve_card(card_id: str) -> dict[str, Any]:
    """Approve a card in the review column."""
    card = get_card(card_id)
    if not card:
        return {"error": f"Card {card_id} not found"}
    if card.state != "review":
        return {"error": f"Card {card_id} is in '{card.state}', not 'review'"}

    await card.approve_card()
    result = await card.advance_to("publish")
    _persist_card(card)
    _persist_event(card_id, "card_approved", from_col="review", to_col="published")

    logger.info("Kanban: card %s approved → published", card_id)
    return {
        "action": "card_approved",
        "card_id": card_id,
        "card": card.to_frontend_card(),
    }


async def handle_revise_card(card_id: str, notes: str) -> dict[str, Any]:
    """Send a card back for revision."""
    card = get_card(card_id)
    if not card:
        return {"error": f"Card {card_id} not found"}
    if card.state != "review":
        return {"error": f"Card {card_id} is in '{card.state}', not 'review'"}

    await card.request_revision(notes)
    sm = card.state_machine()
    await sm.to("generating")
    _persist_card(card)
    _persist_event(card_id, "card_revised", from_col="review", to_col="generating", detail=notes[:200])

    logger.info("Kanban: card %s revision requested → generating", card_id)
    return {
        "action": "card_revised",
        "card_id": card_id,
        "notes": notes,
        "card": card.to_frontend_card(),
    }


async def handle_update_card(
    card_id: str,
    title: str = "",
    chart_count: int = 0,
    compliance_score: float = 0.0,
    compliance_passed: bool = False,
    html_size: int = 0,
) -> dict[str, Any]:
    """Update a card with pipeline progress data."""
    card = get_card(card_id)
    if not card:
        return {"error": f"Card {card_id} not found"}

    await card.update_progress(
        title=title,
        chart_count=chart_count,
        compliance_score=compliance_score,
        compliance_passed=compliance_passed,
        html_size=html_size,
    )

    _persist_card(card)

    return {"action": "card_updated", "card_id": card_id, "card": card.to_frontend_card()}


# ═══════════════════════════════════════════════════════════════
# Pipeline hook — auto-advance card when WOT step completes
# ═══════════════════════════════════════════════════════════════


async def on_pipeline_step(
    request_id: str,
    step_name: str,
    detail: str = "",
    **step_data: Any,
) -> dict[str, Any] | None:
    """Called by the WOT pipeline when a step completes.

    Creates the card if it doesn't exist yet (first step),
    then advances it to the matching column.
    """
    card = get_card(request_id)

    # Auto-create card on first step
    if card is None and step_name in ("interpret_query", "fetch_data"):
        await handle_add_card(
            request_id=request_id,
            query_text=step_data.get("query_text", ""),
            department=step_data.get("department", ""),
            requester_id=step_data.get("requester_id", ""),
            report_type=step_data.get("report_type", ""),
            priority=step_data.get("priority", "normal"),
        )
        card = get_card(request_id)

    if card is None:
        return None

    # Advance card to matching column
    from_col = card.state
    result = await card.advance_to(step_name)

    # Update card with step data
    if step_data.get("title"):
        card.title = step_data["title"]
    if step_data.get("chart_count"):
        card.chart_count = step_data["chart_count"]
    if step_data.get("compliance_score"):
        card.compliance_score = step_data["compliance_score"]
        card.compliance_passed = step_data.get("compliance_passed", False)
    if step_data.get("html_size"):
        card.html_size = step_data["html_size"]

    _persist_card(card)
    _persist_event(request_id, "pipeline_step", from_col=from_col, to_col=card.state, detail=step_name)

    logger.info("Pipeline hook: %s step=%s → column=%s", request_id, step_name, card.state)
    return result


# ═══════════════════════════════════════════════════════════════
# Kanban Hive — stream handler for board actions
# ═══════════════════════════════════════════════════════════════


def build_kanban_hive(app, tracer=None) -> Hive:
    """Create a Hive for Kanban board operations.

    Handles board CRUD via stream events (or .ask() in serverless mode):
        {"action": "get_board"}
        {"action": "add_card", "request_id": "...", "query_text": "..."}
        {"action": "move_card", "card_id": "...", "to_column": "..."}
        {"action": "archive_card", "card_id": "..."}
        {"action": "approve_card", "card_id": "..."}
        {"action": "revise_card", "card_id": "...", "notes": "..."}
        {"action": "update_card", "card_id": "...", "title": "...", ...}
    """

    kanban = Hive(app, name="iris-kanban", tracer=tracer)

    async def kanban_handler(stream):
        async for event in stream:
            action = event.get("action", "")

            if action == "get_board":
                yield get_board()

            elif action == "add_card":
                result = await handle_add_card(
                    request_id=event.get("request_id", ""),
                    query_text=event.get("query_text", ""),
                    department=event.get("department", ""),
                    requester_id=event.get("requester_id", ""),
                    report_type=event.get("report_type", ""),
                    priority=event.get("priority", "normal"),
                )
                yield {**result, "board": get_board()}

            elif action == "move_card":
                result = await handle_move_card(
                    card_id=event.get("card_id", ""),
                    to_column=event.get("to_column", ""),
                )
                yield {**result, "board": get_board()}

            elif action == "archive_card":
                result = await handle_archive_card(card_id=event.get("card_id", ""))
                yield {**result, "board": get_board()}

            elif action == "approve_card":
                result = await handle_approve_card(card_id=event.get("card_id", ""))
                yield {**result, "board": get_board()}

            elif action == "revise_card":
                result = await handle_revise_card(
                    card_id=event.get("card_id", ""),
                    notes=event.get("notes", ""),
                )
                yield {**result, "board": get_board()}

            elif action == "update_card":
                result = await handle_update_card(
                    card_id=event.get("card_id", ""),
                    title=event.get("title", ""),
                    chart_count=event.get("chart_count", 0),
                    compliance_score=event.get("compliance_score", 0.0),
                    compliance_passed=event.get("compliance_passed", False),
                    html_size=event.get("html_size", 0),
                )
                yield {**result, "board": get_board()}

            elif action == "pipeline_step":
                result = await on_pipeline_step(
                    request_id=event.get("request_id", ""),
                    step_name=event.get("step_name", ""),
                    **{k: v for k, v in event.items() if k not in ("action", "request_id", "step_name")},
                )
                yield {"action": "pipeline_sync", "result": result, "board": get_board()}

            else:
                yield {"error": f"Unknown action: {action}"}

    kanban.from_input().to_loop(kanban_handler)

    logger.info("Kanban Hive created: iris-kanban")
    return kanban
