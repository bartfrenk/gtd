# Google Keep Note Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `KeepNoteClient` that logs into Google Keep with a master token and returns the checklist items of a note identified by title.

**Architecture:** A thin wrapper around the unofficial `gkeepapi` library. `Credentials` and `ChecklistItem` are plain dataclasses; `KeepNoteClient` takes a note title and `Credentials` at construction, lazily authenticates on first `fetch_items()` call, finds the note by exact title match, and maps its checklist items to `ChecklistItem` objects. A `keep_factory` constructor parameter (defaulting to `gkeepapi.Keep`) makes the `gkeepapi.Keep` instance swappable in tests.

**Tech Stack:** Python 3.13, `gkeepapi` (unofficial Keep client), `pytest`, `uv` for dependency/venv management.

**Spec:** `docs/superpowers/specs/2026-08-29-keep-note-client-design.md`

## Global Constraints

- Package/module lives at `src/gtd/keep.py` (importable as `gtd.keep` — `src` is already on `sys.path` for this project via `uv`'s virtual-project `.pth`, no `src/gtd/__init__.py` package marker needed beyond an empty file to make it a package).
- No network calls in `KeepNoteClient.__init__` — authentication happens lazily on first `fetch_items()` call.
- Note lookup is an **exact** (case-sensitive) title match, not `gkeepapi`'s default substring match.
- Auth/network errors from `gkeepapi` propagate unwrapped. Note-lookup problems raise `LookupError`; wrong note type raises `TypeError`.
- Run tests with `uv run pytest`.

---

### Task 1: Project setup — dependencies and `Credentials`/`ChecklistItem` dataclasses

**Files:**
- Modify: `pyproject.toml` (add `gkeepapi` runtime dependency, `pytest` dev dependency)
- Create: `src/gtd/__init__.py`
- Create: `src/gtd/keep.py`
- Test: `tests/test_keep.py`

**Interfaces:**
- Produces: `gtd.keep.Credentials` (dataclass: `email: str`, `master_token: str`), `gtd.keep.ChecklistItem` (dataclass: `text: str`, `checked: bool`).

- [ ] **Step 1: Add dependencies**

Run:
```bash
uv add gkeepapi
uv add --dev pytest
```

- [ ] **Step 2: Create the `gtd` package**

Create `src/gtd/__init__.py` as an empty file.

- [ ] **Step 3: Write the failing test for the dataclasses**

Create `tests/test_keep.py`:

```python
from gtd.keep import ChecklistItem, Credentials


def test_credentials_holds_email_and_master_token():
    creds = Credentials(email="user@example.com", master_token="token123")
    assert creds.email == "user@example.com"
    assert creds.master_token == "token123"


def test_checklist_item_holds_text_and_checked():
    item = ChecklistItem(text="Buy milk", checked=True)
    assert item.text == "Buy milk"
    assert item.checked is True
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_keep.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gtd.keep'` (or similar import error).

- [ ] **Step 5: Implement the dataclasses**

Create `src/gtd/keep.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Credentials:
    email: str
    master_token: str


@dataclass
class ChecklistItem:
    text: str
    checked: bool
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_keep.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/gtd/__init__.py src/gtd/keep.py tests/test_keep.py
git commit -m "feat: add Credentials and ChecklistItem dataclasses for Keep client"
```

---

### Task 2: `KeepNoteClient.fetch_items` happy path

**Files:**
- Modify: `src/gtd/keep.py`
- Test: `tests/test_keep.py`

**Interfaces:**
- Consumes: `Credentials(email: str, master_token: str)`, `ChecklistItem(text: str, checked: bool)` from Task 1.
- Produces: `gtd.keep.KeepNoteClient`, constructed as `KeepNoteClient(title: str, credentials: Credentials, keep_factory: Callable[[], gkeepapi.Keep] = gkeepapi.Keep)`, with method `fetch_items() -> list[ChecklistItem]`.

This task introduces a `FakeKeep` test double that mimics the two `gkeepapi.Keep` methods `KeepNoteClient` uses: `authenticate(email, master_token)` and `find(func=...)`. It wraps real `gkeepapi.node.List`/`gkeepapi.node.ListItem` objects (built via `gkeepapi`'s own API) so the notes under test behave exactly like real ones.

- [ ] **Step 1: Write the failing test for the happy path**

Add to `tests/test_keep.py`:

```python
import gkeepapi.node

from gtd.keep import ChecklistItem, Credentials, KeepNoteClient


class FakeKeep:
    def __init__(self, notes):
        self.notes = notes
        self.authenticated_with = None

    def authenticate(self, email, master_token):
        self.authenticated_with = (email, master_token)

    def find(self, func=None, **kwargs):
        return (note for note in self.notes if func is None or func(note))


def make_list_note(title, items):
    note = gkeepapi.node.List()
    note.title = title
    for text, checked in items:
        note.add(text, checked)
    return note


def test_fetch_items_returns_checklist_items_of_matching_note():
    note = make_list_note("Groceries", [("Milk", False), ("Eggs", True)])
    fake_keep = FakeKeep(notes=[note])
    credentials = Credentials(email="user@example.com", master_token="token123")
    client = KeepNoteClient(
        title="Groceries",
        credentials=credentials,
        keep_factory=lambda: fake_keep,
    )

    items = client.fetch_items()

    assert items == [
        ChecklistItem(text="Milk", checked=False),
        ChecklistItem(text="Eggs", checked=True),
    ]
    assert fake_keep.authenticated_with == ("user@example.com", "token123")


def test_fetch_items_authenticates_only_once():
    note = make_list_note("Groceries", [("Milk", False)])
    fake_keep = FakeKeep(notes=[note])
    factory_calls = []

    def keep_factory():
        factory_calls.append(1)
        return fake_keep

    credentials = Credentials(email="user@example.com", master_token="token123")
    client = KeepNoteClient(title="Groceries", credentials=credentials, keep_factory=keep_factory)

    client.fetch_items()
    client.fetch_items()

    assert len(factory_calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_keep.py -v`
Expected: FAIL — `KeepNoteClient` does not exist (`ImportError`).

- [ ] **Step 3: Implement `KeepNoteClient` happy path**

Replace the contents of `src/gtd/keep.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import gkeepapi
import gkeepapi.node


@dataclass
class Credentials:
    email: str
    master_token: str


@dataclass
class ChecklistItem:
    text: str
    checked: bool


class KeepNoteClient:
    def __init__(
        self,
        title: str,
        credentials: Credentials,
        keep_factory: Callable[[], gkeepapi.Keep] = gkeepapi.Keep,
    ) -> None:
        self._title = title
        self._credentials = credentials
        self._keep_factory = keep_factory
        self._keep: gkeepapi.Keep | None = None

    def fetch_items(self) -> list[ChecklistItem]:
        keep = self._authenticated_keep()
        note = self._find_note(keep)
        return [ChecklistItem(text=item.text, checked=item.checked) for item in note.items]

    def _authenticated_keep(self) -> gkeepapi.Keep:
        if self._keep is None:
            keep = self._keep_factory()
            keep.authenticate(self._credentials.email, self._credentials.master_token)
            self._keep = keep
        return self._keep

    def _find_note(self, keep: gkeepapi.Keep) -> gkeepapi.node.List:
        matches = list(keep.find(func=lambda node: node.title == self._title))
        note = matches[0]
        return note
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_keep.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gtd/keep.py tests/test_keep.py
git commit -m "feat: implement KeepNoteClient.fetch_items happy path"
```

---

### Task 3: `KeepNoteClient` error handling — not found, ambiguous title, wrong note type

**Files:**
- Modify: `src/gtd/keep.py`
- Test: `tests/test_keep.py`

**Interfaces:**
- Consumes: `KeepNoteClient`, `FakeKeep`, `make_list_note` from Task 2.
- Produces: no new public names — `KeepNoteClient._find_note` now raises `LookupError` (zero or multiple matches) and `TypeError` (matched note is not a `gkeepapi.node.List`).

- [ ] **Step 1: Write the failing tests for error cases**

Add to `tests/test_keep.py`:

```python
import pytest


def test_fetch_items_raises_lookup_error_when_note_not_found():
    fake_keep = FakeKeep(notes=[])
    credentials = Credentials(email="user@example.com", master_token="token123")
    client = KeepNoteClient(
        title="Groceries",
        credentials=credentials,
        keep_factory=lambda: fake_keep,
    )

    with pytest.raises(LookupError):
        client.fetch_items()


def test_fetch_items_raises_lookup_error_when_title_is_ambiguous():
    notes = [
        make_list_note("Groceries", [("Milk", False)]),
        make_list_note("Groceries", [("Eggs", False)]),
    ]
    fake_keep = FakeKeep(notes=notes)
    credentials = Credentials(email="user@example.com", master_token="token123")
    client = KeepNoteClient(
        title="Groceries",
        credentials=credentials,
        keep_factory=lambda: fake_keep,
    )

    with pytest.raises(LookupError):
        client.fetch_items()


def test_fetch_items_raises_type_error_when_note_is_not_a_checklist():
    note = gkeepapi.node.Note()
    note.title = "Groceries"
    fake_keep = FakeKeep(notes=[note])
    credentials = Credentials(email="user@example.com", master_token="token123")
    client = KeepNoteClient(
        title="Groceries",
        credentials=credentials,
        keep_factory=lambda: fake_keep,
    )

    with pytest.raises(TypeError):
        client.fetch_items()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_keep.py -v`
Expected: FAIL — the not-found case raises `IndexError` instead of `LookupError`, the ambiguous case silently returns the first match instead of raising, and the wrong-type case raises `AttributeError` (no `.items` on `Note`) instead of `TypeError`.

- [ ] **Step 3: Implement the error handling**

In `src/gtd/keep.py`, replace `_find_note`:

```python
    def _find_note(self, keep: gkeepapi.Keep) -> gkeepapi.node.List:
        matches = list(keep.find(func=lambda node: node.title == self._title))
        if len(matches) == 0:
            raise LookupError(f"No note found with title {self._title!r}")
        if len(matches) > 1:
            raise LookupError(f"Multiple notes found with title {self._title!r}")
        note = matches[0]
        if not isinstance(note, gkeepapi.node.List):
            raise TypeError(f"Note {self._title!r} is not a checklist note")
        return note
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_keep.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gtd/keep.py tests/test_keep.py
git commit -m "feat: raise LookupError/TypeError for Keep note lookup failures"
```
