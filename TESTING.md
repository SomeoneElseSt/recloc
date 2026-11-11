# Testing it on your VM

The branch is `feat/location-reminders-plugin-arch` on `SomeoneElseSt/hermes-agent`.
The plugin lives in `~/.hermes/plugins/location-reminders/` and is opt-in.

## 1. Get the branch onto the VM

```bash
cd ~/.hermes/hermes-agent
git remote add steve https://github.com/SomeoneElseSt/hermes-agent.git   # once
git fetch steve
git checkout -b feat/location-reminders-plugin-arch steve/feat/location-reminders-plugin-arch
```

## 2. Install the plugin (later wins over bundled ones)

Copy the plugin directory onto the box, then enable it:

```bash
mkdir -p ~/.hermes/plugins/location-reminders
# scp the four files + subdirs into it
hermes plugins list                 # it should appear, disabled
hermes plugins enable location-reminders
```

## 3. Give it the webhook

Export the secret where Hermes runs — never in `config.yaml`:

```bash
echo 'BRRR_WEBHOOK_URL=https://api.brrr.now/v1/<secret>' >> ~/.hermes/.env
```

## 4. Validate, then run

```bash
hermes plugins doctor location-reminders --ci     # discovery, manifest, register(), registries
hermes plugins validate location-reminders        # the same check catalog CI runs
```

Then talk to it:

```bash
hermes -z "add a place called walgreens at 135 Powell St, San Francisco"
hermes -z "remind me at walgreens to buy microfiber cloths"
```

`/add-place walgreens` in an interactive session does the same, except the address
never reaches the agent — the command asks you for it directly.

## Expected results

- The first command returns `{"ok": true, "saved": "walgreens"}` and writes
  `~/.hermes/plugin-data/location-reminders/places.json`.
- The second posts a line like `HERMES|walgreens|buy microfiber cloths|anytime`
  and your phone should get the brrr push.
- `hermes -z "what places do you have saved"` returns names with **redacted**
  addresses — confirming the agent never holds the full address.

## Worth checking while you're at it

- `list_places` redaction: ask for saved places and confirm the address is truncated.
- The nudge: ask for a reminder at an unsaved place like "trader joes" — the turn
  should be blocked with a message pointing at `/add-place trader joes`.
- A literal address: "remind me at 600 Montgomery St to check the office" should go
  straight through without needing a saved place.
