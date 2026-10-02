# Tickler

## Problem

GTD's Clarify step asks, for each item, "is it actionable?" When the answer is
"not yet, but it will be on a specific date" (give it a week before chasing a
reply, re-read this in a month, renew the passport in six months), the only
place to put it today is the `WAITING` status. `WAITING` has no date attached,
so the only way to find out that one of these items has become actionable
again is to re-scan the *entire* `WAITING` list by hand, every time. That
doesn't scale with the list, and it means the system can't be trusted to
surface things on its own — which is the opposite of the "mind like water" /
externalize-everything premise the rest of this app is built on (see the
*Getting Things Done* and *GTD Workflow* wiki nodes).

David Allen's own system actually keeps these as two separate lists:
*Waiting For* (things blocked on someone else, reviewed weekly) and the
*Tickler File* (the classic 43-folders setup: things that should resurface on
a specific future date, checked daily). This plan is about implementing the
second one — a date-driven resurfacing mechanism — not about replacing
`WAITING`.

The *GTD Workflow* wiki node's cadence table is useful here: the daily review
is "continuous plus one short review" whose job is to clear the inbox to
zero, while the Waiting-For *list scan* is explicitly a weekly-review activity.
A tickler should plug into the **daily** cadence (inbox-zero), not add a third
thing to scan weekly: it should deposit due items straight into the inbox so
the existing daily Clarify step picks them up for free. Conveniently, per the
ticket description, opening any inbox already triggers `gtd sync`, so "daily"
comes for free as long as promotion happens inside `sync`.

## Current architecture (relevant pieces)

- `Item` (`gtd/core.py`) is `title`, `description`, `status` — no date field.
- `Inbox.get_items(status)` yields items filtered by `Status`; `Inbox.clear()`
  wipes the *entire* source after a sync moves its items out.
- `run_sync` (`gtd/__main__.py`): for every non-destination inbox, pull all
  items with an open status, `add` them to the one destination inbox, then
  `clear()` the source completely. It assumes "pulled == entire source
  contents," which a tickler breaks (see below).
- `OrgInbox` (`gtd/org.py`) reads/writes an org file via `orgparse`; status is
  the only thing it round-trips today — scheduling isn't read at all, even
  though `orgparse` already parses `SCHEDULED:` lines including repeaters
  (`node.scheduled.start`, `node.scheduled._repeater`).
