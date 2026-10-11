# GitHub deployment and future migration

The batch monitor runs with Python 3.11+ and jq. No Docker or third-party Python
packages are required. The existing Compose deployment remains available for a
future VPS and as a local fallback.

## Verified activation — October 11, 2026

GitHub run [38177107975](https://github.com/jonathan-velez/dsrt-surf-tracker/actions/runs/38177107975)
completed successfully at 14:37 Los Angeles time. The generated `monitor-data`
branch contains 166 pricing groups, 1,115 upcoming sessions across 13 queried
months, and an error-free status record. The user confirmed receipt of the
labeled migration test through the existing ntfy destination. Daily reports
remain muted. Future scheduled invocations are not yet verified by observation.
For later delivery checks, run the workflow with `notification_test=true`; this
sends a clearly labeled test, not a simulated pricing change.

## Activate

1. Commit and push the source, including `.github/workflows/monitor.yml`, to the
   repository's default branch. Repository visibility is unchanged; reports have
   the same visibility as the repository. Use a private repository if reports
   should be private. The workflow does not create a separate private repository.
2. Allow GitHub Actions and ensure repository policy permits the workflow's
   `contents: write` permission. Branch rules must allow it to create/update
   `monitor-data`. Do not require PRs for that generated-data branch.
3. In Actions, select **DSRT monitor**, then **Run workflow**, mode `all`.
   Confirm the run succeeds and `monitor-data/status.json` has no errors.
4. Inspect `pricing/latest.json` and `availability/latest.json` on `monitor-data`.
   The initial observation creates new baselines; it does not import Docker
   history or send initial alerts. Keep the old volumes for historical reference.
5. Once the GitHub run succeeds, stop the local Compose services if you want only
   one active collector. Do not remove the Docker volumes.

Preserve the existing settings: pricing notifications are enabled in the local
deployment, while availability notifications are muted. Before cutover, set the
repository Actions secret `PRICING_NTFY_URL` to the existing destination's HTTPS
topic URL. Leave `AVAILABILITY_NTFY_URL` unset to retain the daily watch's mute.
The workflow cannot read local Docker notification settings automatically.
For the existing public ntfy configuration, upload it without exposing the URL:

```sh
GH_CONFIG_DIR="$PWD/.local/github" gh auth login --hostname github.com
python3 scripts/configure-github-notifications.py --check
python3 scripts/configure-github-notifications.py
```

The alternate ignored CLI configuration directory avoids this Mac's root-owned
`~/.config` directory. GitHub authentication requires your interactive sign-in.
These must be full HTTPS URLs (not Apprise `ntfy://` URLs). An unguessable topic is
not equivalent to authenticated storage. This credential stays out of the data
branch. Configure and test notification delivery separately before relying on it.

## Scheduling and storage

- Pricing: minute 17 every three hours, current Los Angeles month.
- Availability: UTC 05:17 and 06:17, with a Los Angeles hour-22 guard to select the
  correct DST slot. Late runs outside hour 22 skip availability. Manual `daily`
  or `all` can collect immediately; the existing 22:00 slot cache prevents repeats.
- GitHub scheduling can delay or drop runs. A missed nightly collection results
  in a comparison across the gap, not reconstructed observations.
- One concurrency group serializes scheduled/manual runs. GitHub may replace
  pending runs during a backlog; it is not a guaranteed job queue.
- The `monitor-data` branch stores both baselines, daily raw responses/reports,
  pricing changes, and last-run status. Failed fetches preserve the valid baseline.
  Partial success is persisted even when the overall run fails.
- Snapshot files older than 90 days are removed from the current tree. **Git
  commit history still retains them**, so this is not a total repository size cap.
  Review branch size periodically and export/rotate it if necessary. Generated
  data does not trigger this workflow because it has no push trigger.
- Alerts are saved before delivery. Pending alerts survive send failures;
  delivery is at least once, so crashes or failed acknowledgement pushes can
  produce duplicates. Without a destination, pending alerts are discarded.
- Full reports remain in the branch. Large notification messages are summarized
  and link to that branch. Private reports require GitHub sign-in to read.
- No Actions artifacts or caches are used for durable baselines.

GitHub Free's private-repository minute allowance is shared across projects.
Set an Actions usage budget that stops paid usage at your chosen limit. Monitor
failed runs through GitHub notification settings; ntfy is for reports, not a
separate guarantee of collector-health monitoring. Public repository schedules
can be disabled after 60 days of inactivity; check Actions status periodically.

## Run on another host

```sh
python3 monitor/run.py --state /path/to/dsrt-state --mode pricing
python3 monitor/run.py --state /path/to/dsrt-state --mode daily
python3 monitor/run.py --state /path/to/dsrt-state --mode notify
```

Set `PRICING_NTFY_URL` and/or `AVAILABILITY_NTFY_URL` in the environment for
collection and delivery according to each watch's enabled notification settings.
Save/back up state between collection and delivery. Use one writer; the scripts
do not implement a cross-host lock. Cron/systemd on a VPS can invoke these commands
with the state directory on persistent disk, or use the original Compose stack.

To migrate: disable the GitHub workflow, export the latest `monitor-data` tree,
verify the new host can read the baselines, test a collection, then activate its
schedule. Do not run two writers against one baseline.

Cloudflare migration requires adapting filesystem persistence to D1/R2 and the
Python/jq execution to its runtime. Preserve the pricing group schema and the
availability session/slot schema, atomic successful-baseline replacement, and
the existing normalization/exclusion tests. A full changedetection.io history
import is a separate migration; its native datastore differs from these files.

## Validation

```sh
./tests/test-normalization.sh
python3 tests/test_availability.py
python3 tests/test_monitor.py
```

Local tests do not confirm GitHub permissions, remote scheduling, upstream access
from GitHub runners, or notification delivery. The first remote run validates
those deployment-specific boundaries.
