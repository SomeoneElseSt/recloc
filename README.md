# recloc

Location reminders for [Hermes](https://github.com/NousResearch/hermes-agent) — ask your agent
*"remind me to buy microfiber cloths when I'm at Walgreens"* and Apple Reminders alerts you when
you arrive. Your location never leaves your phone: iOS watches the geofence on-device; the agent
only ever posts a notification.

## How it works

```
you → Hermes agent → plugin → brrr webhook → push notification → iPhone shortcut → Apple Reminders
                                                                                    ↓
                                                        iOS geofences on-device → you're alerted on arrival
```

The plugin turns a request into one brrr notification whose **subtitle is the address** and whose
**message is the reminder text**. An iOS Shortcuts notification automation picks it up and creates
the reminder with a *When I Arrive* alert. Nothing listens on your machine — the VM only makes
outbound HTTPS calls.

## Install

```bash
# on the machine running Hermes
mkdir -p ~/.hermes/plugins/recloc && cp -R . ~/.hermes/plugins/recloc
hermes plugins enable recloc
echo 'BRRR_WEBHOOK_URL=https://api.brrr.now/v1/<secret>' >> ~/.hermes/.env
```

Get the webhook URL from the [brrr](https://brrr.now) app. Export it wherever Hermes runs — never
commit it, and never put it in `config.yaml`.

Then set up the phone side once. The agent hands you the exact prompt to paste into Apple Intelligence — get it any time with `/setup`, or read [`iphone/SHORTCUT.md`](iphone/SHORTCUT.md).

## Tools the agent gets

| Tool | What it does |
|---|---|
| `add_reminder(place, text)` | Send a location reminder. `place` is a saved name or a full address. |
| `list_places()` | Saved places by name, with addresses **redacted**. |
| `save_place(name, address)` / `edit_place` / `remove_place` | Manage the mapping. |
| `list_reminders()` / `cancel_reminder(id)` | Delivery is immediate; a sent notification can't be recalled. |

`/add-place <name> <address>` does the same as `save_place`, except the address never reaches the
agent — it goes straight into the mapping.

## The address contract

The shortcut puts the subtitle straight into the location field, which only resolves when the
subtitle **starts with the address**. The plugin rejects anything else before sending. Tested
against a real iPhone:

| Subtitle | Result |
|---|---|
| `300 Montgomery St, San Francisco, CA 94104` | works |
| `Montgomery St, San Francisco, CA 94104` | works — no street number needed |
| `300 montgomery st san francisco ca 94104` | works — case and commas don't matter |
| `300 Montgomery St (Walgreens), San Francisco, CA` | works — name parenthesised, after the address |
| `Walgreens 300 Montgomery St` | fails — a place name leads |
| `Walgreens FiDi` | fails — no address at all |

So: **the subtitle must start with the address, never a place name.**

## Delivery isn't guaranteed

brrr answering `HTTP 202` means the request was accepted, not that the phone received it — one
identical push silently vanished in testing and worked on retry. The plugin retries throttled or
failed requests with backoff, and reports what it knows without claiming the phone got it. The
shortcut's confirmation notification is how you check.

## Development

```bash
python3 -m pytest tests/ -q
```

30 tests, no network, no Hermes install required — the tests stand in for `plugin_data_dir`.
