# DSRT Surf price monitor

A single changedetection.io container monitors **published public reef pricing** every three hours at [localhost:5050](http://localhost:5050). No browser, custom app, database service, or scraper. Notifications start muted.

## Start / stop

Prerequisites: Docker Desktop running on macOS (Apple Silicon supported), Docker Compose, Bash, curl, and jq (`brew install jq` if needed).

```sh
docker compose up -d
# Wait for the dashboard to load, then:
./scripts/setup-watch.sh
```

Open http://localhost:5050. The official image is pinned to the tested digest (changedetection.io 0.60.8); it includes Python jq. The web port binds only to `127.0.0.1`, with timezone `America/Los_Angeles`. State and history live in the named Docker volume.

```sh
docker compose stop        # stop, retain container and history
docker compose start       # resume
docker compose down        # remove container, retain volume
# Do NOT add -v unless you intend to delete all settings and history.
```

Docker Desktop and the Mac must remain awake for checks. Restart policy is `unless-stopped`; enable Docker Desktop login startup if desired. Missed observations while asleep/offline cannot be reconstructed.

## What it measures

`filters/sessions.jq` selects `waveClass=reef`, `audience=public`, and excludes `privateSession=true` (DSRT labels some private sessions public). It groups by exact session name, weekday, and start time, keeping sorted distinct effective prices. It uses numeric `currentPrice`, falling back to `price` only when currentPrice is absent/null. Invalid prices cause errors rather than silently falling back. Integer/decimal formatting is normalized.

Availability, capacity, IDs, and duplicate directions do not affect the result. Different direction prices remain distinct. Blocked and sold-out public sessions remain included. New names/types and both increases and decreases are detected.

- **Published pricing:** prices attached to scheduled public reef sessions, even when unavailable.
- **Currently bookable pricing:** would additionally require availability, booking mode, blocking, and checkout validation; this monitor does not promise that a displayed price can be booked.
- **Catalog/template pricing:** secondary product definitions, potentially internal/unpublished. These are not price floors or booking offers.

Empty, malformed, wrong-schema, and failed HTTP responses produce watch errors and preserve the previous valid baseline. Partial but otherwise valid responses cannot reliably be recognized as incomplete.

## Dates and normal calendar changes

The URL uses changedetection.io's native `{% now 'America/Los_Angeles', '%Y-%m' %}` template. **No monthly script or manual update is needed.** The API returns a padded calendar window for the selected month, not all future sessions. `upcoming=true` removes past sessions, including started sessions on the current day. See [live API findings](docs/api-findings.md).

Grouping hides a session's expiration when another session still represents the same group/price. When the last representative of a group/tier disappears, a change is unavoidable. New schedules and month rollover may also change groups without a price edit. The current-month watch does not cover all farther-future inventory. These limits deliberately avoid a separate stateful aggregation engine.

## Settings and history

Edit `config/watch.json` and rerun `./scripts/setup-watch.sh`. Edit `filters/sessions.jq` the same way. The script finds the exact title, creates or updates one watch, and refuses ambiguous duplicate titles. Keep the title stable to retain identity/history. Running setup reapplies the file's notification settings, including muted defaults.

Change `time_between_check.hours` to adjust polling. Checks use the normal HTTP fetcher. Click the watch's **Diff/history** controls to inspect saved versions; the watch's human-facing link opens [DSRT's calendar](https://book.dsrtsurf.com/app.html#/calendar). Filter changes can themselves cause a historical diff.

The script reads the local instance's API key from its Docker volume without printing it. Alternatively set `CHANGEDETECTION_API_KEY` and `API_URL` in your environment. Do not commit credentials. Local web access is not password protected by this setup; an optional UI password is available in changedetection.io settings.

The image may create example watches on first startup. They can be deleted in the dashboard; setup deliberately does not delete unrelated watches. The initial deployment's examples were removed.

## Optional ntfy notifications

No provider or credentials are required. Once ready, use the watch's Notifications settings to add an Apprise URL, test delivery, and unmute. See [Apprise ntfy syntax](https://github.com/caronc/apprise/wiki/Notify_ntfy). Examples:

- Public ntfy: `ntfy://your-unguessable-topic`
- Your HTTPS ntfy server: `ntfys://ntfy.example.com/your-topic`

For repeatable local configuration, copy the JSON to an ignored file:

```sh
mkdir -p .local
cp config/watch.json .local/watch.json
# Edit .local/watch.json: notification_urls = [your Apprise URL],
# notification_muted = false. Keep credentials out of version control.
./scripts/setup-watch.sh .local/watch.json
```

The prepared message identifies a **pricing change** and links to the booking calendar. It does not claim price-drop-only alerts. No notification delivery was tested because no destination was supplied. A future strict decrease-only mode would need a small comparator at a notification/webhook boundary that matches group identities and compares numeric tiers; native textual diffs alone are insufficient. This is intentionally not implemented.

## Optional catalog

```sh
./scripts/setup-watch.sh config/catalog.json filters/catalog.jq
```

This creates/updates **DSRT Surf — Session Catalog**, paused and muted. Unpause to collect informational history. The filter preserves ID, name, price, wave class/code, and skill fields, sorts deterministically, and removes exact duplicates. Conflicting definitions sharing an ID remain distinct. Missing optional fields become null; malformed required identity/price data errors out.

## Verification / troubleshooting

```sh
./tests/test-normalization.sh
./tests/test-integration.sh
docker compose ps
docker compose logs --tail=80 changedetection
```

Integration tests run the same pinned image in a disposable, network-isolated container, with synthetic JSON served on its internal loopback interface. Test state is tmpfs, the repository is mounted read-only, and no production history is modified. Python is used only in that disposable test harness; the monitor uses native changedetection.io and jq.

On API/network errors, inspect the watch's error and press Recheck after recovery. Do not clear history to hide failures. Check Docker is awake, internet/DNS works, and DSRT still exposes the expected schema. A sudden no-public-reef error may mean the calendar has no published sessions or the API changed. Do not relax validation without inspecting the response.

If setup returns an HTTP validation error, its body identifies the unsupported field. If connection is refused, wait for startup and confirm port 5050 is free. If the API returns 403, check the API key/security setting. Rerun setup after changing filters/settings; do not edit the application code or its datastore files.

To upgrade, update the image digest in both Compose files, run the tests, and recreate production with `docker compose up -d`. Back up the named volume before upgrades. See [validation results](docs/validation.md).
