# Remarkable inbox

## Problem

GTD-367Q wants a `remarkable` inbox kind: the user keeps a document (say
`/Inbox`) on their reMarkable tablet and jots down to-dos on it by hand. `gtd
sync` should pull that document, turn each handwritten line into an `Item`,
hand it to the destination inbox, and leave the reMarkable document ready to
be written on again — same source→destination→`clear()` shape as
`tasks`/`spotify`/`tickler`.

Two things make this source different from the others: the content isn't
structured data behind an API (it's a PDF of ink strokes, so turning it into
items needs OCR), and reading it costs real time and possibly money (an OCR
pass), so it matters whether a given sync actually needs to do that work.
Hence the ticket's two questions, answered below.

## Current architecture (relevant pieces)

- `Inbox` (`gtd/core.py`): `get_items(status)`, `add(items)`, `clear()`.
  `run_sync` (`gtd/__main__.py`) pulls open items from every non-destination
  source, `add()`s them to the one destination, then `clear()`s the source —
  but **only if `get_items` actually yielded something** (`if not items:
  continue` skips both `add` and `clear`). That short-circuit matters here:
  it means "should we do the expensive OCR work" and "should we clear" are
  the same decision, made once, inside `get_items`.
- There's already a bespoke local project for talking to reMarkable:
  `/home/bart/code/projects/remarkable`, installed both as a `uv tool` (the
  `remarkable` CLI mentioned in the ticket: `register`/`upload`/`replace`/
  `download`/`delete`) and usable as a library (`RemarkableClient`). It wraps
  the unofficial reMarkable Cloud sync protocol directly (no `rmapi`
  dependency). Not yet a dependency of this repo — it's a local path, so it'd
  be added to `pyproject.toml` as a `path`-sourced dependency, the same way
  the CLI is installed via `uv tool install --from /home/bart/code/projects/remarkable`.
