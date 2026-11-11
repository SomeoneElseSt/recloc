"""Location reminders — a Hermes plugin.

Turns "remind me at Walgreens to buy cloths" into an Apple Reminders reminder with
a location alert, while the user's location never leaves their phone.
"""

from __future__ import annotations

from .remind import handlers
from .places import places
from .hooks.place_hook import unmapped_place_hook

PROVIDES_TOOLS = [
    "add_reminder",
    "list_reminders",
    "cancel_reminder",
    "save_place",
    "edit_place",
    "list_places",
    "remove_place",
]


def _tool(name: str, label: str, description: str, schema: dict, handler) -> dict:
    return {"name": name, "label": label, "description": description, "schema": schema, "handler": handler}


_PLACE_SCHEMA = {
    "type": "object",
    "properties": {"place": {"type": "string", "description": "Saved place name or a full address"}},
    "required": ["place"],
}

TOOLS = [
    _tool(
        "add_reminder",
        "Add a location reminder",
        "Send the user a location reminder they will see when they arrive at a place. "
        "Place is a saved name (e.g. walgreens) or a full address.",
        {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "Saved place name or full address"},
                "text": {"type": "string", "description": "What to remind the user about"},
                "when": {"type": "string", "description": "Optional time hint, e.g. 18:00"},
            },
            "required": ["place", "text"],
        },
        handlers.add_reminder,
    ),
    _tool("list_reminders", "List reminders", "List delivered reminders (delivery is immediate).", {"type": "object", "properties": {}}, handlers.list_reminders),
    _tool("cancel_reminder", "Cancel a reminder", "Explain that a delivered notification cannot be recalled.", {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}, handlers.cancel_reminder),
    _tool("save_place", "Save a place", "Save a name to an address. The address stays on the user's machine.", {"type": "object", "properties": {"name": {"type": "string"}, "address": {"type": "string"}}, "required": ["name", "address"]}, handlers.save_place),
    _tool("edit_place", "Edit a saved place", "Change the address of an existing saved place.", {"type": "object", "properties": {"name": {"type": "string"}, "address": {"type": "string"}}, "required": ["name", "address"]}, handlers.edit_place),
    _tool("list_places", "List saved places", "Saved places by name, with addresses redacted.", {"type": "object", "properties": {}}, handlers.list_places),
    _tool("remove_place", "Remove a saved place", "Forget a saved place.", _PLACE_SCHEMA, handlers.remove_place),
]


def register(ctx) -> None:
    """Wire the tools, the backstop hook and the /add-place command."""
    for spec in TOOLS:
        ctx.register_tool(
            name=spec["name"],
            toolset="location-reminders",
            schema={**spec["schema"], "name": spec["name"], "description": spec["description"]},
            handler=spec["handler"],
        )

    ctx.register_hook("pre_tool_call", unmapped_place_hook)

    def _handle_add_place(raw_args: str) -> str:
        # ctx.input does not exist on PluginContext — the gateway swallowed the
        # AttributeError and the command looked dead. Take the address as an
        # argument instead: /add-place <name> <address>
        raw_args = (raw_args or "").strip()
        if not raw_args:
            return "Usage: /add-place <name> <address>"
        name, _, address = raw_args.partition(" ")
        if not address.strip():
            return f"Usage: /add-place {name} <address> — the address is missing."
        name, address = name.strip(), address.strip()
        try:
            places.set_place(name, address)
        except ValueError as exc:
            return f"Could not save: {exc}"
        # The agent learns only that it worked, never the address.
        return f"Saved {name!r}. The agent has been told it exists."

    ctx.register_command(
        "add-place",
        handler=_handle_add_place,
        description="Save a place name to an address (the agent never sees the address)",
    )
