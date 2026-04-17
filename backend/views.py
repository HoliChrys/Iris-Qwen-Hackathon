"""
IRIS Views — dispatches to the global Hive via ask().
"""
from __future__ import annotations

from tachikoma.web import TracedView
from tachikoma.web_sse import TracedSSEView

_INTERNAL = {"_wot_hive", "_booking_wot", "_entity_cls", "_step_records",
             "_lobby_manager", "_event_bus", "_acl_provider", "_lobby_id",
             "_hive", "_correlation_id"}


class IrisActionView(TracedView):
    async def post(self, request):
        body = await request.json()
        if not body.get("session_id"):
            body["session_id"] = "default"

        action = body.pop("action", "chat")
        body["event_type"] = f"iris.{action}"

        hive = getattr(self.tachikoma, 'iris', None)
        if not hive:
            return self.json({"error": "No hive"}, status=500)

        # 300s to accommodate HITL review cast point (wait_respond)
        result = await hive.ask(body, timeout=300.0)

        if isinstance(result, dict):
            for k in _INTERNAL:
                result.pop(k, None)

        return self.json(result)


class IrisEventsView(TracedSSEView):
    pass
