# Content Pipeline Runbook — `constant-reader-content-pipeline`

Documentation only. Nothing in this file changes the routine's behavior.

## What it actually is

This is **not** a Windows Scheduled Task and **not** a GitHub Actions workflow — this
repo has neither. It is a **Claude Code cloud Routine** (a scheduled cloud agent,
`trigger_id: trig_01Gv8dwW3KNwo8foGVDBgndz`), created 2026-07-08. Each fire spins up a
fresh, isolated cloud session with its own throwaway git checkout of this repo
(`persist_session: false` — no state carries over between runs except what's committed
to `main`). The site's own GitHub Actions tab only shows `pages-build-deployment`,
GitHub's built-in Pages hosting deploy — that's a side effect of the pipeline's push,
not the pipeline itself.

## Trigger schedule

- Cron: `0 13 * * 1,4` — **Mondays and Thursdays at 13:00 UTC**.
- Model: `claude-sonnet-5`.
- Tools available to the run: `Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch`.
- Repo source: `https://github.com/mschlegel/constant-reader`, branch `main`.

## What it reads

- `topics_backlog.md` at the repo root — four buckets under `##` headers (Reading order
  guides, Best/worst rankings, Per-book deep dives, Book-vs-adaptation comparisons).
  Unchecked items (`- [ ]`) are pre-ordered highest-traffic-potential first within each
  bucket; the prompt explicitly tells the agent not to reorder this list.
- The last 2 checked-off (`- [x]`) items across the whole file, to decide which bucket
  to pull from next (round-robins buckets, avoids repeating the same bucket as both of
  the last 2 picks).
- Two existing articles in `content/` (e.g. `stephen-king-reading-order.md`,
  `it-plot-summary-ending-explained.md`) as a style/voice/frontmatter reference.
- Facts researched live via `WebSearch`/`WebFetch` for accuracy (publication years,
  adaptation cast/dates, plot details).

## One unit of work

Per fire, the routine does exactly one pass:

1. Picks the topmost unchecked item in the next bucket in rotation.
2. Researches and writes one ~1200–1500 word Markdown article to `content/<slug>.md`
   (YAML frontmatter: title, slug, description, date; 2–5 Amazon affiliate search
   links using the fixed pattern `.../s?k=...&tag=YOURTAG-20`, never a fabricated ASIN).
3. Checks off that topic in `topics_backlog.md`, appending `— published <date>, slug: <slug>`.
4. **Backlog top-up exception:** if fewer than 5 unchecked topics remain in total, it
   first writes ~10 new topics (same ordering convention) before picking one — and
   says so in the commit message.

## Self-verification before committing

- Installs its own build deps fresh every run (`pip install --user markdown jinja2
  pyyaml` — the repo's `venv/` is gitignored and never persists between fires), then
  runs `python build.py`.
- Confirms the build reports one more article than before.
- Spot-checks the new article's rendered `docs/<slug>/index.html` for unrendered Jinja
  (`{{`, `{%`) and for the presence of the affiliate/internal links.

There is no automated test suite and no human review gate — verification is entirely
the agent re-reading its own rendered output inside the same run.

## State it updates

- New file: `content/<slug>.md`
- `topics_backlog.md`: one item checked off
- `docs/`: full rebuild output (every page, since `build.py` regenerates the whole site
  from templates + content each time, not just the new article)

## Commit and push

`git add -A`, commit message `Add article: <title>`, then `git push origin main` —
**directly to `main`, no branch, no PR, no review step.** The routine is explicitly
told not to touch `site_config.json`'s `affiliate_tag`/`site_url`, not to change its
own schedule, and not to start a second site/niche.

## On failure

The prompt has no defined failure/retry/rollback path. If `pip install`, `build.py`,
or `git push` fails mid-run, the session simply ends without having completed the
checklist — there's no compensating step to revert a partial `topics_backlog.md` edit
or a partial `content/` write. The next scheduled fire (3 or 4 days later) would pick
up whatever state was left, which could mean a checked-off backlog item with no
corresponding published article, or vice versa. This hasn't been observed in the
run history checked so far (all recent runs show `ROUTINE_RUN_STATUS_SUCCEEDED`), but
nothing prevents it.

## Independent health check

Because the routine has no failure handling and nothing tells a human when a
run dies silently, a separate, independent watchdog exists:
`.github/workflows/pipeline-health-check.yml`, a GitHub Actions **scheduled
workflow** — not a Claude Routine, so it doesn't share the Routine's own
failure mode (a Routine watching a Routine could die the same silent way).

- **Schedule:** `0 16 * * 1,4` — the same two days as the content routine,
  three hours after its `0 13 * * 1,4` window, so a merely slow run isn't
  mistaken for a dead one.
- **What it watches:** the timestamp of the most recent commit that touches
  `content/`. Every real unit of work the routine does ends in exactly one
  new file under `content/` (see "One unit of work" above), so this is the
  most direct proxy for "did the routine actually publish today" that's
  available from git history alone — more precise than a rolling multi-day
  window, which could let one missed run hide behind the next successful one
  three or four days later. The check compares that timestamp against
  *today's* 13:00 UTC (the cron fires this workflow only on the routine's own
  scheduled days, so "today" is always a day a run was expected).
- **How failure surfaces:** if no `content/` commit landed at or after
  today's 13:00 UTC cutoff, the job exits non-zero with an `::error::` message
  naming both the expected cutoff and the actual last-touched timestamp.
  GitHub emails the repo owner automatically on scheduled-workflow failure —
  no extra service, no secrets, nothing to configure.
- **If it fires:** check the Routine's run history in the Claude Code cloud
  dashboard for the failed date. Common causes per "On failure" below: a
  `pip install` hiccup, a `build.py` error, or a `git push` rejection (e.g.
  local commits sitting unpushed on `main` — see "Fragility worth flagging").
  If the routine's checkout diverged or a partial `topics_backlog.md`/
  `content/` edit was left behind, reconcile by hand before the next
  scheduled fire; the routine itself has no compensating rollback step.
- Manual test: `gh workflow run pipeline-health-check.yml --ref main` runs it
  on demand (e.g. to re-check sooner, or to sanity-test after editing it).

## Fragility worth flagging

- **Direct push to `main` with no coordination against human edits.** This is exactly
  what caused the divergence this runbook's own history was written to resolve: two
  local commits made outside the routine sat unpushed while the routine kept
  fast-forwarding `main` on its own schedule. There's no lock, no PR, no signal to a
  human editor that the routine is about to push. Any local work-in-progress on this
  repo that isn't pushed before the next Monday/Thursday 13:00 UTC fire will diverge
  again the same way.
- **No persisted environment.** Every run reinstalls `markdown`/`jinja2`/`pyyaml` from
  scratch into a throwaway checkout — a transient PyPI issue or version drift on any
  of those packages would fail the run with no retry.
- **No content review gate.** Factual accuracy depends entirely on the model's own
  web research inside a single run; nothing else checks it before it's live and
  indexed.
- **Self-expanding backlog.** When the backlog runs low, the routine writes its own
  next ~10 topics unsupervised. This keeps the pipeline running indefinitely without
  a human ever re-approving what it writes about next.