- Relevant shape of that library (`remarkable/client.py`):
  - `list_documents()` walks the account's root index and, for each
    top-level entry, fetches its small `.docSchema` index + `.metadata` JSON
    to recover `visible_name`/`parent`/`type`/**`hash`**. This only reads
    index/metadata text, never PDF/page bytes — cost scales with the number
    of documents in the account, not their size.
  - `download(path)` = `list_documents()` + `resolve_path()` + fetch the
    actual PDF bytes (the expensive part).
  - `replace_pdf(path_or_file, name=, folder=)` uploads a new PDF under the
    given name, then moves any pre-existing document with that name (in that
    folder) to the trash — upload-before-trash, so a failure never leaves
    neither version live.
  - `delete(path)` moves a document to the trash (`parent` set to the
    `"trash"` id); there's no "permanently wipe now" call, matching how the
    tablet itself handles deletes.
  - The protocol is content-addressed throughout: a document's `hash`
    changes exactly when any of its parts (strokes, metadata, …) change.
    There is no mutation API — every change is "upload new content, retarget
    metadata to point at it," never "edit these bytes in place."

## Question 1 — can the Inbox file be cleared?

**Yes, but as "recreate," not "wipe in place"** — the sync protocol has no
in-place edit, so `clear()` can't zero out the existing document's content.
The available primitive is `RemarkableClient.replace_pdf()`: upload a fresh
blank one-page PDF named e.g. `Inbox` into the configured folder; the
library uploads it first, then trashes whatever was previously at that name.
Net effect from the user's perspective: the same path now contains a blank
page, and the handwritten one they just filled in is in the tablet's trash
(recoverable, not instantly destroyed) — the same safety margin
`TasksInbox.clear()` and `SpotifyInbox.clear()` already get for free by
deleting-after-reading rather than wiping.

This fits `RemarkableInbox.clear()` directly: ship a tiny blank PDF as a
packaged resource (or generate one on the fly — a single blank page needs no
library beyond a few hardcoded PDF bytes) and call `replace_pdf` with it on
every `clear()`.

Two caveats worth flagging, both about *when* the tablet sees the new blank
page rather than whether clearing works:

- **Sync latency on the device side.** `replace_pdf` changes the cloud copy
  immediately, but the tablet only picks it up next time it syncs. If the
  user keeps writing on the (now-stale, locally cached) old document between
  our `clear()` and the tablet's next sync, those new strokes exist only on
  the device and will be overwritten/orphaned once it does sync and sees the
  document was replaced. This is a real UX edge case but not a code
  problem — same class of risk as editing a Google Doc offline while someone
  else replaces it.
- **Read/clear race.** Because there's no partial edit, `clear()` can only
  replace the *whole* document, not "remove what `get_items` already read"
  the way `TicklerInbox.clear()` does. If the user adds a new stroke on the
  tablet and it syncs to the cloud in the narrow window between our
  `download()` (for OCR) and our `replace_pdf()` (for clear), that stroke is
  lost. Mitigate by keeping that window small (don't do anything slow
  between download and clear) rather than trying to make it correct in
  general — not worth more complexity for a window measured in seconds.

## Question 2 — cheap OCR, and a timestamp/skip mechanism

### Skip mechanism: the document's content hash, not a timestamp

The library already gives us something strictly better than a wall-clock
timestamp: `DocumentEntry.hash` from `list_documents()`/`resolve_path()`.
It's a content hash of the document's index (which transitively covers its
pages and metadata), so it changes if and only if the document's content
changed — no clock skew, no "touched but unchanged" false positives, no
reliance on the tablet or cloud reporting modification times honestly.

Design: `RemarkableInbox` keeps a small local cache (one file, analogous to
`TokenCache`) mapping `path -> last-seen hash`. On `get_items()`:

1. Call `list_documents()` + `resolve_path()` to get the Inbox entry's
   current `hash`. This alone is cheap (index/metadata reads scoped to the
   account's document count, no PDF bytes).
2. If it matches the cached hash from the last successful OCR run, yield
   nothing — `run_sync`'s `if not items: continue` then skips `add` *and*
   `clear` for free, so the no-op case costs exactly one cheap listing call
   and nothing else, every sync.
3. If it differs (or there's no cached hash yet), `download()` the PDF, OCR
   it (see below), yield the resulting items, and only persist the new hash
   once OCR succeeds — so a crash mid-OCR retries next sync instead of
   silently skipping real content.

This directly answers the latency concern: the expensive path (download +
OCR) only runs when the user actually wrote something new, which is far
rarer than "every sync."

### OCR: a vision LLM given page images beats dedicated OCR here

Three options considered:

1. **Vision LLM (e.g. Claude Haiku, GPT-4o-mini, Gemini Flash) on page
   images, prompted to directly emit a list of to-do items** — recommended.
   Render each PDF page to PNG locally (e.g. `pymupdf`, pure-Python wheel,
   no system dependency, not currently in `pyproject.toml`), send the
   image(s) with a prompt like "list each handwritten line item on this page
   as a to-do; ignore crossed-out items; respond as JSON." This collapses
   OCR and parsing into one step and reads messy handwriting noticeably
   better than dedicated OCR engines, since these models are trained on
   exactly this kind of document-understanding task rather than
   character-level transcription. Cost per call is fractions of a cent at
   the small end of these model families, and since step 3 above means this
   only runs when the hash changed, total cost is "a few cents a month,"
   not "a few cents times every sync." This repo has no existing LLM
   dependency, so picking a provider/SDK is a decision to make explicitly
   (open question below) rather than something this doc should force.
2. **Local specialized handwriting-OCR model** (e.g. TrOCr-large-handwritten
   via `transformers`, or GOT-OCR2.0) — zero marginal cost and fully
   offline, but handwriting accuracy is noticeably worse than a frontier
   vision LLM on messy/mixed print-cursive notes, and it only yields raw
   text, needing a second parsing pass to split into discrete items
   (bullets, checkboxes, line breaks). Worth keeping as a fallback if the
   recurring-cloud-call model ever becomes undesirable, but given option 1's
   cost is already hash-gated to "rarely," that trade doesn't pay off today.
3. **reMarkable's own handwriting recognition** ("Convert to text" in the
   app, MyScript-based) — not pursued: it isn't covered by the existing
   `remarkable` library's reverse-engineered protocol, so using it means
   reverse-engineering another undocumented endpoint for marginal benefit
   over option 1. Revisit only if option 1 proves insufficient in practice.

## Recommendation

1. Add the local `remarkable` project as a path dependency; add `pymupdf`
   for PDF→PNG rendering.
2. New `gtd/remarkable.py`: `Config(kind: Literal["remarkable"])` (path on
   the tablet, folder, local hash-cache location, OCR provider credentials),
   `RemarkableInbox` implementing the hash-gated `get_items()` from Question
   2 and the replace-based `clear()` from Question 1.
3. Wire into `InboxConfig.config`'s discriminated union and `build_inbox`,
   same as every other inbox kind.

## Open questions

1. **Which vision-LLM provider/SDK** to add, since the repo has none today —
   depends on which the user already has billing/API-key setup for.
2. **Where the local hash cache and blank-page template PDF live** — likely
   next to `TokenCache` (`gtd/token_cache.py`) and as a packaged resource
   respectively, but not yet designed in detail.
3. **Multi-page Inbox documents** — if the user fills more than one page
   before a sync, all pages need rendering + OCR; the options above already
   handle this (loop pages, merge resulting items) but it's untested against
   a real multi-page handwritten document.

## Suggested next step

File a separate implementation ticket covering: `gtd/remarkable.py`
(`Config`, `RemarkableInbox.get_items()`/`clear()` per the recommendation
above), the chosen vision-LLM dependency, the `pyproject.toml`/
`InboxConfig`/`build_inbox` wiring, and a blank-page template resource —
once the open questions above are settled.
