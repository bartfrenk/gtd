import gkeepapi.node
import pytest

from gtd.keep import ChecklistItem, Credentials, KeepNoteClient


def test_credentials_holds_email_and_master_token():
    creds = Credentials(email="user@example.com", master_token="token123")
    assert creds.email == "user@example.com"
    assert creds.master_token == "token123"


def test_credentials_hides_master_token_from_repr():
    creds = Credentials(email="user@example.com", master_token="secret-token-12345")
    creds_repr = repr(creds)
    assert "user@example.com" in creds_repr
    assert "secret-token-12345" not in creds_repr


def test_checklist_item_holds_text_and_checked():
    item = ChecklistItem(text="Buy milk", checked=True)
    assert item.text == "Buy milk"
    assert item.checked is True


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
    # Assign explicit sort values in descending order to ensure deterministic ordering.
    # List.sorted_items returns items ordered by sort value descending, so earlier items
    # get higher sort values to preserve insertion order.
    sort_value = 1000 + len(items) * 100
    for text, checked in items:
        note.add(text, checked, sort=sort_value)
        sort_value -= 100
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
