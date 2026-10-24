
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
        yield client


def test_home_redirects_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_registration(client):
    response = client.get("/register")

    assert response.status_code == 200
    assert b"Open an Account" in response.data


def test_register_and_login(client):
    # Open the registration page and obtain the CSRF token.
    response = client.get("/register")

    assert response.status_code == 200

    with client.session_transaction() as session:
        token = session["_csrf_token"]

    # Register a test user.
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

    # Log out the test user.
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/logout",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200

    # Open the login page and obtain a fresh CSRF token.
    response = client.get("/login")

    assert response.status_code == 200

    with client.session_transaction() as session:
        token = session["_csrf_token"]

    # Log in with the registered credentials.
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
