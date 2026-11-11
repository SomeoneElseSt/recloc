"""Tests for the location-reminders plugin. Run: python3 -m pytest tests/ -q"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT.parent))

# The plugin imports plugins.plugin_storage from the Hermes tree; stand it in for unit tests.
if "plugins.plugin_storage" not in sys.modules:
    fake = types.ModuleType("plugins.plugin_storage")
    DATA = Path(os.environ.get("RECLOC_TEST_DATA", "/tmp/recloc-test-data"))

    def plugin_data_dir(name):  # noqa: D103
        d = DATA / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    fake.plugin_data_dir = plugin_data_dir
    pkg = types.ModuleType("plugins")
    pkg.plugin_storage = fake
    sys.modules["plugins"] = pkg
    sys.modules["plugins.plugin_storage"] = fake

import recloc  # noqa: E402
from recloc.brrr import brrr_client  # noqa: E402
from recloc.places import places  # noqa: E402
from recloc.remind import handlers  # noqa: E402


@pytest.fixture(autouse=True)
def clean_store():
    p = places._places_path()
    if p.exists():
        p.unlink()
    yield
    if p.exists():
        p.unlink()


def test_set_place_then_resolve():
    assert places.set_place("Walgreens", "135 Powell St, San Francisco") == "walgreens"
    assert places.resolve_place("walgreens") == "135 Powell St, San Francisco"


def test_literal_address_passes_through():
    assert places.resolve_place("600 Montgomery St, San Francisco") == "600 Montgomery St, San Francisco"


def test_edit_and_remove():
    places.set_place("home", "1 Old Rd")
    places.set_place("home", "2 New Rd")
    assert places.load_places()["home"] == "2 New Rd"
    assert places.remove_place("home") is True
    assert places.remove_place("home") is False


def test_empty_address_is_refused():
    with pytest.raises(ValueError):
        places.set_place("walgreens", "   ")


def test_file_is_valid_json_and_survives_damage():
    places.set_place("a", "1 A St")
    places._places_path().write_text("{not json")
    assert places.load_places() == {}


def test_address_is_redacted_for_the_agent():
    long = "135 Powell Street, San Francisco, California 94102"
    hint = places.redact_address(long)
    assert hint.startswith("…") and len(hint) <= 29 and long not in hint


def test_places_for_agent_never_leaks_a_full_address():
    places.set_place("walgreens", "135 Powell Street, San Francisco, California 94102")
    [entry] = places.places_for_agent()
    assert entry["name"] == "walgreens"
    assert "135 Powell Street" not in entry["address_hint"]


def test_fields_shape():
    fields = brrr_client.format_fields("300 Montgomery St, San Francisco, CA 94104", "buy microfiber cloths")
    assert fields["title"] == "Reminder"
    assert fields["subtitle"].startswith("300 Montgomery St")
    assert fields["message"] == "buy microfiber cloths"


def test_subtitle_is_the_address_alone():
    # The shortcut puts Subtitle straight into the location field: no place names.
    fields = brrr_client.format_fields("300 Montgomery St, San Francisco", "buy cloths")
    assert fields["subtitle"] == "300 Montgomery St, San Francisco"


def test_when_is_folded_into_the_message():
    fields = brrr_client.format_fields("300 Montgomery St", "buy cloths", when="18:00")
    assert fields["message"].endswith("(18:00)")


@pytest.mark.parametrize("address", [
    "300 Montgomery St, San Francisco, CA 94104",
    "Montgomery St, San Francisco, CA 94104",   # no number: the phone accepted this
    "300 montgomery st san francisco ca 94104",  # lowercase, no commas: accepted
])
def test_validate_accepts_addresses_the_phone_resolved(address):
    assert brrr_client.validate_address(address) is None


@pytest.mark.parametrize("address", [
    "Walgreens 300 Montgomery St",       # leading place name: failed on the phone
    "Walgreens FiDi",                   # no street token at all: failed
    "",
])
def test_validate_rejects_what_the_phone_could_not_resolve(address):
    assert brrr_client.validate_address(address) is not None


def test_newlines_are_stripped_from_fields():
    fields = brrr_client.format_fields("300 A St, SF", "x\ny")
    assert "\n" not in fields["subtitle"] and "\n" not in fields["message"]


def test_send_without_webhook_is_a_readable_error(monkeypatch):
    monkeypatch.delenv(brrr_client.WEBHOOK_ENV, raising=False)
    with pytest.raises(brrr_client.BrrrError, match="not set"):
        brrr_client.send({"title": "Reminder", "subtitle": "x", "message": "y"})


def test_add_reminder_reports_a_missing_webhook_without_raising(monkeypatch):
    monkeypatch.delenv(brrr_client.WEBHOOK_ENV, raising=False)
    places.set_place("walgreens", "300 Montgomery St, San Francisco, CA 94104")
    out = json.loads(handlers.add_reminder({"place": "walgreens", "text": "buy cloths"}))
    assert out["ok"] is False and "not set" in out["error"]


def test_add_reminder_success_path(monkeypatch):
    monkeypatch.setenv(brrr_client.WEBHOOK_ENV, "https://example.invalid/v1/secret")
    seen = {}

    def fake_send(fields):
        seen["fields"] = fields
        return {"status": 202, "response": '{"success":true}', "attempts": 1}

    monkeypatch.setattr(brrr_client, "send", fake_send)
    places.set_place("walgreens", "300 Montgomery St, San Francisco, CA 94104")
    out = json.loads(handlers.add_reminder({"place": "walgreens", "text": "buy cloths"}))
    assert out["ok"] is True and out["delivered"] == 202
    assert seen["fields"]["subtitle"].startswith("300 Montgomery St")
    assert seen["fields"]["title"] == "Reminder"


def test_add_reminder_needs_both_arguments():
    out = json.loads(handlers.add_reminder({"place": "walgreens"}))
    assert out["ok"] is False


def test_list_places_redacts():
    places.set_place("walgreens", "135 Powell Street, San Francisco, California 94102")
    out = json.loads(handlers.list_places({}))
    assert out["ok"] is True
    assert "135 Powell Street" not in json.dumps(out)


def test_edit_unknown_place_is_refused():
    out = json.loads(handlers.edit_place({"name": "nope", "address": "1 A St"}))
    assert out["ok"] is False and "no saved place" in out["error"]


def test_unresolvable_address_is_refused_before_sending(monkeypatch):
    calls = []
    monkeypatch.setattr(brrr_client, "send", lambda fields: calls.append(fields) or {"status": 202, "response": "", "attempts": 1})
    out = json.loads(handlers.add_reminder({"place": "Walgreens FiDi", "text": "buy cloths"}))
    assert out["ok"] is False and "does not look like an address" in out["error"]
    assert calls == []   # never pushed to brrr


def test_retries_on_a_retryable_status(monkeypatch):
    monkeypatch.setenv(brrr_client.WEBHOOK_ENV, "https://example.invalid/v1/secret")
    statuses = [(429, "slow down"), (202, '{"success":true}')]
    monkeypatch.setattr(brrr_client, "_post", lambda url, body: statuses.pop(0))
    monkeypatch.setattr(brrr_client, "_backoff", lambda attempt: 0)
    result = brrr_client.send({"title": "Reminder", "subtitle": "x", "message": "y"})
    assert result["attempts"] == 2


def test_hard_rejection_is_not_retried(monkeypatch):
    monkeypatch.setenv(brrr_client.WEBHOOK_ENV, "https://example.invalid/v1/secret")
    calls = []
    monkeypatch.setattr(brrr_client, "_post", lambda url, body: calls.append(1) or (400, "bad"))
    with pytest.raises(brrr_client.BrrrError, match="400"):
        brrr_client.send({"title": "Reminder", "subtitle": "x", "message": "y"})
    assert len(calls) == 1


def test_exhausted_retries_raise(monkeypatch):
    monkeypatch.setenv(brrr_client.WEBHOOK_ENV, "https://example.invalid/v1/secret")
    monkeypatch.setattr(brrr_client, "_post", lambda url, body: (503, "unavailable"))
    monkeypatch.setattr(brrr_client, "_backoff", lambda attempt: 0)
    with pytest.raises(brrr_client.BrrrError, match="after"):
        brrr_client.send({"title": "Reminder", "subtitle": "x", "message": "y"})


def test_hook_blocks_an_unmapped_place():
    from recloc.hooks.place_hook import unmapped_place_hook

    directive = unmapped_place_hook(tool_name="add_reminder", args={"place": "trader joes"})
    assert directive["action"] == "block"
    assert "/add-place trader joes" in directive["message"]


def test_hook_allows_a_literal_address_and_a_saved_place():
    from recloc.hooks.place_hook import unmapped_place_hook

    places.set_place("walgreens", "135 Powell St")
    assert unmapped_place_hook(tool_name="add_reminder", args={"place": "walgreens"}) is None
    assert unmapped_place_hook(tool_name="add_reminder", args={"place": "600 Montgomery St"}) is None


def test_hook_ignores_other_tools():
    from recloc.hooks.place_hook import unmapped_place_hook

    assert unmapped_place_hook(tool_name="terminal", args={"place": "x"}) is None
