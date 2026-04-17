"""
IRIS — Single global Hive that mirrors the entire app structure.

Topology-as-user-journey. Every user path is a switch case.

    switch(polymorphic)
    ├── init / reset                                      (session)
    ├── chat → SemanticRouter → search | report_wot.ask() (chat + intent)
    │                                    └── 7 AgentEntity steps (each with a SKILL.md)
    │                                          interpret → fetch → generate →
    │                                          render_charts → compliance →
    │                                          human_review(cast) → publish →
    │                                          semantic_filing stage
    ├── review                                            (HITL cast resume)
    ├── search                                            (unified search endpoint)
    ├── kanban                                            (CRUD + pipeline_step auto-advance)
    ├── treefile                                          (published report tree, filed via fastembed)
    ├── datasource                                        (dynamic TracedTopic CRUD)
    ├── dashboard                                         (KPIs + chart data)
    ├── history                                           (report_tracking list)
    └── otherwise                                         (catch-all error envelope)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from tachikoma import Tachikoma
from tachikoma.agent import AgentEntity
from tachikoma.hive import Hive
from tachikoma.topic import TracedTopic
from tachikoma.monorepo.eventbus import InProcessEventBus
from tachikoma.stateful.journal import EventJournal
from tachikoma.monorepo import Monorepo

from .config import KAFKA_BROKER, HITL_REVIEW_TIMEOUT_SECONDS
from .records import ReportRequest, STEP_RECORDS
from .views import IrisActionView, IrisEventsView

logger = logging.getLogger(__name__)

# ── App ──────────────────────────────────────────────────────

app = Tachikoma(
    "iris",
    broker=KAFKA_BROKER,
    web_host="10.200.10.15",
    web_port=8001,
    ray_enabled=True,
)

event_bus = InProcessEventBus()
EventJournal.set_event_bus(
    event_bus,
    channel_fn=lambda entity: f"iris.{getattr(entity, 'session_id', '')}"
    if getattr(entity, 'session_id', '') else None,
)

# ── Topics ───────────────────────────────────────────────────

input_topic = TracedTopic(app, "sb5.report.requests")
output_topic = TracedTopic(app, "sb5.report.events")

# ── Global Hive ──────────────────────────────────────────────

iris = Hive(app, name="iris")

# ── Conditions ───────────────────────────────────────────────

def is_init(event):
    return event.get("event_type") == "iris.init"

def is_reset(event):
    return event.get("event_type") == "iris.reset"

def is_chat(event):
    return event.get("event_type") == "iris.chat"

def is_kanban(event):
    et = event.get("event_type", "")
    return et.startswith("iris.kanban")

def is_datasource(event):
    et = event.get("event_type", "")
    return et.startswith("iris.datasource")

def is_review(event):
    return event.get("event_type") == "iris.review"

def is_search(event):
    return event.get("event_type") == "iris.search"

def is_treefile(event):
    return event.get("event_type", "").startswith("iris.treefile")

def is_dashboard(event):
    return event.get("event_type", "").startswith("iris.dashboard")

def is_history(event):
    return event.get("event_type", "").startswith("iris.history")

# ═══════════════════════════════════════════════════════════
# Handlers — canonical single-event signature for to_loop + ask()
#
# Each handler takes ONE event (dict) and returns ONE dict.
# This is the same convention used by the booking pipeline in
# landingpage/wot_pipeline.py and matches Hive._ask_impl which
# calls `dest(value)` and expects a single awaitable result.
# ═══════════════════════════════════════════════════════════

# ── Init ─────────────────────────────────────────────────────

async def handle_init(event: dict) -> dict:
    sid = event.get("session_id", "default") if isinstance(event, dict) else "default"
    return {
        "state": {"current_state": "ready"},
        "agent_message": "Hello! I'm IRIS. Describe the report you need, or search existing ones.",
        "token": sid,
        "channel": f"iris.{sid}",
    }


# ── Reset ────────────────────────────────────────────────────

async def handle_reset(event: dict) -> dict:
    sid = event.get("session_id", "default") if isinstance(event, dict) else "default"
    return {
        "state": {"current_state": "ready"},
        "agent_message": "Session reset. How can I help?",
        "token": sid,
        "channel": f"iris.{sid}",
    }


# ── Search (dedicated /search action) ───────────────────────

async def handle_search(event: dict) -> dict:
    from .search import search_reports
    query = event.get("query") or event.get("message", "")
    max_r = event.get("max_results", 10)
    sources = event.get("sources")
    try:
        return await search_reports(query, max_results=max_r, sources=sources)
    except Exception as e:
        logger.exception("search failed")
        return {"query": query, "results": [], "total": 0, "error": str(e),
                "sources_queried": []}


# ── Kanban (CRUD dispatcher on dotted event_type) ───────────

async def handle_kanban(event: dict) -> dict:
    from .kanban_hive import (
        handle_add_card, handle_move_card, handle_approve_card,
        handle_archive_card, handle_revise_card, get_board,
        on_pipeline_step,
    )

    # Support both dotted event_type (iris.kanban.move_card)
    # and legacy kanban_action field.
    et = event.get("event_type", "")
    sub = et.split(".")[-1] if "." in et else event.get("kanban_action", "")

    try:
        if sub == "get_board":
            return get_board()
        elif sub == "add_card":
            clean = {k: v for k, v in event.items()
                     if k not in ("event_type", "kanban_action")}
            result = await handle_add_card(**clean)
            return {**result, "board": get_board()}
        elif sub == "move_card":
            result = await handle_move_card(event.get("card_id", ""),
                                            event.get("to_column", ""))
            return {**result, "board": get_board()}
        elif sub == "approve_card":
            result = await handle_approve_card(event.get("card_id", ""))
            return {**result, "board": get_board()}
        elif sub == "archive_card":
            result = await handle_archive_card(event.get("card_id", ""))
            return {**result, "board": get_board()}
        elif sub == "revise_card":
            result = await handle_revise_card(event.get("card_id", ""),
                                              event.get("notes", ""))
            return {**result, "board": get_board()}
        elif sub == "pipeline_step":
            result = on_pipeline_step(
                request_id=event.get("request_id", ""),
                step_name=event.get("step_name", ""),
                **{k: v for k, v in event.items()
                   if k not in ("event_type", "request_id", "step_name")},
            )
            if hasattr(result, "__await__"):
                result = await result
            return {**(result or {}), "board": get_board()}
        else:
            return {"error": f"Unknown kanban action: {sub}"}
    except Exception as e:
        logger.exception("kanban handler failed")
        return {"error": str(e), "kanban_action": sub}


# ── DataSource (dynamic TracedTopic CRUD) ───────────────────

_dynamic_topics: dict[str, TracedTopic] = {}
_ds_bindings: dict[str, list[str]] = {}

async def handle_datasource(event: dict) -> dict:
    et = event.get("event_type", "")
    sub = et.split(".")[-1] if "." in et else event.get("ds_action", "")

    try:
        if sub == "list":
            return {"sources": [
                {"id": f"ds-{n}", "name": n, "type": "kafka_topic",
                 "endpoint": n, "status": "active",
                 "events_count": 0,
                 "bound_agents": _ds_bindings.get(n, [])}
                for n in _dynamic_topics
            ]}
        elif sub == "create":
            name = event.get("topic_name", "")
            if not name:
                return {"error": "Empty topic_name"}
            if name in _dynamic_topics:
                return {"error": f"Topic '{name}' already exists"}
            _dynamic_topics[name] = TracedTopic(app, name)
            return {"status": "created", "topic": name}
        elif sub == "send":
            name = event.get("topic_name", "")
            topic = _dynamic_topics.get(name)
            if not topic:
                return {"error": f"Topic '{name}' not found"}
            try:
                await topic.send(value=event.get("payload", {}))
            except Exception as send_err:
                # Topic may not be started (no Faust runtime in ask() mode)
                logger.warning("topic.send skipped: %s", send_err)
            return {"status": "sent", "topic": name}
        elif sub == "bind":
            name = event.get("topic_name", "")
            handler = event.get("handler", "")
            if name not in _dynamic_topics:
                return {"error": f"Topic '{name}' not found"}
            _ds_bindings.setdefault(name, []).append(handler)
            return {"status": "bound", "topic": name, "handler": handler}
        else:
            return {"error": f"Unknown datasource action: {sub}"}
    except Exception as e:
        logger.exception("datasource handler failed")
        return {"error": str(e), "ds_action": sub}


# ── Review (resume cast(review_point) Future) ──────────────

_pending_reviews: dict[str, "asyncio.Future"] = {}

async def handle_review(event: dict) -> dict:
    """Directly invoke the HITL tool on the entity (approve/revise/reject).

    This drives the state machine transition *immediately* so the next
    `iris.chat` / run-to-pause cycle picks up from the new state
    (publish for approve, generate_report for revise, error for reject).
    """
    sid = event.get("session_id", "default")
    req_id = event.get("request_id") or sid
    route = event.get("route", "approve")
    notes = event.get("revision_notes") or event.get("comments", "")

    # Find the entity for this session
    ent = report_wot.get_schema_instance(sid, "entity_in_build")
    if ent is None or ent.state != "human_review":
        # Entity may not exist yet (no active pipeline) or is in a different
        # state (pipeline still running / already completed). Log-only — the
        # frontend can retry when the pipeline pauses at human_review.
        current = ent.state if ent else "<none>"
        logger.info("No pending review for %s (state=%s); logged", sid, current)
        return {"status": f"review_{route}_logged", "session_id": sid,
                "request_id": req_id, "warning": "no_pending_review",
                "current_state": current}

    try:
        if route == "approve":
            r = await ent.approve()
        elif route == "revise":
            r = await ent.request_revision(notes=notes or "Please revise")
        elif route == "reject":
            r = await ent.reject(reason=notes or "Rejected")
        else:
            return {"error": f"Unknown route: {route}"}
    except Exception as e:
        logger.exception("review route=%s failed", route)
        return {"error": str(e), "route": route}

    return {
        "status": f"review_{route}_applied",
        "session_id": sid,
        "request_id": req_id,
        "new_state": ent.state,
        "tool_result": r,
    }


# ── TreeFile ────────────────────────────────────────────────

async def handle_treefile(event: dict) -> dict:
    try:
        from .treefile import build_tree, get_node_detail
    except ImportError:
        build_tree = None
        get_node_detail = None

    sub = event.get("event_type", "").split(".")[-1]
    try:
        if sub == "get_tree":
            return {"tree": await build_tree()} if build_tree else {"tree": []}
        elif sub == "select_node":
            if get_node_detail:
                return {"node": await get_node_detail(event.get("node_id", ""))}
            return {"error": "treefile module not available"}
        elif sub == "auto_file":
            return {"status": "indexed", "folder": event.get("folder_id")}
        else:
            return {"error": f"Unknown treefile action: {sub}"}
    except Exception as e:
        logger.exception("treefile handler failed")
        return {"error": str(e), "treefile_action": sub}


# ── Dashboard ───────────────────────────────────────────────

async def handle_dashboard(event: dict) -> dict:
    try:
        from .dashboard import get_kpis, get_chart_data
    except ImportError:
        get_kpis = None
        get_chart_data = None

    sub = event.get("event_type", "").split(".")[-1]
    try:
        if sub == "kpis":
            return {"kpis": await get_kpis()} if get_kpis else {"kpis": {}}
        elif sub == "chart":
            if get_chart_data:
                return await get_chart_data(event.get("chart_id", ""))
            return {"error": "dashboard module not available"}
        else:
            return {"error": f"Unknown dashboard action: {sub}"}
    except Exception as e:
        logger.exception("dashboard handler failed")
        return {"error": str(e), "dashboard_action": sub}


# ── History ─────────────────────────────────────────────────

async def handle_history(event: dict) -> dict:
    try:
        from .history import list_reports
    except ImportError:
        list_reports = None
    try:
        if list_reports:
            return await list_reports(
                limit=event.get("limit", 100),
                department=event.get("department"),
                report_type=event.get("report_type"),
                status=event.get("status", "published"),
            )
        return {"reports": [], "total": 0}
    except Exception as e:
        logger.exception("history handler failed")
        return {"reports": [], "total": 0, "error": str(e)}


# ── Unknown (catch-all) ─────────────────────────────────────

async def handle_unknown(event: dict) -> dict:
    return {"error": f"Unknown action: {event.get('event_type', '?') if isinstance(event, dict) else '?'}"}


# ── Chat (intent routing: search vs report WOT) ─────────────

_SEARCH_KEYWORDS = ["find", "search", "look up", "cherche", "trouv",
                    "existing", "show me reports", "list reports", "what reports"]

# WOT terminal/pause states — loop stops here
_WOT_PAUSE_STATES = {"human_review", "completed", "error"}


async def _run_wot_to_pause(hive: "Hive", event: dict,
                            max_steps: int = 20,
                            step_timeout: float = 90.0,
                            stuck_retries: int = 2) -> dict:
    """Run a WOT hive step-by-step until it reaches a pause/terminal state.

    Each `ask()` call drives ONE state transition (via the WOT-auto-built
    switch). We re-enter until:
      - entity reaches {human_review, completed, error}  → PAUSE, return
      - max_steps exceeded                               → safety stop
      - same state `stuck_retries` consecutive calls AND the last call
        did not return an error envelope                 → stuck, abort

    The stuck_retries parameter (default 2) allows a second attempt on
    the same state when the previous call returned an `error` envelope
    (e.g. Ray OOM, transient LLM hiccup). This distinguishes "agent
    actually stuck" from "agent hit a recoverable glitch".
    """
    sid = event.get("session_id", "default")
    last_state = ""
    same_state_count = 0
    last_result_had_error = False
    results: list[dict] = []

    for step_num in range(max_steps):
        # Current entity state
        instances = hive._session_schema_instances.get(sid, {})
        current = None
        for tag, inst in instances.items():
            if hasattr(inst, "state"):
                current = inst.state
                break

        # Terminal / pause? stop.
        if current in _WOT_PAUSE_STATES:
            logger.info("WOT reached pause state '%s' after %d steps", current, step_num)
            break

        # Same state as before?
        if current and current == last_state:
            same_state_count += 1
            if same_state_count >= stuck_retries and not last_result_had_error:
                logger.warning(
                    "WOT stuck at '%s' after %d same-state iters — aborting",
                    current, same_state_count,
                )
                break
            if last_result_had_error:
                logger.info("WOT same state '%s' but previous had error — retry", current)
        else:
            same_state_count = 0
        last_state = current or ""

        # Dispatch one step
        try:
            r = await asyncio.wait_for(hive.ask(event, timeout=step_timeout),
                                       timeout=step_timeout + 5)
        except asyncio.TimeoutError:
            logger.error("WOT step %d at state '%s' timed out", step_num, current)
            break
        except Exception as e:
            logger.exception("WOT step %d raised", step_num)
            return {"error": f"wot_step_raised: {e}", "last_state": current,
                    "steps_run": len(results)}

        if isinstance(r, dict):
            results.append(r)
            last_result_had_error = bool(r.get("error"))
        else:
            last_result_had_error = False

    # Build final result — merge last step's dict + current entity snapshot
    final = results[-1] if results else {}
    insts = hive._session_schema_instances.get(sid, {})
    for tag, inst in insts.items():
        if hasattr(inst, "state"):
            final["final_state"] = inst.state
            if getattr(inst, "report_content", None):
                final["report_content"] = inst.report_content
            if getattr(inst, "report_html", None):
                final["report_html"] = inst.report_html
            if getattr(inst, "compliance_result", None):
                final["compliance_result"] = inst.compliance_result
            if hasattr(inst, "revision_count"):
                final["revision_count"] = inst.revision_count
            break
    final["steps_run"] = len(results)
    return final


async def handle_chat(event: dict) -> dict:
    """Route chat messages by intent: keyword match → search; else → report_wot."""
    import asyncio  # local import to match helper
    from .search import search_reports

    msg = event.get("message", "")
    is_search_intent = any(kw in msg.lower() for kw in _SEARCH_KEYWORDS)

    if is_search_intent:
        try:
            result = await search_reports(msg, max_results=10)
        except Exception as e:
            logger.exception("chat→search failed")
            return {"agent_message": f"Search failed: {e}", "search_results": []}
        results = result.get("results", [])
        if results:
            lines = [f"Found {len(results)} report(s):"]
            for r in results[:5]:
                title = r.get("report_title") or r.get("query_text", "?")[:60]
                lines.append(f"- **{title}** ({r.get('department', '')}) [{r.get('source', '')}]")
            return {"agent_message": "\n".join(lines), "search_results": results}
        return {"agent_message": "No reports found.", "search_results": []}

    # Report intent → run the WOT until it pauses (typically at human_review)
    event["_wot_hive"] = report_wot
    try:
        return await _run_wot_to_pause(report_wot, event)
    except Exception as e:
        logger.exception("chat→report_wot failed")
        return {"agent_message": f"Pipeline failed: {e}"}

# ── Report WOT sub-hive (AgentEntity instances + skills) ───

from .config import DATA_DOMAINS

def _domain_desc():
    lines = []
    for name, info in DATA_DOMAINS.items():
        metrics = ", ".join(info["metrics"])
        dims = ", ".join(info["dimensions"])
        lines.append(f"- {name}: metrics=[{metrics}], dimensions=[{dims}]")
    return "\n".join(lines)

# Factory: build AgentEntity from SKILL.md files ───────────────
_AGENT_DIR = Path(__file__).parent / "agent"
_MAIN_SKILL = (_AGENT_DIR / "SKILL.md").read_text()


def _load_skill(*parts: str) -> str:
    """Compose system_prompt from main SKILL.md + nested step SKILL.md."""
    skill_path = _AGENT_DIR.joinpath(*parts) / "SKILL.md"
    try:
        sub = skill_path.read_text()
    except FileNotFoundError:
        logger.warning("SKILL.md not found at %s — using main skill only", skill_path)
        return _MAIN_SKILL
    return f"{_MAIN_SKILL}\n\n---\n# {parts[-1].title()} Sub-Skill\n\n{sub}"


def _make_step_agent(agent_name: str, label: str, short: str,
                     skill_parts: tuple[str, ...]) -> AgentEntity:
    """Construct an AgentEntity with its skill binding."""
    return AgentEntity(
        agent_name=agent_name,
        system_prompt=_load_skill(*skill_parts),
        label=label,
        short=short,
    )


# 7 preconstructed AgentEntity for the 7 report steps ──────────
interpret_agent  = _make_step_agent(
    "interpret_query", "Query Interpreter", "Interpret",
    ("report", "interpret"),
)
fetch_agent = _make_step_agent(
    "fetch_data", "Data Fetcher", "Fetch",
    ("report", "fetch"),
)
generate_agent = _make_step_agent(
    "generate_report", "Report Generator", "Generate",
    ("report", "generate"),
)
charts_agent = _make_step_agent(
    "render_charts", "Chart Renderer", "Charts",
    ("report", "charts"),
)
compliance_agent = _make_step_agent(
    "check_compliance", "Compliance Check", "Comply",
    ("report", "compliance"),
)
review_agent = _make_step_agent(
    "human_review", "Human Review", "Review",
    ("report", "review"),
)
publish_agent = _make_step_agent(
    "publish", "Publisher", "Publish",
    ("report", "publish"),
)


# ── Chart WOT sub-hive (nested inside render_charts) ─────────
# 4 AgentEntity steps: elaborate → implement → test → verify
# Each with its own SKILL.md. The chart_wot is invoked per
# <blackbox tag="chart"> by chart_renderer.render_all_charts.

chart_elaborate_agent = _make_step_agent(
    "chart_elaborate", "Chart Elaborator", "Elaborate",
    ("report", "charts", "elaborate"),
)
chart_implement_agent = _make_step_agent(
    "chart_implement", "Chart Implementor", "Implement",
    ("report", "charts", "implement"),
)
chart_test_agent = _make_step_agent(
    "chart_test", "Chart Tester", "Test",
    ("report", "charts", "test"),
)
chart_verify_agent = _make_step_agent(
    "chart_verify", "Chart Verifier", "Verify",
    ("report", "charts", "verify"),
)


# ── WOT hive (bind ReportRequest + chain 7 AgentEntity) ─────
report_wot = Hive(app, name="report", type="wot")
report_wot.bind(ReportRequest, step_records=STEP_RECORDS)

(
    report_wot.from_input()
    .to_agent(interpret_agent)   .will({"parsed_query":      "parsed_query"})
    .to_agent(fetch_agent)       .will({"data_result":       "data_result"})
    .to_agent(generate_agent)    .will({"report_content":    "report_content"})
    # render_charts internally invokes chart_wot per <blackbox tag="chart">
    .to_agent(charts_agent)      .will({"report_html":       "report_html",
                                        "charts":            "charts"})
    .to_agent(compliance_agent)  .will({"compliance_result": "compliance_result"})
    .to_agent(review_agent)      .will({"review_decision":   "review_decision"})
    .to_agent(publish_agent)     .will({"published":         "report_content"})
    .to_output()
)


# ── Inject LLM function + per-step tool filter ──────────────
# Defense in depth: (1) state-guard in each @tool (records.py) prevents
# the pipeline from being corrupted even if the LLM picks a wrong tool.
# (2) tool_schemas filter at the handler level means qwen only SEES the
# relevant tools for the current step, so with tool_choice=required it
# can't pick anything else.
from .llm import chat_completion
from tachikoma.hive.wot_handler import WOTStepHandler
from tachikoma.stateful.decorators.tool import extract_openai_schemas

# The single tool exposed per state — mirrors _STATE_TRANSITIONS in records.py.
_STEP_TOOLS = {
    "interpret_query":  ["save_interpretation"],
    "fetch_data":       ["fetch_warehouse_data"],
    "generate_report":  ["save_report"],
    "render_charts":    ["render_report_charts"],
    "check_compliance": ["run_compliance_check"],
    "human_review":     ["approve", "request_revision", "reject"],
    "publish":          ["publish_report"],
}


def _prep_step_agent(ae: AgentEntity, entity_cls) -> None:
    """Pre-build the WOTStepHandler with filtered tools + qwen llm_fn."""
    step_name = ae.agent_name
    allowed = set(_STEP_TOOLS.get(step_name, []))
    all_schemas = extract_openai_schemas(entity_cls)
    tool_schemas = [
        s for s in all_schemas
        if s.get("function", {}).get("name") in allowed
    ] if allowed else None

    ae._wot_handler = WOTStepHandler(
        step_name=step_name,
        system_prompt=ae.system_prompt,
        label=ae.label or step_name,
        short=ae.short or step_name,
        intro_message=getattr(ae, "intro_message", ""),
        llm_fn=chat_completion,
        tool_schemas=tool_schemas,
    )
    logger.info("[prep %s] tools=%s", step_name,
                [s["function"]["name"] for s in (tool_schemas or [])])


# Pre-build handlers for every report_wot step
for _ae in (interpret_agent, fetch_agent, generate_agent, charts_agent,
            compliance_agent, review_agent, publish_agent):
    _prep_step_agent(_ae, ReportRequest)


# ── Chart WOT hive (invoked per blackbox from render_charts) ─
# Declared but currently not bound to a StatefulRecord because
# the existing chart_renderer.py has its own entity life-cycle.
# The 4 AgentEntity above can be wired later via a dedicated
# chart_wot.ask() call from render_report_charts.

chart_wot = Hive(app, name="chart", type="wot")
(
    chart_wot.from_input()
    .to_agent(chart_elaborate_agent).will({"spec":        "spec"})
    .to_agent(chart_implement_agent).will({"svg":         "svg",
                                           "html":        "html"})
    .to_agent(chart_test_agent)     .will({"test_result": "test_result"})
    .to_agent(chart_verify_agent)   .will({"verified":    "verified"})
    .to_output()
)
# Chart WOT agents — no entity bound, leave handlers to be created lazily

# ── Build the global Hive topology ──────────────────────────
# Every user-path is a case; each case terminates in a continuous
# to_loop handler. Polymorphic=True deserializes before dispatch.

(
    iris.from_topic(input_topic)

    .switch(polymorphic=True)

        .case(is_init)       .to_loop(handle_init)
        .case(is_reset)      .to_loop(handle_reset)
        .case(is_chat)       .to_loop(handle_chat)
        .case(is_review)     .to_loop(handle_review)
        .case(is_search)     .to_loop(handle_search)
        .case(is_kanban)     .to_loop(handle_kanban)
        .case(is_treefile)   .to_loop(handle_treefile)
        .case(is_datasource) .to_loop(handle_datasource)
        .case(is_dashboard)  .to_loop(handle_dashboard)
        .case(is_history)    .to_loop(handle_history)
        .otherwise()         .to_loop(handle_unknown)

)

# ── Register ────────────────────────────────────────────────

monorepo = Monorepo(app)
monorepo.register(iris)
monorepo.register(report_wot)
monorepo.register(chart_wot)

# ── Expose ──────────────────────────────────────────────────

app.iris = iris
app.report_wot = report_wot
app.chart_wot = chart_wot
app.event_bus = event_bus

# ── Routes ──────────────────────────────────────────────────

app.page("/api/iris/action")(IrisActionView)
app.page("/api/iris/events")(IrisEventsView)
