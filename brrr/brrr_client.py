"""brrr client: deliver one reminder notification, and not trust a 202.

What the phone tests taught us:
- The shortcut's location field only resolves when the Subtitle STARTS with an
  address. A leading place name ("Walgreens 300 Montgomery St") fails silently.
- A place name is fine only when parenthesised after the address.
- HTTP 202 from brrr means "accepted", NOT delivered: repeats sometimes vanish.
  So we retry transient failures and record every accepted push for auditing.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request

WEBHOOK_ENV = "BRRR_WEBHOOK_URL"
DEFAULT_TITLE = "Reminder"
# brrr rejects Python's default "Python-urllib/x" user agent with a bare 403.
USER_AGENT = "location-reminders-hermes-plugin/0.1 (+https://github.com/NousResearch/hermes-agent)"
REQUEST_TIMEOUT_SECS = 15
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECS = 1.0
BACKOFF_CAP_SECS = 8.0
# Statuses worth retrying: throttling, auth blips and server-side failures.
RETRYABLE_STATUS = {403, 408, 429, 500, 502, 503, 504}
ACCEPTED_STATUS = 202

# Street suffixes that make a string address-like even without a leading number
# (the phone accepted "Montgomery St, San Francisco, CA 94104").
STREET_SUFFIXES = (
    "st", "street", "ave", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive",
    "ln", "lane", "way", "pl", "place", "ct", "court", "cir", "circle", "hwy", "highway",
    "pkwy", "parkway", "sq", "square", "ter", "terrace", "plaza", "row", "walk", "loop",
)
_SUFFIX_RE = re.compile(r"\b(?:" + "|".join(STREET_SUFFIXES) + r")\b\.?", re.IGNORECASE)
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+[a-zA-Z]?\s+\S")


class BrrrError(RuntimeError):
    """A delivery failure the caller should surface, not swallow."""


def webhook_url() -> str | None:
    # Through Hermes' secret scope, not os.environ: a gateway serves several
    # profiles, and os.environ returns the LAUNCH profile's value, not this one's.
    from agent.secret_scope import get_secret
    url = (get_secret(WEBHOOK_ENV) or "").strip()
    return url or None


def validate_address(address: str) -> str | None:
    """An error message if the address will not resolve on the phone, else None.

    Heuristic, deliberately offline: the phone is the real authority, but a
    string that starts with a place name and carries no street suffix is the
    failure mode we reproduced, so it is refused before it reaches the user.
    """
    address = address.strip()
    if not address:
        return "the address is empty"
    if not (_LEADING_NUMBER_RE.match(address) or _SUFFIX_RE.search(address)):
        return (
            f"{address!r} does not look like an address the phone can resolve — "
            "it must start with the address itself (e.g. '300 Montgomery St, San Francisco, CA'), "
            "not a place name"
        )
    # A leading place name before any street token is the exact case that failed.
    # "Montgomery St, San Francisco" is fine: the first token is the street name itself.
    # From the phone tests, on the first comma-separated segment:
    #   with a number  — it must START with that number ("300 Montgomery St" ok,
    #                    "Walgreens 300 Montgomery St" failed)
    #   without one    — it must carry a street suffix ("Montgomery St, San Francisco" ok,
    #                    "Walgreens FiDi" failed)
    head = address.split(",")[0]
    has_number = any(ch.isdigit() for ch in head)
    starts_with_number = head.split()[0][0].isdigit()
    if has_number and starts_with_number:
        return None
    if not has_number and _SUFFIX_RE.search(head):
        return None
    return (
        f"{address!r} starts with a place name — put the address first and the name in "
        "parentheses, e.g. '300 Montgomery St (Walgreens), San Francisco, CA'"
    )


def format_fields(address: str, text: str, when: str | None = None) -> dict[str, str]:
    """The notification fields: subtitle = the address alone, message = the reminder text.

    The subtitle is only ever the address. The shortcut feeds it straight into the
    location field, and a place name there — inline or parenthesised — is either
    unresolvable or noise the user did not ask to see.
    """
    subtitle = _clean(address)
    message = _clean(text)
    when = (when or "").strip()
    if when:
        message = f"{message} ({when})"
    return {"title": DEFAULT_TITLE, "subtitle": subtitle, "message": message}


def _clean(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def _post(url: str, body: bytes) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECS) as response:
            return response.status, response.read(2048).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(512).decode("utf-8", "replace") if exc.fp else ""
    except urllib.error.URLError as exc:
        raise BrrrError(f"could not reach brrr: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BrrrError("brrr did not answer in time") from exc


def _backoff(attempt: int) -> float:
    delay = min(BACKOFF_CAP_SECS, BACKOFF_BASE_SECS * (2 ** (attempt - 1)))
    # Jitter so a retry storm does not line up on the same instant.
    return delay + random.uniform(0, delay / 2)


def send(fields: dict[str, str]) -> dict:
    """Deliver one notification, retrying transient failures.

    Returns {"status", "response", "attempts"} on acceptance; raises BrrrError
    when every attempt failed, with the last status and body for the log.
    """
    url = webhook_url()
    if url is None:
        # Point at the fix, not just the missing variable: the user asked the agent
        # to set this up, so the reply should say what to do next.
        raise BrrrError(
            f"{WEBHOOK_ENV} is not set on this machine. Run /recloc-setup to get the phone "
            "setup prompt, and export BRRR_WEBHOOK_URL from the brrr app in ~/.hermes/.env."
        )
    body = json.dumps(fields).encode("utf-8")
    last_status, last_body = None, ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, payload = _post(url, body)
        last_status, last_body = status, payload
        if status == ACCEPTED_STATUS and "success" in payload.lower():
            return {"status": status, "response": payload.strip()[:200], "attempts": attempt}
        if status not in RETRYABLE_STATUS:
            break  # a hard rejection: retrying would just repeat it
        if attempt < MAX_ATTEMPTS:
            time.sleep(_backoff(attempt))
    raise BrrrError(f"brrr did not accept the notification after {attempt} attempt(s): HTTP {last_status} {last_body[:120]}")
