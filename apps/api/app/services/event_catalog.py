"""The events the web may send to `POST /v1/events` (docs/62) — and the properties each may carry.

Mirrors `apps/web/src/lib/analytics/events.ts`. An event not listed here is refused; a property not listed
for its event is dropped. Values are short codes and numbers only: a string longer than `MAX_STR` is
dropped, never cut, so free text (the one-line option text, a chat message) cannot slip in by accident.
`course_id` travels in its own column, not in the properties.
"""

from __future__ import annotations

import math
from typing import Any

MAX_STR = 64
MAX_PROPS = 12

# events another change is adding (the stop sheet, course confirm): accepted now with a generic set
_SHEET = frozenset(
    {"position", "category", "role", "to", "from", "via", "kind", "pinned", "fixed", "rank", "strategy"}
)

EVENT_PROPS: dict[str, frozenset[str]] = {
    # planning
    "plan_started": frozenset({"entry"}),
    "plan_step_completed": frozenset({"step", "step_name", "value"}),
    "preference_style_selected": frozenset({"pace"}),
    "travel_preference_selected": frozenset({"move_style"}),
    "quick_preference_selected": frozenset({"wish", "on"}),
    "advanced_preference_opened": frozenset(),
    "advanced_preference_selected": frozenset({"tag", "state"}),
    "course_generation_started": frozenset({"pace", "wishes", "detailed", "move_style"}),
    "plan_abandoned": frozenset({"step"}),
    "plan_last_choices_applied": frozenset({"fields", "extras"}),
    "course_generate_requested": frozenset({"region", "purpose", "party_size", "budget_total", "transport"}),
    "course_generated": frozenset({"purpose", "budget_total", "price", "stops", "candidates", "latency_ms"}),
    "course_generate_failed": frozenset({"code", "purpose", "budget_total"}),
    # the result screen
    "course_viewed": frozenset({"label", "shared"}),
    "course_saved": frozenset({"price"}),
    "course_shared": frozenset({"method"}),
    "share_clicked": frozenset({"method"}),
    "alternative_selected": frozenset({"label"}),
    "stop_swapped": frozenset({"position", "strategy"}),
    "stop_reason_opened": frozenset({"position"}),
    "stop_reordered": frozenset({"position", "delta"}),
    "stop_pinned": frozenset({"position", "pinned"}),
    "place_link_clicked": frozenset({"position", "to"}),
    "place_sheet_opened": frozenset({"position"}),
    "directions_opened": frozenset({"position", "from"}),
    "reroll_clicked": frozenset({"from_shared", "focus"}),
    "reroll_tweaked": frozenset({"tweaks", "pinned"}),
    "course_settings_changed": frozenset({"changed"}),
    "course_option_toggled": frozenset({"option", "on", "via"}),
    "course_option_text_parsed": frozenset({"length", "matched", "options"}),  # never the text itself
    "familiarity_changed": frozenset({"to"}),
    "budget_whatif_tried": frozenset({"budget_total", "from_budget"}),
    "budget_whatif_opened": frozenset({"budget_total"}),
    "settlement_copied": frozenset({"party_size", "total"}),
    "suggestion_added": frozenset({"role", "price"}),
    "course_feedback_sent": frozenset({"rating"}),
    "visit_marked": frozenset({"rating"}),
    "nearby_shown": frozenset({"kind"}),
    "map_fullscreen": frozenset({"open"}),
    "stay_clicked": frozenset({"day"}),
    # the stop sheet and course confirm (being added in parallel)
    "stop_sheet_opened": _SHEET,
    "stop_fixed": _SHEET,
    "stop_alternative_viewed": _SHEET,
    "stop_swapped_from_sheet": _SHEET,
    "course_confirmed": _SHEET | {"stops", "price"},
    "outbound_link": _SHEET,
    # elsewhere
    "hot_place_opened": frozenset({"region", "place_id", "rank"}),
    "intro_left": frozenset({"via"}),
    "performance_clicked": frozenset({"performance_id"}),
    "banner_clicked": frozenset({"banner_id", "placement"}),
    "event_clicked": frozenset({"event_id", "from"}),
    "attraction_opened": frozenset({"attraction_id", "type"}),
    "attraction_link_clicked": frozenset({"attraction_id", "to"}),
    "explore_filtered": frozenset({"type", "region"}),
    "chat_message_sent": frozenset({"length", "suggested"}),  # not the message
    "chat_course_received": frozenset(),
    "login_clicked": frozenset({"provider"}),
    "signup_completed": frozenset({"method"}),
    "error_shown": frozenset({"code", "where"}),
}

# what the north star (docs/61 §6) counts as "the course was used"
SAVE_EVENTS = frozenset({"course_saved"})
SHARE_EVENTS = frozenset({"share_clicked", "course_shared"})
OUTBOUND_EVENTS = frozenset({"directions_opened", "place_link_clicked", "outbound_link"})
CONFIRM_EVENTS = frozenset({"course_confirmed", "visit_marked"})
# asking for something else instead of taking the course as it is
REGENERATE_EVENTS = frozenset(
    {
        "reroll_clicked",
        "reroll_tweaked",
        "course_settings_changed",
        "course_option_toggled",
        "familiarity_changed",
    }
)
SWAP_EVENTS = frozenset({"stop_swapped", "stop_swapped_from_sheet"})


def is_known(name: str) -> bool:
    return name in EVENT_PROPS


def clean_props(name: str, props: dict[str, Any] | None) -> dict[str, Any]:
    """Only the listed keys, only short scalar values. Anything else is dropped silently."""
    allowed = EVENT_PROPS.get(name, frozenset())
    out: dict[str, Any] = {}
    for key, value in (props or {}).items():
        if key not in allowed or len(out) >= MAX_PROPS:
            continue
        if isinstance(value, bool) or (isinstance(value, int) and abs(value) < 10**12):
            out[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            out[key] = round(value, 4)
        elif isinstance(value, str) and len(value) <= MAX_STR and value.isprintable():
            out[key] = value
    return out
