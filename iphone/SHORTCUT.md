# The shortcut, and the contract behind it

Three actions. That is the whole phone side, and it works because the plugin
does the validating before anything is sent.

## The shortcut

| # | Action | Settings |
|---|---|---|
| 1 | **Add New Reminder** | Title = the notification's **Body** · list **Reminders** · **Show More** → **Remind Me** on → **At a Location** → **When I Arrive** → **Of Location** = the notification's **Subtitle** · radius 300 m |
| 2 | **Show Notification** | `Reminder added: ` followed by **Body**, then **Subtitle** |

No `Get Addresses from Input`, no conversion step, no Receive block.

## The automation

Shortcuts → **Automation** → **+** → **Notification**:
App **brrr** · **Title contains** `Reminder` · **Run Immediately** · runs the shortcut above.

## The contract: the plugin validates, the shortcut trusts

The shortcut feeds the Subtitle straight into the location field. Shortcuts
accepts that only when the string is a real address — given a bare store name it
fails with *"couldn't convert from Text to Location"* and the reminder is created
with no alert. So the plugin refuses anything that is not address-like before it
is pushed (`brrr_client.validate_address`), and the shortcut never has to defend
against it.

That is deliberate: a conversion step in the shortcut only helped sometimes and
made the configuration more fragile. One gate on the server is simpler and
predictable.

## What the phone actually resolved (tested)

| Subtitle sent | Result |
|---|---|
| `300 Montgomery St, San Francisco, CA 94104` | ✅ works |
| `Montgomery St, San Francisco, CA 94104` | ✅ works (no street number needed) |
| `300 montgomery st san francisco ca 94104` | ✅ works (case and commas don't matter) |
| `300 Montgomery St (Walgreens), San Francisco, CA` | ✅ works (name parenthesised, after the address) |
| `Walgreens 300 Montgomery St` | ❌ fails — place name leads |
| `Walgreens FiDi` | ❌ fails — no address at all |

The rule that falls out: **the Subtitle must start with the address itself, never
a place name.** A place name is fine only in parentheses afterwards.

## Delivery is not guaranteed

brrr answering `HTTP 202` means the request was accepted, not that the phone
received it — one identical push silently vanished in testing and the same push
succeeded on retry. The plugin retries throttled or failed requests with backoff,
and reports what it knows (accepted, with attempt count) without claiming the
phone got it. The confirmation notification above is how you check.
