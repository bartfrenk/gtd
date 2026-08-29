from gtd.keep import ChecklistItem, Credentials


def test_credentials_holds_email_and_master_token():
    creds = Credentials(email="user@example.com", master_token="token123")
    assert creds.email == "user@example.com"
    assert creds.master_token == "token123"


def test_checklist_item_holds_text_and_checked():
    item = ChecklistItem(text="Buy milk", checked=True)
    assert item.text == "Buy milk"
    assert item.checked is True
