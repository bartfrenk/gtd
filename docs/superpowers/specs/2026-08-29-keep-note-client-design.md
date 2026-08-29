# Google Keep note client — design

## Purpose

Provide a client that fetches the checklist items from a specific Google Keep
note, identified by title, for use in the `gtd` project.

## Approach

Google Keep has no official public API for personal (`@gmail.com`) accounts.
We use the unofficial [`gkeepapi`](https://github.com/kiwiz/gkeepapi) library,
which authenticates against Keep's private sync API using a Google *master
token* (obtained once via `gpsoauth`, outside the scope of this client) rather
than the account password.

## Components

Location: `src/gtd/keep.py`.

```python
@dataclass
class Credentials:
    email: str
    master_token: str

@dataclass
class ChecklistItem:
    text: str
    checked: bool

class KeepNoteClient:
    def __init__(self, title: str, credentials: Credentials):
        ...

    def fetch_items(self) -> list[ChecklistItem]:
        ...
```

- **`Credentials`** — a plain dataclass bundling `email` and `master_token`.
  Construction and sourcing of these values (env vars, secrets manager, etc.)
  is the caller's responsibility, not this client's.
- **`ChecklistItem`** — a plain dataclass representing one checklist entry:
  its text and checked state.
- **`KeepNoteClient`** — takes the target note's `title` and a `Credentials`
  instance at construction. No network I/O happens in `__init__`.
  - `fetch_items()`:
    1. Lazily logs in via `gkeepapi.Keep().resume(email, master_token)` on
       first call, caching the authenticated `Keep` instance on `self` for
       subsequent calls.
    2. Looks up the note via `keep.find(query=title)`, matching titles
       exactly (case-sensitive). Raises `LookupError` if zero or more than
       one note matches.
    3. Confirms the matched note is a checklist (`gkeepapi.node.List`).
       Raises `TypeError` if it is not.
    4. Maps the note's `items` to a list of `ChecklistItem(text, checked)`
       and returns it.

## Error handling

- Authentication and network errors from `gkeepapi.Keep.resume()` propagate
  unwrapped — the caller needs to see the underlying `gkeepapi` exception to
  diagnose auth/network problems.
- Note-lookup and note-type problems (not found, ambiguous, wrong type) are
  domain-specific to this client and raised as `LookupError` / `TypeError` so
  callers can distinguish "note problem" from "auth/network problem".

## Testing

Unit tests with a fake/injectable `gkeepapi.Keep` (constructor-injected or
monkeypatched), covering:

- Happy path: single matching checklist note → correct `ChecklistItem` list.
- Note not found (zero matches) → `LookupError`.
- Ambiguous title (multiple matches) → `LookupError`.
- Matched note is not a checklist → `TypeError`.

## Dependencies

Add `gkeepapi` to `pyproject.toml`.
