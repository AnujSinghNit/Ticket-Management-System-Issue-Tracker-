"""
TrackIT – Ticket Management System (Issue Tracker)
===================================================
A full-stack Flask application for managing support tickets, tracking issues,
assigning tasks, and resolving problems efficiently.

Tech Stack: Python Flask · SQLite · Jinja2 · HTML/CSS/JS
"""

import sqlite3
import os
import math
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "trackit-secret-key-2026-change-in-production"
app.config["DATABASE"] = os.path.join(app.root_path, "database.db")

# Pagination settings
TICKETS_PER_PAGE = 8


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open a new database connection if there isn't one for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row  # Return rows as dict-like objects
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and seed data if the database doesn't exist yet."""
    db_path = app.config["DATABASE"]
    fresh = not os.path.exists(db_path)

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    # ── Create Tables ─────────────────────────────────────────────────────
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            password    TEXT    NOT NULL,
            full_name   TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'user',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL,
            priority    TEXT    NOT NULL DEFAULT 'Medium',
            status      TEXT    NOT NULL DEFAULT 'Open',
            assigned_to TEXT,
            created_by  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)

    # ── Seed Data (only on first run) ─────────────────────────────────────
    if fresh:
        # Default users
        users = [
            ("admin", generate_password_hash("admin"), "Admin User", "admin"),
            ("john",  generate_password_hash("john123"), "John Smith", "developer"),
            ("sarah", generate_password_hash("sarah123"), "Sarah Connor", "support"),
            ("mike",  generate_password_hash("mike123"), "Mike Johnson", "developer"),
            ("lisa",  generate_password_hash("lisa123"), "Lisa Wong", "tester"),
        ]
        db.executemany(
            "INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)",
            users,
        )

        # Sample realistic tickets
        now = datetime.utcnow()
        tickets = [
            (
                "Login Page Returns 500 Error on Invalid Credentials",
                "Users report a 500 Internal Server Error when entering incorrect "
                "credentials on the login page. The error occurs intermittently and "
                "affects approximately 30% of login attempts. Stack trace points to "
                "an unhandled exception in the authentication middleware.",
                "High", "Open", "John Smith", "Admin User",
                (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "REST API Timeout on /api/v2/reports Endpoint",
                "The /api/v2/reports endpoint is timing out after 30 seconds when "
                "generating monthly summary reports. Performance profiling shows a "
                "slow SQL query joining the transactions and audit_log tables. "
                "Affects all users requesting reports for periods > 90 days.",
                "High", "In Progress", "Mike Johnson", "Sarah Connor",
                (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "Database Connection Pool Exhaustion Under Load",
                "During peak traffic (>500 concurrent users), the PostgreSQL connection "
                "pool is being exhausted, causing DatabaseError exceptions. Current pool "
                "size is set to 20 connections. Need to investigate connection leaks and "
                "increase pool size or implement connection recycling.",
                "High", "Open", "Mike Johnson", "John Smith",
                (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "Dashboard Chart Tooltip Overlaps on Mobile Devices",
                "On screens smaller than 768px, the bar chart tooltips on the analytics "
                "dashboard overflow outside the viewport. The tooltip positioning logic "
                "doesn't account for edge cases near screen boundaries. Reproducible on "
                "iOS Safari and Chrome for Android.",
                "Medium", "In Progress", "Lisa Wong", "Admin User",
                (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "Payment Gateway Returns Duplicate Transaction IDs",
                "The Stripe integration is intermittently returning duplicate transaction "
                "IDs for separate payment attempts. This causes reconciliation failures "
                "in our accounting module. Issue started after upgrading stripe-python "
                "from v5.4 to v6.0. Rollback may be required.",
                "High", "Open", "Sarah Connor", "Mike Johnson",
                (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "User Profile Avatar Upload Fails for PNG Files > 2 MB",
                "File upload for user avatars silently fails when PNG files exceed 2 MB. "
                "The server returns 200 OK but the avatar is not updated. JPEG files of "
                "the same size upload successfully. Likely a MIME-type validation issue "
                "in the file processing pipeline.",
                "Low", "Open", "John Smith", "Lisa Wong",
                (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "Notification Emails Sent in Wrong Timezone",
                "Scheduled notification emails display timestamps in UTC instead of the "
                "user's configured timezone. This affects daily digest emails and ticket "
                "update notifications. Root cause appears to be the email template not "
                "converting datetime objects using the user's TZ preference.",
                "Medium", "Resolved", "Sarah Connor", "Admin User",
                (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
            (
                "CSV Export Missing Header Row for Custom Fields",
                "When exporting ticket data to CSV, custom field columns are present but "
                "the header row only includes default fields. This makes the exported "
                "data difficult to parse programmatically. Issue affects all export "
                "formats (CSV, XLSX).",
                "Low", "Closed", "Lisa Wong", "Sarah Connor",
                (now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        ]
        db.executemany(
            """INSERT INTO tickets
               (title, description, priority, status, assigned_to, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[6]) for t in tickets],
        )

    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Authentication Decorator
# ---------------------------------------------------------------------------
def login_required(f):
    """Redirect to login page if user is not authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Context Processor – make current user available in all templates
# ---------------------------------------------------------------------------
@app.context_processor
def inject_user():
    """Inject current user info into every template context."""
    user = None
    if "user_id" in session:
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
    return dict(current_user=user)


# ---------------------------------------------------------------------------
# Jinja Filters
# ---------------------------------------------------------------------------
@app.template_filter("humandate")
def humandate_filter(value):
    """Convert a datetime string to a human-readable format."""
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%b %d, %Y · %I:%M %p")
    except (ValueError, TypeError):
        return value


@app.template_filter("shortdate")
def shortdate_filter(value):
    """Convert a datetime string to a short date format."""
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return value


@app.template_filter("timeago")
def timeago_filter(value):
    """Return a 'time ago' string (e.g. '2 hours ago')."""
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        diff = datetime.utcnow() - dt
        seconds = diff.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds // 60)
            return f"{mins} min{'s' if mins != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds // 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return value


# ---------------------------------------------------------------------------
# Routes – Authentication
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter both username and password.", "error")
            return render_template("login.html")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Handle new user registration."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")

        if not username or not password or not full_name:
            flash("Please fill in all fields.", "error")
            return render_template("signup.html")

        db = get_db()
        existing_user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if existing_user:
            flash("Username already exists. Please choose a different one.", "error")
        else:
            db.execute(
                "INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), full_name)
            )
            db.commit()
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes – Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    """Render the main dashboard with ticket statistics."""
    db = get_db()

    # Aggregate counts
    total    = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    open_c   = db.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Open'").fetchone()[0]
    progress = db.execute("SELECT COUNT(*) FROM tickets WHERE status = 'In Progress'").fetchone()[0]
    resolved = db.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Resolved'").fetchone()[0]
    closed   = db.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Closed'").fetchone()[0]
    high     = db.execute("SELECT COUNT(*) FROM tickets WHERE priority = 'High'").fetchone()[0]

    # Recent tickets (latest 5)
    recent = db.execute(
        "SELECT * FROM tickets ORDER BY created_at DESC LIMIT 5"
    ).fetchall()

    return render_template(
        "dashboard.html",
        total=total, open_c=open_c, progress=progress,
        resolved=resolved, closed=closed, high=high,
        recent=recent,
    )


# ---------------------------------------------------------------------------
# Routes – Tickets CRUD
# ---------------------------------------------------------------------------
@app.route("/tickets")
@login_required
def tickets():
    """List all tickets with search, filter and pagination."""
    db = get_db()

    # Query parameters
    search   = request.args.get("search", "").strip()
    status   = request.args.get("status", "")
    priority = request.args.get("priority", "")
    page     = request.args.get("page", 1, type=int)

    # Build dynamic query
    query  = "SELECT * FROM tickets WHERE 1=1"
    params = []

    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if status:
        query += " AND status = ?"
        params.append(status)
    if priority:
        query += " AND priority = ?"
        params.append(priority)

    # Count for pagination
    count_query = query.replace("SELECT *", "SELECT COUNT(*)", 1)
    total = db.execute(count_query, params).fetchone()[0]
    total_pages = max(1, math.ceil(total / TICKETS_PER_PAGE))
    page = max(1, min(page, total_pages))

    # Fetch page
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([TICKETS_PER_PAGE, (page - 1) * TICKETS_PER_PAGE])
    ticket_list = db.execute(query, params).fetchall()

    return render_template(
        "tickets.html",
        tickets=ticket_list,
        search=search,
        status=status,
        priority=priority,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/tickets/create", methods=["GET", "POST"])
@login_required
def create_ticket():
    """Create a new ticket."""
    db = get_db()

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority    = request.form.get("priority", "Medium")
        status      = request.form.get("status", "Open")
        assigned_to = request.form.get("assigned_to", "").strip()

        # Validation
        if not title:
            flash("Title is required.", "error")
            return render_template("create_ticket.html", users=_get_user_names())
        if not description:
            flash("Description is required.", "error")
            return render_template("create_ticket.html", users=_get_user_names())

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """INSERT INTO tickets (title, description, priority, status, assigned_to, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, description, priority, status, assigned_to,
             session.get("full_name", "Unknown"), now, now),
        )
        db.commit()
        flash("Ticket created successfully!", "success")
        return redirect(url_for("tickets"))

    return render_template("create_ticket.html", users=_get_user_names())


@app.route("/tickets/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    """View a single ticket's details."""
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("tickets"))
    return render_template("ticket_detail.html", ticket=ticket)


@app.route("/tickets/<int:ticket_id>/edit", methods=["GET", "POST"])
@login_required
def edit_ticket(ticket_id):
    """Edit an existing ticket."""
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("tickets"))

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority    = request.form.get("priority", "Medium")
        status      = request.form.get("status", "Open")
        assigned_to = request.form.get("assigned_to", "").strip()

        if not title:
            flash("Title is required.", "error")
            return render_template("edit_ticket.html", ticket=ticket, users=_get_user_names())
        if not description:
            flash("Description is required.", "error")
            return render_template("edit_ticket.html", ticket=ticket, users=_get_user_names())

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """UPDATE tickets
               SET title=?, description=?, priority=?, status=?, assigned_to=?, updated_at=?
               WHERE id=?""",
            (title, description, priority, status, assigned_to, now, ticket_id),
        )
        db.commit()
        flash("Ticket updated successfully!", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    return render_template("edit_ticket.html", ticket=ticket, users=_get_user_names())


@app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
@login_required
def delete_ticket(ticket_id):
    """Delete a ticket."""
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("tickets"))

    db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    db.commit()
    flash("Ticket deleted successfully.", "success")
    return redirect(url_for("tickets"))


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def _get_user_names():
    """Return a list of full_name values for the assign-to dropdown."""
    db = get_db()
    rows = db.execute("SELECT full_name FROM users ORDER BY full_name").fetchall()
    return [r["full_name"] for r in rows]


# ---------------------------------------------------------------------------
# Initialise DB (always, so it's ready whether run directly or imported)
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# Run Flask dev server (only when executed directly: python app.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
