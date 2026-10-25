import pytest
import app as banking_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "test_banking.db"
    monkeypatch.setattr(banking_app, "DATABASE", database)

    banking_app.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
    )

    with banking_app.app.test_client() as client:
        # Trigger DB initialization
        client.get("/")
        yield client


# ---------------- HELPER UTILITIES ----------------

def create_and_login_user(
    client,
    username="sender_user",
    name="Sender User",
    password="Password123!",
):
    """Registers and authenticates a test user, returning user dict and CSRF token."""
    client.get("/register")
    with client.session_transaction() as sess:
        token = sess["_csrf_token"]

    client.post(
        "/register",
        data={
            "csrf_token": token,
            "name": name,
            "username": username,
            "password": password,
        },
        follow_redirects=True,
    )

    db = banking_app.get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    with client.session_transaction() as sess:
        active_csrf = sess["_csrf_token"]

    return dict(user), active_csrf


def create_recipient_user(
    username="recipient_user",
    name="Recipient User",
    account_number="RB-8888",
    balance=5000.00,
):
    """Directly creates a recipient account in the test database."""
    db = banking_app.get_db()
    db.execute(
        """
        INSERT INTO users (name, username, password, account_number, balance)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, username, "dummy_password_hash", account_number, balance),
    )
    db.commit()
    user = db.execute("SELECT * FROM users WHERE account_number = ?", (account_number,)).fetchone()
    return dict(user)


def get_user_by_account(account_number):
    """Retrieves current user row from database by account number."""
    db = banking_app.get_db()
    row = db.execute("SELECT * FROM users WHERE account_number = ?", (account_number,)).fetchone()
    return dict(row) if row else None


# ---------------- EXISTING BASIC TESTS ----------------

def test_home_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_registration(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"Open an Account" in response.data


def test_register_and_login(client):
    response = client.get("/register")
    assert response.status_code == 200

    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/register",
        data={
            "csrf_token": token,
            "name": "Test User",
            "username": "testuser",
            "password": "testpassword123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Available Balance" in response.data

    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/logout",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200

    response = client.get("/login")
    assert response.status_code == 200

    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/login",
        data={
            "csrf_token": token,
            "username": "testuser",
            "password": "testpassword123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Available Balance" in response.data


# ---------------- HEALTH CHECK TEST ----------------

def test_health_check_endpoint(client):
    """Tests the container health check endpoint returns 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "healthy"


# ---------------- 14 TRANSFER SCENARIOS ----------------

def test_scenario_01_successful_transfer(client):
    """Scenario 1: Standard valid transfer between two registered users."""
    sender, csrf = create_and_login_user(client, "alice", "Alice")
    receiver = create_recipient_user("bob", "Bob", "RB-2001", 5000.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "500.00",
            "description": "Payment for lunch",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    updated_sender = get_user_by_account(sender["account_number"])
    updated_receiver = get_user_by_account(receiver["account_number"])

    assert updated_sender["balance"] == 9500.00
    assert updated_receiver["balance"] == 5500.00

    # Verify transaction table
    db = banking_app.get_db()
    txn = db.execute("SELECT * FROM transactions WHERE sender_id = ?", (sender["id"],)).fetchone()
    assert txn is not None
    assert txn["amount"] == 500.00
    assert txn["description"] == "Payment for lunch"


def test_scenario_02_transfer_to_preseeded_demo_account(client):
    """Scenario 2: Successful transfer to pre-seeded demo user (DEMO-1001)."""
    sender, csrf = create_and_login_user(client, "charlie", "Charlie")

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": "DEMO-1001",
            "amount": "250.00",
            "description": "Demo funding",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    updated_sender = get_user_by_account(sender["account_number"])
    updated_demo = get_user_by_account("DEMO-1001")

    assert updated_sender["balance"] == 9750.00
    assert updated_demo["balance"] == 10250.00


def test_scenario_03_minimum_boundary_amount(client):
    """Scenario 3: Lower boundary amount transfer of exactly ₹0.01."""
    sender, csrf = create_and_login_user(client, "david", "David")
    receiver = create_recipient_user("eric", "Eric", "RB-2003", 100.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "0.01",
            "description": "Micro transfer",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    updated_sender = get_user_by_account(sender["account_number"])
    updated_receiver = get_user_by_account(receiver["account_number"])

    assert updated_sender["balance"] == 9999.99
    assert updated_receiver["balance"] == 100.01


def test_scenario_04_maximum_boundary_amount(client):
    """Scenario 4: Upper boundary amount transfer of exactly ₹100,000.00."""
    sender, csrf = create_and_login_user(client, "frank", "Frank")
    receiver = create_recipient_user("grace", "Grace", "RB-2004", 1000.00)

    # Fund the sender account to 100,000.00
    db = banking_app.get_db()
    db.execute("UPDATE users SET balance = 100000.00 WHERE id = ?", (sender["id"],))
    db.commit()

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "100000.00",
            "description": "Maximum allowed transfer",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    updated_sender = get_user_by_account(sender["account_number"])
    updated_receiver = get_user_by_account(receiver["account_number"])

    assert updated_sender["balance"] == 0.00
    assert updated_receiver["balance"] == 101000.00


def test_scenario_05_exact_full_balance_depletion(client):
    """Scenario 5: Transfer exact balance leaving sender with exactly ₹0.00."""
    sender, csrf = create_and_login_user(client, "helen", "Helen")
    receiver = create_recipient_user("ivan", "Ivan", "RB-2005", 500.00)

    # Sender initial balance is 10000.00. Transfer all 10000.00.
    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "10000.00",
            "description": "Closing transfer",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    updated_sender = get_user_by_account(sender["account_number"])
    updated_receiver = get_user_by_account(receiver["account_number"])

    assert updated_sender["balance"] == 0.00
    assert updated_receiver["balance"] == 10500.00


def test_scenario_06_transfer_with_custom_description(client):
    """Scenario 6: Transfer with custom description stored accurately."""
    sender, csrf = create_and_login_user(client, "judy", "Judy")
    receiver = create_recipient_user("kevin", "Kevin", "RB-2006", 500.00)

    custom_note = "Seeds and fertilizer supply purchase #42"
    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "1200.50",
            "description": custom_note,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    db = banking_app.get_db()
    txn = db.execute("SELECT * FROM transactions WHERE sender_id = ?", (sender["id"],)).fetchone()
    assert txn["description"] == custom_note


def test_scenario_07_transfer_default_description_when_empty(client):
    """Scenario 7: Default description ('Money transfer') used when field is blank."""
    sender, csrf = create_and_login_user(client, "leo", "Leo")
    receiver = create_recipient_user("maria", "Maria", "RB-2007", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "300.00",
            "description": "   ",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Simulated transfer completed successfully!" in response.data

    db = banking_app.get_db()
    txn = db.execute("SELECT * FROM transactions WHERE sender_id = ?", (sender["id"],)).fetchone()
    assert txn["description"] == "Money transfer"


def test_scenario_08_description_exceeds_max_length(client):
    """Scenario 8: Description exceeding 100 characters is rejected."""
    sender, csrf = create_and_login_user(client, "nina", "Nina")
    receiver = create_recipient_user("oscar", "Oscar", "RB-2008", 500.00)

    oversized_description = "A" * 101

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "200.00",
            "description": oversized_description,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Description must be 100 characters or fewer." in response.data

    # Balances must remain unchanged
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00
    assert get_user_by_account(receiver["account_number"])["balance"] == 500.00


def test_scenario_09_invalid_non_numeric_amount(client):
    """Scenario 9: Non-numeric transfer amount is rejected."""
    sender, csrf = create_and_login_user(client, "paul", "Paul")
    receiver = create_recipient_user("quinn", "Quinn", "RB-2009", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "five-hundred",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid amount." in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


def test_scenario_10_empty_amount(client):
    """Scenario 10: Empty amount string is rejected."""
    sender, csrf = create_and_login_user(client, "rita", "Rita")
    receiver = create_recipient_user("sam", "Sam", "RB-2010", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid amount." in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


def test_scenario_11_zero_amount(client):
    """Scenario 11: Zero amount (₹0.00) is rejected by boundary check."""
    sender, csrf = create_and_login_user(client, "tina", "Tina")
    receiver = create_recipient_user("uma", "Uma", "RB-2011", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "0.00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transfer amount must be between" in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


def test_scenario_12_negative_amount(client):
    """Scenario 12: Negative amount (-₹50.00) is rejected."""
    sender, csrf = create_and_login_user(client, "victor", "Victor")
    receiver = create_recipient_user("wendy", "Wendy", "RB-2012", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "-50.00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transfer amount must be between" in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


def test_scenario_13_exceeding_maximum_limit(client):
    """Scenario 13: Amount exceeding ₹100,000.00 (e.g. ₹100,000.01) is rejected."""
    sender, csrf = create_and_login_user(client, "xavier", "Xavier")
    receiver = create_recipient_user("yara", "Yara", "RB-2013", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "100000.01",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Transfer amount must be between" in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


def test_scenario_14_self_transfer_rejected(client):
    """Scenario 14: Transferring to own account number is rejected."""
    sender, csrf = create_and_login_user(client, "zack", "Zack")

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": sender["account_number"],
            "amount": "500.00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"You cannot transfer money to your own account." in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


# ---------------- ADDITIONAL ROBUSTNESS TESTS ----------------

def test_transfer_recipient_not_found(client):
    """Rejects transfer when target account number does not exist."""
    sender, csrf = create_and_login_user(client, "user_a", "User A")

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": "RB-NONEXISTENT",
            "amount": "500.00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Recipient account not found." in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00


def test_transfer_insufficient_balance(client):
    """Rejects transfer when requested amount exceeds sender balance."""
    sender, csrf = create_and_login_user(client, "user_b", "User B")
    receiver = create_recipient_user("user_c", "User C", "RB-2015", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": receiver["account_number"],
            "amount": "10000.01",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Insufficient balance." in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00
    assert get_user_by_account(receiver["account_number"])["balance"] == 500.00


def test_transfer_unauthenticated_rejected(client):
    """Rejects unauthenticated POST request to /transfer."""
    client.get("/register")
    with client.session_transaction() as sess:
        csrf = sess["_csrf_token"]

    response = client.post(
        "/transfer",
        data={
            "csrf_token": csrf,
            "account_number": "DEMO-1001",
            "amount": "100.00",
        },
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_transfer_invalid_csrf_rejected(client):
    """Rejects transfer with an invalid or spoofed CSRF token."""
    sender, _ = create_and_login_user(client, "user_d", "User D")
    receiver = create_recipient_user("user_e", "User E", "RB-2016", 500.00)

    response = client.post(
        "/transfer",
        data={
            "csrf_token": "spoofed-or-invalid-token",
            "account_number": receiver["account_number"],
            "amount": "100.00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Invalid form submission." in response.data
    assert get_user_by_account(sender["account_number"])["balance"] == 10000.00
