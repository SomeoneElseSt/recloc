"""The reminder tools: validate the address, format the fields, deliver them.

Every handler keeps the shape Hermes requires — ``(args: dict, **kwargs) -> str``,
always a JSON string, never raising.
"""

from __future__ import annotations

import json

from ..brrr import brrr_client
from ..places import places


def _ok(**fields) -> str:
    return json.dumps({"ok": True, **fields})


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def add_reminder(args: dict, **kwargs) -> str:
    """`place` is a saved alias or a literal address; `text` is what to remember."""
    place = str(args.get("place") or "").strip()
    text = str(args.get("text") or "").strip()
    if not place or not text:
        return _err("need both place and text")

    address = places.resolve_place(place)
    problem = brrr_client.validate_address(address)
    if problem is not None:
        return _err(problem)

    fields = brrr_client.format_fields(address, text, when=args.get("when"))
    try:
        result = brrr_client.send(fields)
    except brrr_client.BrrrError as exc:
        return _err(str(exc))
    return _ok(
        title=fields["title"],
        subtitle=fields["subtitle"],
        delivered=result["status"],
        attempts=result["attempts"],
        address_from=place,
        note="brrr accepted it; delivery to the phone is not guaranteed by that",
    )


def list_reminders(args: dict, **kwargs) -> str:
    """Delivery is immediate and nothing is queued, so there is no backlog to list."""
    return _ok(reminders=[], note="delivery is immediate; nothing is queued")


def cancel_reminder(args: dict, **kwargs) -> str:
    """A delivered notification cannot be recalled — say so instead of pretending."""
    reminder_id = str(args.get("id") or "").strip()
    if not reminder_id:
        return _err("need an id")
    return _err("a delivered notification cannot be recalled — delete the reminder on your phone")


def save_place(args: dict, **kwargs) -> str:
    name = str(args.get("name") or "").strip()
    address = str(args.get("address") or "").strip()
    problem = brrr_client.validate_address(address)
    if problem is not None:
        return _err(f"not saved: {problem}")
    try:
        key = places.set_place(name, address)
    except ValueError as exc:
        return _err(str(exc))
    return _ok(saved=key)


def edit_place(args: dict, **kwargs) -> str:
    name = str(args.get("name") or "").strip()
    address = str(args.get("address") or "").strip()
    if places.normalize_name(name) not in places.load_places():
        return _err(f"no saved place called {name!r} — add it first")
    problem = brrr_client.validate_address(address)
    if problem is not None:
        return _err(f"not updated: {problem}")
    try:
        key = places.set_place(name, address)
    except ValueError as exc:
        return _err(str(exc))
    return _ok(updated=key)


def list_places(args: dict, **kwargs) -> str:
    return _ok(places=places.places_for_agent())


def remove_place(args: dict, **kwargs) -> str:
    name = str(args.get("name") or "").strip()
    if places.remove_place(name):
        return _ok(removed=places.normalize_name(name))
    return _err(f"no saved place called {name!r}")