- Non-obvious `orgparse` gotcha worth flagging: a heading keyword is only
  recognized as a TODO state (`node.todo`) if it's declared via a `#+TODO:`
  line in the file (or matches orgparse's bare `TODO`/`DONE` default).
  `WAITING` already relies on whichever org files are in use declaring
  `#+TODO: TODO NEXT WAITING URGENT | DONE CANCELLED` (or similar) — a new
  `tickler.org` needs the same line, or its items silently fail `node.todo
  is None` and get skipped by `get_items`.

## Options

### Option A — standalone `tickler.org`, examined during sync

A dedicated file. During `gtd sync`, read it, find items whose schedule has
passed, append those to the destination inbox, and rewrite the file with only
the not-yet-due items left in it.

- Pros: fully isolated — no changes to `Inbox`/`Config` at all, easiest to
  prototype, easy to reason about ("one file, one job").
- Cons: it's a one-off special case rather than something that fits the
  `Inbox`/`InboxConfig` model, so it doesn't compose with the rest of the app
  (can't point a tickler at anything but a hardcoded path, doesn't show up in
  `config.yaml` next to other inboxes, needs its own bespoke promotion
  function in `__main__.py` rather than reusing `run_sync`'s source→destination
  loop).

### Option B — new inbox kind: `tickler` (org-backed)

Matches the ticket's own sketch. Add `gtd/tickler.py` with a `Config(kind:
Literal["tickler"])` and a `TicklerInbox`, wired into the `InboxConfig.config`
discriminated union and `build_inbox` next to `tasks`/`org`/`spotify`. It
behaves like `OrgInbox` but:

- `get_items` only yields items whose `SCHEDULED` date is today or earlier
  (ignores future-dated items entirely).
- It's configured as an ordinary *source* inbox in `config.yaml` (not
  `destination: true`), so `run_sync`'s existing source→destination loop
  handles promotion with zero changes to `run_sync` itself.

The one real wrinkle: `run_sync` calls `source.clear()` after moving items,
and today `clear()` means "wipe the whole file." For a tickler file that's
wrong — not-yet-due items must survive. `TicklerInbox.clear()` needs
different semantics than `OrgInbox.clear()`: re-read the file and rewrite it
keeping only the items that were *not* due (i.e., clear = "remove exactly what
`get_items` would currently return," not "truncate").

- Pros: fits the existing `Inbox`/config pattern exactly, needs no `run_sync`
  changes, only a config change for the user (per the ticket's own note) plus
  one new source file.
- Cons: `clear()`'s meaning now differs per inbox implementation in a way
  that isn't obvious from the `Inbox` ABC (nothing in the interface documents
  "clear what was just read" vs. "truncate everything"); a future reader
  could misuse it. Worth a comment on `Inbox.clear()` or a docstring on
  `TicklerInbox` calling this out explicitly.

### Option C — generalize scheduling onto `Item` itself

Same as B, but instead of hiding the "is it due yet" filter inside
`TicklerInbox.get_items`, add `available_at: datetime | None` to `Item` in
`core.py` and do the due/not-due filtering centrally (e.g. a helper used by
both `run_sync` and the tickler inbox). `TicklerInbox` then just parses
`SCHEDULED` into `available_at` on read, same as it parses `status` today.

- Pros: scheduling becomes a first-class, reusable concept instead of being
  wired into one inbox kind. If a future inbox wants it — e.g. `TasksInbox`
  could map Google Tasks' native `due` field onto `available_at` — the
  filtering logic is already shared rather than duplicated per kind.
- Cons: more surface area for a problem the ticket only asks about for org
  files right now; speculative generality the other inboxes don't need yet.

## Recommendation

Option B, with the `available_at`-on-`Item` piece of Option C folded in (i.e.
put the date on `Item` rather than keeping it as filtering logic purely
internal to `TicklerInbox`). Concretely:

1. `Item` gains `available_at: datetime | None = None`.
2. New `gtd/tickler.py`: `Config(kind: Literal["tickler"])` (just a `path`,
   like `org.Config`), `TicklerInbox` that parses `SCHEDULED` (including
   repeaters, see open questions) into `available_at`, filters `get_items` to
   `available_at is None or available_at <= now`, and implements `clear()` as
   "rewrite the file keeping only items *not* returned by the last
   `get_items` call" rather than truncation.
3. Wire `tickler.Config` into `InboxConfig.config`'s union and `build_inbox`.
4. User adds a `tickler.org` entry to `config.yaml` as a regular (non-
   destination) source inbox — no `run_sync` changes needed.

This keeps the blast radius to "one new module + one new config entry,"
mirrors how `spotify.py` was added (see `docs/features/spotify-inbox.md`),
and doesn't touch `run_sync`, `tasks.py`, or `org.py`.

## Open questions to settle before implementing

- **Recurrence on promotion.** If a tickler item has a repeater
  (`SCHEDULED: <2026-10-15 Thu +1w>`), should promoting it to the inbox also
  reschedule it in `tickler.org` for the next occurrence (like Emacs does
  when you mark a repeating TODO done), or should recurrence just not be
  supported initially and only one-off dates ship first? `orgparse` parses
  the repeater (`prefix, n, unit`) but doesn't advance dates itself — that
  logic would need to be written from scratch.
- **Write-side guardrail.** The ticket requires it *not* be possible to move
  an item to the tickler without setting a date. Since items land in
  `tickler.org` by hand-editing during Clarify (there's no `gtd` command that
  writes to it), is the guardrail just documentation/convention, or should
  `TicklerInbox.add()` reject items with `available_at is None` to make
  misuse fail loudly if something ever does call it programmatically?
- **Time of day.** `available_at <= now` comparison needs a decision on
  timezone handling (org dates are naive) — probably compare at date
  granularity (local date, not datetime) to match how org-mode itself treats
  `SCHEDULED` as a day, not a timestamp.

## Suggested next step

File a separate implementation ticket once an option/open-questions are
confirmed with the user — this ticket is the plan, not the build.
