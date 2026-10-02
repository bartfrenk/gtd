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

## Resolved design decisions

### Recurrence on promotion: reschedule, don't just delete

If a promoted item had a repeater (`SCHEDULED: <2026-10-15 Thu +1w>`),
`TicklerInbox.clear()` advances its `SCHEDULED` date in `tickler.org` instead
of dropping it — the item is copied to the destination inbox *and* kept in
the tickler for its next occurrence, mirroring what Emacs does when you mark
a repeating TODO `DONE`. Only non-repeating items are removed outright once
promoted. Approximate algorithm per repeater prefix (`n`, `unit` from
`orgparse`'s parsed repeater; `today` = promotion date):

- `+n<unit>` (cumulative): advance from the *original* scheduled date in
  steps of `n<unit>` until the result is after `today` — keeps the series
  anchored to its original date (e.g. always-the-15th), not to whenever it
  happened to be promoted.
- `++n<unit>` (catch-up): same computation as `+`; org's catch-up vs.
  cumulative distinction is about equidistant missed cycles, which doesn't
  matter at the precision this feature needs.
- `.+n<unit>` (from-today): anchor resets to `today + n<unit>`, regardless of
  the original date.

### Write-side guardrail: an Emacs refile hook, not app-side validation

Items land in `tickler.org` by refiling a headline during Clarify (`C-c C-w`
in the org files registered in `org-refile-targets`), not through any `gtd`
command — so the guardrail belongs where the refile happens, in the user's
Doom config (`~/.config/doom/modules/local/gtd/config.el`), not in this
repo's Python code. `org-refile-target-verify-function` isn't the right hook
for this — it filters candidate *destination* headings, not the entry being
moved. The correct hook is `org-after-refile-insert-hook`, which runs with
point on the newly-inserted entry, in the destination buffer, after the copy
but before the source subtree is deleted: if the destination file is
`tickler.org` and the inserted entry has no `SCHEDULED` property, delete the
just-inserted copy and signal `user-error` — this aborts `org-refile` before
it deletes the original, so the refile as a whole is a no-op other than the
error message. Sketch:

```elisp
(defun gtd--tickler-file-p (file)
  (file-equal-p file (gtd--path "tickler.org")))

(defun gtd--reject-undated-tickler-refile ()
  (when (gtd--tickler-file-p (buffer-file-name))
    (unless (org-entry-get nil "SCHEDULED")
      (let ((beg (point)) (end (org-end-of-subtree t t)))
        (delete-region beg end)
        (user-error "Refusing to refile into tickler.org without a SCHEDULED date")))))

(add-hook 'org-after-refile-insert-hook #'gtd--reject-undated-tickler-refile)
```

This also needs `tickler.org` added to `org-refile-targets` in
`gtd--register-files` so it's a refile destination at all.

### Time-of-day: compare at date granularity

`available_at <= now` is really `available_at.date() <= date.today()` — org
`SCHEDULED` values are calendar days, not timestamps, so a tickler item
dated today should be promoted on first sync that day regardless of time of
day (no timezone-aware datetime math needed).

## Suggested next step

File a separate implementation ticket covering: `Item.available_at`,
`gtd/tickler.py` (`Config`, `TicklerInbox.get_items`/`clear()` with the
reschedule-on-repeat logic above, date-granularity comparison), the
`InboxConfig`/`build_inbox` wiring, and — as a companion change in the
`~/.config/doom` repo, not this one — the `org-after-refile-insert-hook`
guardrail and the `tickler.org` refile target.
