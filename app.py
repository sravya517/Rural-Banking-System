import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    g,
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

# ---------------- CONFIGURATION ----------------

BASE_DIR = Path(__file__).resolve().parent

DATABASE = Path(
    os.environ.get("DATABASE_PATH", str(BASE_DIR / "banking.db"))
)

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", secrets.token_hex(32)
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "false").lower() == "true"
)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")


# ---------------- DATABASE ----------------

def get_db():
    if "db" not in g:
        DATABASE.parent.mkdir(parents=True, exist_ok=True)

        g.db = sqlite3.connect(
            str(DATABASE),
            timeout=10,
        )

        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            account_number TEXT NOT NULL UNIQUE,
            balance REAL NOT NULL DEFAULT 10000.00
                CHECK(balance >= 0)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            receiver_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL CHECK(amount > 0),
            description TEXT NOT NULL DEFAULT 'Money transfer',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    demo_accounts = [
        ("Demo Customer One", "demo1", "DEMO-1001"),
        ("Demo Customer Two", "demo2", "DEMO-1002"),
    ]

    for name, username, account_number in demo_accounts:
        db.execute(
            """
            INSERT OR IGNORE INTO users
            (name, username, password, account_number, balance)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                username,
                generate_password_hash(secrets.token_urlsafe(24)),
                account_number,
                10000.00,
            ),
        )

    db.commit()


# ---------------- CSRF PROTECTION ----------------

def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)

    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def prepare_request():
    init_db()

    # Create a token for new sessions, including login-page visitors.
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)


@app.before_request
def protect_forms():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")

        if not expected or not secrets.compare_digest(
            submitted, expected
        ):
            flash(
                "Invalid form submission. Please try again.",
                "error",
            )
            return redirect(url_for("login"))


# ---------------- LOGIN PROTECTION ----------------

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Administrator login required.", "error")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


# ---------------- HEALTH CHECK ----------------

@app.route("/health")
def health():
    try:
        get_db().execute("SELECT 1")
        return {"status": "healthy"}, 200
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}, 500


# ---------------- HOME ----------------

@app.route("/")
def index():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ---------------- USER REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not username or not password:
            flash("Please fill in every field.", "error")
            return render_template("register.html")

        if len(name) > 80 or len(username) > 30:
            flash("Name or username is too long.", "error")
            return render_template("register.html")

        if not username.replace("_", "").isalnum():
            flash(
                "Use only letters, numbers, and underscores "
                "in your username.",
                "error",
            )
            return render_template("register.html")

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "error",
            )
            return render_template("register.html")

        db = get_db()
        account_number = "RB" + secrets.token_hex(5).upper()

        try:
            cursor = db.execute(
                """
                INSERT INTO users
                (name, username, password, account_number, balance)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    username,
                    generate_password_hash(password),
                    account_number,
                    10000.00,
                ),
            )

            db.commit()

        except sqlite3.IntegrityError:
            flash("That username is already taken.", "error")
            return render_template("register.html")

        session.clear()
        session["user_id"] = cursor.lastrowid
        session["_csrf_token"] = secrets.token_urlsafe(32)

        flash("Account created successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


# ---------------- COMBINED LOGIN PAGE ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    # Both user and admin login forms are displayed on login.html.
    # The form's action determines which login function is called.
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["_csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


# ---------------- ADMIN LOGIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if (
            ADMIN_PASSWORD
            and secrets.compare_digest(username, ADMIN_USERNAME)
            and secrets.compare_digest(password, ADMIN_PASSWORD)
        ):
            session.clear()
            session["is_admin"] = True
            session["_csrf_token"] = secrets.token_urlsafe(32)

            flash("Admin login successful.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid administrator credentials.", "error")

    # Reuse the combined login page instead of a separate admin login page.
    return render_template("login.html")


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()

    total_users = db.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_transactions = db.execute(
        "SELECT COUNT(*) FROM transactions"
    ).fetchone()[0]

    total_transferred = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions"
    ).fetchone()[0]

    recent_transactions = db.execute(
        """
        SELECT
            t.*,
            s.name AS sender_name,
            r.name AS receiver_name
        FROM transactions t
        JOIN users s ON t.sender_id = s.id
        JOIN users r ON t.receiver_id = r.id
        ORDER BY t.id DESC
        LIMIT 10
        """
    ).fetchall()

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_transactions=total_transactions,
        total_transferred=total_transferred,
        recent_transactions=recent_transactions,
    )


