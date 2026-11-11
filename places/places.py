"""Saved places: a name mapped to one address, stored in the plugin data dir.

The mapping is the valuable thing here, so it lives outside the install tree
(``plugin_data_dir`` survives updates and removals) and is written atomically.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from plugins.plugin_storage import plugin_data_dir

PLUGIN_NAME = "location-reminders"
PLACES_FILE = "places.json"
# Enough of an address to tell two branches apart, never the whole thing.
ADDRESS_TAIL_CHARS = 28


def _places_path() -> Path:
    return plugin_data_dir(PLUGIN_NAME) / PLACES_FILE


def load_places() -> dict[str, str]:
    """Every saved place as {name: address}. A missing or damaged file is empty, not fatal."""
    try:
        raw = json.loads(_places_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def save_places(places: dict[str, str]) -> None:
    """Replace the mapping atomically, so a crash can never leave it half-written."""
    target = _places_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(places, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def normalize_name(name: str) -> str:
    return name.strip().lower()


def set_place(name: str, address: str) -> str:
    """Add or replace a place. Returns the normalized name."""
    key = normalize_name(name)
    if not key:
        raise ValueError("place name is empty")
    address = address.strip()
    if not address:
        raise ValueError("address is empty")
    places = load_places()
    places[key] = address
    save_places(places)
    return key


def remove_place(name: str) -> bool:
    key = normalize_name(name)
    places = load_places()
    if key not in places:
        return False
    del places[key]
    save_places(places)
    return True


def resolve_place(name_or_address: str) -> str:
    """A saved alias resolves to its address; anything else is taken as a literal address."""
    return load_places().get(normalize_name(name_or_address), name_or_address.strip())


def redact_address(address: str) -> str:
    """The tail of an address, for the agent: `…Powell St (San Francisco)`."""
    address = address.strip()
    if len(address) <= ADDRESS_TAIL_CHARS:
        return address
    return "…" + address[-ADDRESS_TAIL_CHARS:]


def places_for_agent() -> list[dict[str, str]]:
    """Saved places with addresses redacted — the agent never holds a full address."""
    return [
        {"name": name, "address_hint": redact_address(address)}
        for name, address in sorted(load_places().items())
    ]
