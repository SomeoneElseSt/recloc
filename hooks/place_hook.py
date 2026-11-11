"""The nudge hook: when the agent uses an unmapped place, tell it to run /add-place.

Kept as a backstop. A one-line mention in the prompt makes the command
discoverable; this fires only when the agent actually tries an unknown place.
"""

from __future__ import annotations

from ..places import places

# Tool names whose `place` argument may name a saved place.
PLACE_TOOLS = {"add_reminder"}


def unmapped_place_hook(*, tool_name: str = "", args: dict | None = None, **kwargs):
    """pre_tool_call hook: block the call and point at /add-place when the place is unknown."""
    if tool_name not in PLACE_TOOLS:
        return None
    place = str((args or {}).get("place") or "").strip()
    if not place:
        return None
    known = places.normalize_name(place) in places.load_places()
    # A literal address is legitimate too: it contains a digit or a comma.
    looks_literal = any(ch.isdigit() for ch in place) or "," in place
    if known or looks_literal:
        return None
    return {
        "action": "block",
        "message": (
            f"No saved place called {place!r}. Ask the user to run "
            f"/add-place {place} so the address can be saved, or ask them for the full address."
        ),
    }