# ---------------- USER DASHBOARD ----------------

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    transactions = db.execute(
        """
        SELECT
            t.*,
            s.name AS sender_name,
            r.name AS receiver_name
        FROM transactions t
        JOIN users s ON t.sender_id = s.id
        JOIN users r ON t.receiver_id = r.id
        WHERE t.sender_id = ? OR t.receiver_id = ?
        ORDER BY t.id DESC
        LIMIT 5
        """,
        (user["id"], user["id"]),
    ).fetchall()

    return render_template(
        "dashboard.html",
        user=user,
        transactions=transactions,
    )


# ---------------- MONEY TRANSFER ----------------

@app.route("/transfer", methods=["POST"])
@login_required
def transfer():
    receiver_account = (
        request.form.get("account_number", "").strip().upper()
    )

    description = (
        request.form.get("description", "").strip()
        or "Money transfer"
    )

    if len(description) > 100:
        flash("Description must be 100 characters or fewer.", "error")
        return redirect(url_for("dashboard"))

    try:
        amount = round(float(request.form.get("amount", "")), 2)
    except (ValueError, TypeError):
        flash("Enter a valid amount.", "error")
        return redirect(url_for("dashboard"))

    if not 0.01 <= amount <= 100000:
        flash(
            "Transfer amount must be between ₹0.01 and ₹100,000.",
            "error",
        )
        return redirect(url_for("dashboard"))

    db = get_db()

    try:
        db.execute("BEGIN IMMEDIATE")

        sender = db.execute(
            "SELECT * FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()

        receiver = db.execute(
            "SELECT * FROM users WHERE account_number = ?",
            (receiver_account,),
        ).fetchone()

        if sender is None:
            db.rollback()
            session.clear()
            return redirect(url_for("login"))

        if receiver is None:
            db.rollback()
            flash("Recipient account not found.", "error")
            return redirect(url_for("dashboard"))

        if sender["id"] == receiver["id"]:
            db.rollback()
            flash(
                "You cannot transfer money to your own account.",
                "error",
            )
            return redirect(url_for("dashboard"))

        if sender["balance"] < amount:
            db.rollback()
            flash("Insufficient balance.", "error")
            return redirect(url_for("dashboard"))

        db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (amount, sender["id"]),
        )

        db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amount, receiver["id"]),
        )

        db.execute(
            """
            INSERT INTO transactions
            (sender_id, receiver_id, amount, description)
            VALUES (?, ?, ?, ?)
            """,
            (sender["id"], receiver["id"], amount, description),
        )

        db.commit()
        flash("Simulated transfer completed successfully!", "success")

    except sqlite3.Error:
        db.rollback()
        app.logger.exception("Transfer failed")
        flash(
            "Transfer could not be completed. Please try again.",
            "error",
        )

    return redirect(url_for("dashboard"))


# ---------------- TRANSACTION HISTORY ----------------

@app.route("/history")
@login_required
def history():
    db = get_db()
    user_id = session["user_id"]

    transactions = db.execute(
        """
        SELECT
            t.*,
            s.name AS sender_name,
            r.name AS receiver_name
        FROM transactions t
        JOIN users s ON t.sender_id = s.id
        JOIN users r ON t.receiver_id = r.id
        WHERE t.sender_id = ? OR t.receiver_id = ?
        ORDER BY t.id DESC
        """,
        (user_id, user_id),
    ).fetchall()

    return render_template(
        "history.html",
        transactions=transactions,
    )


# ---------------- LOGOUT ----------------

@app.route("/logout", methods=["POST"])
def logout():
    if "user_id" not in session and not session.get("is_admin"):
        return redirect(url_for("login"))

    session.clear()
    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    app.run(debug=False)