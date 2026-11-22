"""
ZenFlow - Smart Wellness Tracker
A simple Flask + SQLite website to track water, sleep, activity and habits.

Run:  python app.py   then open http://127.0.0.1:5000
"""

import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "zenflow-secret-key-change-me"   # used to sign the session cookie

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

DEFAULT_WATER_GOAL = 2500      # ml
DEFAULT_SLEEP_GOAL = 8         # hours
ACTIVITY_GOAL_MINUTES = 30     # daily activity target used for overall progress

ACTIVITY_TYPES = ["Walking", "Running", "Cycling", "Gym", "Yoga", "Swimming", "Other"]

SUGGESTED_HABITS = [
    "Read for 20 minutes",
    "Exercise daily",
    "Wake up early",
    "Avoid excessive screen time",
    "Meditate",
    "Drink enough water",
    "Sleep on time",
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open one SQLite connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row          # access columns by name: row["name"]
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    """Close the database connection at the end of every request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables if they do not exist yet."""
    db = sqlite3.connect(DATABASE)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS water_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount_ml INTEGER NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS sleep_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bedtime TEXT NOT NULL,
        wakeup_time TEXT NOT NULL,
        duration REAL NOT NULL,
        date TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS activity_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        activity_type TEXT NOT NULL,
        duration INTEGER NOT NULL,
        distance REAL,
        steps INTEGER,
        date TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        habit_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS habit_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        completion_date TEXT NOT NULL,
        completed INTEGER NOT NULL DEFAULT 1,
        UNIQUE (habit_id, completion_date),
        FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS user_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        daily_water_goal INTEGER NOT NULL DEFAULT 2500,
        daily_sleep_goal REAL NOT NULL DEFAULT 8,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------------------
def login_required(view):
    """Decorator: send the visitor to the login page if not logged in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def today_str():
    """Today's date as text, e.g. '2026-11-21'."""
    return date.today().isoformat()


def last_7_days():
    """List of the last 7 dates (oldest first) as 'YYYY-MM-DD' text."""
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]


def day_label(date_text):
    """'2026-11-21' -> 'Sat 21' (used as chart labels)."""
    return datetime.strptime(date_text, "%Y-%m-%d").strftime("%a %d")


def valid_date(text):
    """Return True if text is a real date in YYYY-MM-DD format."""
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def safe_next(default):
    """Go back to the page given in the form's 'next' field (only pages on this site)."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


def percent(value, goal):
    """Percentage of goal reached, capped at 100."""
    if not goal:
        return 0
    return min(100, round(value * 100 / goal))


def get_goals(user_id):
    """Return the user's goals; create default goals if missing."""
    db = get_db()
    goals = db.execute("SELECT * FROM user_goals WHERE user_id = ?", (user_id,)).fetchone()
    if goals is None:
        db.execute("INSERT INTO user_goals (user_id, daily_water_goal, daily_sleep_goal) VALUES (?, ?, ?)",
                   (user_id, DEFAULT_WATER_GOAL, DEFAULT_SLEEP_GOAL))
        db.commit()
        goals = db.execute("SELECT * FROM user_goals WHERE user_id = ?", (user_id,)).fetchone()
    return goals


def calculate_sleep_duration(bedtime, wakeup_time):
    """
    Work out hours slept from two 'HH:MM' times.
    If wake-up time is earlier than bedtime, the person slept past midnight,
    so we add 24 hours.  Example: 23:00 -> 07:00 = 8.0 hours.
    """
    bed = datetime.strptime(bedtime, "%H:%M")
    wake = datetime.strptime(wakeup_time, "%H:%M")
    if wake <= bed:
        wake = wake + timedelta(days=1)
    hours = (wake - bed).total_seconds() / 3600
    return round(hours, 2)


def format_hours(hours):
    """7.5 -> '7h 30m'."""
    hours = hours or 0
    h = int(hours)
    m = round((hours - h) * 60)
    if m == 60:
        h, m = h + 1, 0
    return f"{h}h {m}m"


app.jinja_env.filters["hours"] = format_hours


def to_12h(time_text):
    """'23:00' -> '11:00 PM'."""
    try:
        return datetime.strptime(time_text, "%H:%M").strftime("%I:%M %p")
    except (ValueError, TypeError):
        return time_text


app.jinja_env.filters["time12"] = to_12h


def nice_date(date_text):
    """'2026-11-21' -> '21 Nov 2026'."""
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return date_text


app.jinja_env.filters["nicedate"] = nice_date


# ---------------------------------------------------------------------------
# Functions that read the user's data (used by dashboard, modules, analytics)
# ---------------------------------------------------------------------------
def water_total(user_id, day):
    row = get_db().execute(
        "SELECT COALESCE(SUM(amount_ml), 0) AS total FROM water_records WHERE user_id = ? AND date = ?",
        (user_id, day)).fetchone()
    return row["total"]


def sleep_total(user_id, day):
    row = get_db().execute(
        "SELECT COALESCE(SUM(duration), 0) AS total FROM sleep_records WHERE user_id = ? AND date = ?",
        (user_id, day)).fetchone()
    return round(row["total"], 2)


def activity_total(user_id, day):
    row = get_db().execute(
        "SELECT COALESCE(SUM(duration), 0) AS total FROM activity_records WHERE user_id = ? AND date = ?",
        (user_id, day)).fetchone()
    return row["total"]


def habit_counts(user_id, day):
    """Return (total_habits, completed_on_that_day)."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS c FROM habits WHERE user_id = ?", (user_id,)).fetchone()["c"]
    done = db.execute(
        "SELECT COUNT(*) AS c FROM habit_completions WHERE user_id = ? AND completion_date = ? AND completed = 1",
        (user_id, day)).fetchone()["c"]
    return total, done


def weekly_data(user_id):
    """Collect 7-day data for all charts from the database."""
    days = last_7_days()
    total_habits = habit_counts(user_id, today_str())[0]
    data = {
        "labels": [day_label(d) for d in days],
        "water": [water_total(user_id, d) for d in days],
        "sleep": [sleep_total(user_id, d) for d in days],
        "activity": [activity_total(user_id, d) for d in days],
        "habits_done": [habit_counts(user_id, d)[1] for d in days],
    }
    data["habits_percent"] = [percent(done, total_habits) for done in data["habits_done"]]
    goals = get_goals(user_id)
    data["water_goal"] = goals["daily_water_goal"]
    data["sleep_goal"] = goals["daily_sleep_goal"]
    data["total_habits"] = total_habits
    return data


def calculate_streaks(habit_id):
    """
    Current streak  = how many days in a row (ending today or yesterday) the habit was completed.
    Longest streak  = the longest run of consecutive completed days ever.
    """
    rows = get_db().execute(
        "SELECT completion_date FROM habit_completions WHERE habit_id = ? AND completed = 1 ORDER BY completion_date",
        (habit_id,)).fetchall()
    dates = [datetime.strptime(r["completion_date"], "%Y-%m-%d").date() for r in rows]

    # Longest streak: walk through the sorted dates
    longest, run = 0, 0
    previous = None
    for d in dates:
        if previous is not None and d - previous == timedelta(days=1):
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        previous = d

    # Current streak: count backwards from today (or yesterday if today not done yet)
    done_set = set(dates)
    day = date.today()
    if day not in done_set:
        day = day - timedelta(days=1)
    current = 0
    while day in done_set:
        current += 1
        day = day - timedelta(days=1)

    return current, longest


# ---------------------------------------------------------------------------
# Make the logged-in user's name and today's date available in all templates
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    return {
        "current_user_name": session.get("user_name"),
        "today_text": date.today().strftime("%A, %d %B %Y"),
    }


# ---------------------------------------------------------------------------
# Public pages: home, register, login, logout
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        # Basic validation
        if not name or not email or not password:
            flash("All fields are required.", "danger")
        elif "@" not in email or "." not in email:
            flash("Please enter a valid email address.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            db = get_db()
            existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                flash("An account with this email already exists.", "danger")
            else:
                # Never store the plain password - store a secure hash instead
                hashed = generate_password_hash(password)
                cursor = db.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                                    (name, email, hashed))
                db.execute("INSERT INTO user_goals (user_id, daily_water_goal, daily_sleep_goal) VALUES (?, ?, ?)",
                           (cursor.lastrowid, DEFAULT_WATER_GOAL, DEFAULT_SLEEP_GOAL))
                db.commit()
                flash("Account created successfully! Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html", name=name, email=email)

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "danger")
            return render_template("login.html", email=email)

        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html", email=email)

        # Save who is logged in inside the session cookie
        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    today = today_str()
    db = get_db()
    goals = get_goals(user_id)

    water = water_total(user_id, today)
    water_goal = goals["daily_water_goal"]
    sleep = sleep_total(user_id, today)
    sleep_goal = goals["daily_sleep_goal"]
    activity = activity_total(user_id, today)
    total_habits, done_habits = habit_counts(user_id, today)

    water_pct = percent(water, water_goal)
    sleep_pct = percent(sleep, sleep_goal)
    activity_pct = percent(activity, ACTIVITY_GOAL_MINUTES)
    habit_pct = percent(done_habits, total_habits)
    # Overall progress = average of the four module percentages
    overall = round((water_pct + sleep_pct + activity_pct + habit_pct) / 4)

    today_sleep = db.execute(
        "SELECT * FROM sleep_records WHERE user_id = ? AND date = ? ORDER BY id DESC", (user_id, today)).fetchall()
    recent_activities = db.execute(
        "SELECT * FROM activity_records WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 5", (user_id,)).fetchall()
    habits = db.execute("""
        SELECT h.id, h.habit_name,
               COALESCE((SELECT completed FROM habit_completions c
                         WHERE c.habit_id = h.id AND c.completion_date = ?), 0) AS done
        FROM habits h WHERE h.user_id = ? ORDER BY h.id
    """, (today, user_id)).fetchall()

    return render_template(
        "dashboard.html",
        water=water, water_goal=water_goal, water_remaining=max(0, water_goal - water), water_pct=water_pct,
        sleep=sleep, sleep_goal=sleep_goal, sleep_pct=sleep_pct,
        activity=activity, activity_goal=ACTIVITY_GOAL_MINUTES, activity_pct=activity_pct,
        total_habits=total_habits, done_habits=done_habits, habit_pct=habit_pct,
        overall=overall, today_sleep=today_sleep, recent_activities=recent_activities,
        habits=habits, chart_data=weekly_data(user_id),
    )


# ---------------------------------------------------------------------------
# Module 1: Water tracker
# ---------------------------------------------------------------------------
@app.route("/water")
@login_required
def water():
    user_id = session["user_id"]
    today = today_str()
    db = get_db()
    goal = get_goals(user_id)["daily_water_goal"]
    total = water_total(user_id, today)

    today_records = db.execute(
        "SELECT * FROM water_records WHERE user_id = ? AND date = ? ORDER BY time DESC, id DESC",
        (user_id, today)).fetchall()
    data = weekly_data(user_id)
    week_history = [
        {"date": d, "total": data["water"][i], "pct": percent(data["water"][i], goal)}
        for i, d in enumerate(last_7_days())
    ][::-1]

    return render_template(
        "water.html", goal=goal, total=total, remaining=max(0, goal - total),
        pct=percent(total, goal), today_records=today_records,
        week_history=week_history, chart_data=data,
    )


@app.route("/water/add", methods=["POST"])
@login_required
def add_water():
    amount_text = request.form.get("amount", "").strip()
    try:
        amount = int(amount_text)
    except ValueError:
        flash("Please enter a valid water amount in ml.", "danger")
        return redirect(url_for("water"))

    if amount <= 0:
        flash("Water amount must be greater than 0 ml.", "danger")
    elif amount > 5000:
        flash("That is too much for one entry. Maximum is 5000 ml.", "danger")
    else:
        now = datetime.now()
        db = get_db()
        db.execute("INSERT INTO water_records (user_id, amount_ml, date, time) VALUES (?, ?, ?, ?)",
                   (session["user_id"], amount, now.strftime("%Y-%m-%d"), now.strftime("%H:%M")))
        db.commit()
        flash(f"Added {amount} ml of water.", "success")
    return redirect(safe_next(url_for("water")))


@app.route("/water/goal", methods=["POST"])
@login_required
def set_water_goal():
    try:
        goal = int(request.form.get("goal", ""))
    except ValueError:
        flash("Please enter a valid goal in ml.", "danger")
        return redirect(url_for("water"))

    if goal < 500 or goal > 10000:
        flash("Daily water goal must be between 500 and 10000 ml.", "danger")
    else:
        get_goals(session["user_id"])  # make sure a goals row exists
        db = get_db()
        db.execute("UPDATE user_goals SET daily_water_goal = ? WHERE user_id = ?", (goal, session["user_id"]))
        db.commit()
        flash(f"Daily water goal updated to {goal} ml.", "success")
    return redirect(url_for("water"))


@app.route("/water/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_water(record_id):
    db = get_db()
    # user_id in the WHERE clause makes sure users can only delete their own records
    result = db.execute("DELETE FROM water_records WHERE id = ? AND user_id = ?", (record_id, session["user_id"]))
    db.commit()
    if result.rowcount:
        flash("Water record deleted.", "success")
    else:
        flash("Record not found.", "danger")
    return redirect(url_for("water"))


# ---------------------------------------------------------------------------
# Module 2: Sleep tracker
# ---------------------------------------------------------------------------
@app.route("/sleep")
@login_required
def sleep():
    user_id = session["user_id"]
    db = get_db()
    goal = get_goals(user_id)["daily_sleep_goal"]
    records = db.execute(
        "SELECT * FROM sleep_records WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 30", (user_id,)).fetchall()
    avg_row = db.execute(
        "SELECT AVG(day_total) AS avg FROM (SELECT SUM(duration) AS day_total FROM sleep_records "
        "WHERE user_id = ? GROUP BY date)", (user_id,)).fetchone()
    average = round(avg_row["avg"] or 0, 2)

    data = weekly_data(user_id)
    week_values = [v for v in data["sleep"] if v > 0]
    week_avg = round(sum(week_values) / len(week_values), 2) if week_values else 0
    data["sleep_avg"] = week_avg
    last = records[0] if records else None

    return render_template("sleep.html", goal=goal, records=records, average=average,
                           week_avg=week_avg, last=last, chart_data=data, today=today_str())


@app.route("/sleep/add", methods=["POST"])
@login_required
def add_sleep():
    bedtime = request.form.get("bedtime", "").strip()
    wakeup = request.form.get("wakeup_time", "").strip()
    day = request.form.get("date", "").strip() or today_str()

    if not bedtime or not wakeup:
        flash("Please enter both bedtime and wake-up time.", "danger")
        return redirect(url_for("sleep"))
    if not valid_date(day):
        flash("Please choose a valid date.", "danger")
        return redirect(url_for("sleep"))
    if day > today_str():
        flash("You cannot add sleep for a future date.", "danger")
        return redirect(url_for("sleep"))
    try:
        duration = calculate_sleep_duration(bedtime, wakeup)
    except ValueError:
        flash("Please enter times in HH:MM format.", "danger")
        return redirect(url_for("sleep"))

    if duration <= 0 or duration > 20:
        flash("Sleep duration looks invalid. Please check the times.", "danger")
        return redirect(url_for("sleep"))

    db = get_db()
    db.execute("INSERT INTO sleep_records (user_id, bedtime, wakeup_time, duration, date) VALUES (?, ?, ?, ?, ?)",
               (session["user_id"], bedtime, wakeup, duration, day))
    db.commit()
    flash(f"Sleep saved: {format_hours(duration)}.", "success")
    return redirect(url_for("sleep"))


@app.route("/sleep/goal", methods=["POST"])
@login_required
def set_sleep_goal():
    try:
        goal = float(request.form.get("goal", ""))
    except ValueError:
        flash("Please enter a valid number of hours.", "danger")
        return redirect(url_for("sleep"))

    if goal < 1 or goal > 16:
        flash("Sleep target must be between 1 and 16 hours.", "danger")
    else:
        get_goals(session["user_id"])
        db = get_db()
        db.execute("UPDATE user_goals SET daily_sleep_goal = ? WHERE user_id = ?", (goal, session["user_id"]))
        db.commit()
        flash(f"Sleep target updated to {goal:g} hours.", "success")
    return redirect(url_for("sleep"))


@app.route("/sleep/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_sleep(record_id):
    db = get_db()
    result = db.execute("DELETE FROM sleep_records WHERE id = ? AND user_id = ?", (record_id, session["user_id"]))
    db.commit()
    flash("Sleep record deleted." if result.rowcount else "Record not found.",
          "success" if result.rowcount else "danger")
    return redirect(url_for("sleep"))


# ---------------------------------------------------------------------------
# Module 3: Activity tracker
# ---------------------------------------------------------------------------
@app.route("/activity")
@login_required
def activity():
    user_id = session["user_id"]
    db = get_db()
    selected = request.args.get("date", "").strip()
    if not valid_date(selected):
        selected = today_str()

    day_records = db.execute(
        "SELECT * FROM activity_records WHERE user_id = ? AND date = ? ORDER BY id DESC",
        (user_id, selected)).fetchall()
    totals = db.execute(
        "SELECT COALESCE(SUM(duration),0) AS minutes, COALESCE(SUM(steps),0) AS steps, "
        "COALESCE(SUM(distance),0) AS distance FROM activity_records WHERE user_id = ? AND date = ?",
        (user_id, selected)).fetchone()
    history = db.execute(
        "SELECT * FROM activity_records WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 30",
        (user_id,)).fetchall()

    week = last_7_days()
    type_summary = db.execute(
        "SELECT activity_type, COUNT(*) AS sessions, SUM(duration) AS minutes FROM activity_records "
        "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY activity_type ORDER BY minutes DESC",
        (user_id, week[0], week[-1])).fetchall()

    data = weekly_data(user_id)
    data["type_labels"] = [r["activity_type"] for r in type_summary]
    data["type_minutes"] = [r["minutes"] for r in type_summary]

    return render_template("activity.html", types=ACTIVITY_TYPES, selected=selected, day_records=day_records,
                           totals=totals, history=history, type_summary=type_summary,
                           chart_data=data, today=today_str())


@app.route("/activity/add", methods=["POST"])
@login_required
def add_activity():
    activity_type = request.form.get("activity_type", "")
    duration_text = request.form.get("duration", "").strip()
    distance_text = request.form.get("distance", "").strip()
    steps_text = request.form.get("steps", "").strip()
    day = request.form.get("date", "").strip() or today_str()

    if activity_type not in ACTIVITY_TYPES:
        flash("Please choose an activity type.", "danger")
        return redirect(url_for("activity"))
    try:
        duration = int(duration_text)
    except ValueError:
        flash("Please enter the duration in whole minutes.", "danger")
        return redirect(url_for("activity"))
    if duration <= 0 or duration > 1440:
        flash("Duration must be between 1 and 1440 minutes.", "danger")
        return redirect(url_for("activity"))
    if not valid_date(day) or day > today_str():
        flash("Please choose a valid date (not in the future).", "danger")
        return redirect(url_for("activity"))

    # Optional fields: empty means "not entered"
    distance = None
    steps = None
    try:
        if distance_text:
            distance = float(distance_text)
            if distance < 0:
                raise ValueError
        if steps_text:
            steps = int(steps_text)
            if steps < 0:
                raise ValueError
    except ValueError:
        flash("Distance and steps must be positive numbers.", "danger")
        return redirect(url_for("activity"))

    db = get_db()
    db.execute("INSERT INTO activity_records (user_id, activity_type, duration, distance, steps, date) "
               "VALUES (?, ?, ?, ?, ?, ?)", (session["user_id"], activity_type, duration, distance, steps, day))
    db.commit()
    flash(f"{activity_type} for {duration} minutes saved.", "success")
    return redirect(url_for("activity", date=day))


@app.route("/activity/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_activity(record_id):
    db = get_db()
    result = db.execute("DELETE FROM activity_records WHERE id = ? AND user_id = ?",
                        (record_id, session["user_id"]))
    db.commit()
    flash("Activity deleted." if result.rowcount else "Record not found.",
          "success" if result.rowcount else "danger")
    return redirect(safe_next(url_for("activity")))


# ---------------------------------------------------------------------------
# Module 4: Habit tracker
# ---------------------------------------------------------------------------
@app.route("/habits")
@login_required
def habits():
    user_id = session["user_id"]
    today = today_str()
    db = get_db()
    rows = db.execute("""
        SELECT h.id, h.habit_name, h.created_at,
               COALESCE((SELECT completed FROM habit_completions c
                         WHERE c.habit_id = h.id AND c.completion_date = ?), 0) AS done
        FROM habits h WHERE h.user_id = ? ORDER BY h.id
    """, (today, user_id)).fetchall()

    habit_list = []
    for row in rows:
        current, longest = calculate_streaks(row["id"])
        habit_list.append({"id": row["id"], "name": row["habit_name"], "done": row["done"],
                           "current": current, "longest": longest})

    total = len(habit_list)
    completed = sum(1 for h in habit_list if h["done"])
    existing = {h["name"].lower() for h in habit_list}
    suggestions = [s for s in SUGGESTED_HABITS if s.lower() not in existing]

    return render_template("habits.html", habits=habit_list, total=total, completed=completed,
                           pending=total - completed, pct=percent(completed, total),
                           suggestions=suggestions, chart_data=weekly_data(user_id))


@app.route("/habits/add", methods=["POST"])
@login_required
def add_habit():
    name = request.form.get("habit_name", "").strip()
    if not name:
        flash("Habit name cannot be empty.", "danger")
    elif len(name) > 60:
        flash("Habit name is too long (max 60 characters).", "danger")
    else:
        db = get_db()
        duplicate = db.execute("SELECT id FROM habits WHERE user_id = ? AND LOWER(habit_name) = LOWER(?)",
                               (session["user_id"], name)).fetchone()
        if duplicate:
            flash("You already have this habit.", "warning")
        else:
            db.execute("INSERT INTO habits (user_id, habit_name, created_at) VALUES (?, ?, ?)",
                       (session["user_id"], name, today_str()))
            db.commit()
            flash(f"Habit '{name}' added.", "success")
    return redirect(url_for("habits"))


@app.route("/habits/toggle/<int:habit_id>", methods=["POST"])
@login_required
def toggle_habit(habit_id):
    """Mark a habit as completed today, or undo it if it was already completed."""
    user_id = session["user_id"]
    today = today_str()
    db = get_db()
    habit = db.execute("SELECT * FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id)).fetchone()
    if habit is None:
        flash("Habit not found.", "danger")
        return redirect(url_for("habits"))

    record = db.execute("SELECT * FROM habit_completions WHERE habit_id = ? AND completion_date = ?",
                        (habit_id, today)).fetchone()
    if record is None:
        db.execute("INSERT INTO habit_completions (habit_id, user_id, completion_date, completed) VALUES (?, ?, ?, 1)",
                   (habit_id, user_id, today))
        flash(f"Great job! '{habit['habit_name']}' completed.", "success")
    else:
        new_value = 0 if record["completed"] else 1
        db.execute("UPDATE habit_completions SET completed = ? WHERE id = ?", (new_value, record["id"]))
        flash(f"'{habit['habit_name']}' " + ("completed." if new_value else "marked as not done."),
              "success" if new_value else "info")
    db.commit()
    return redirect(safe_next(url_for("habits")))


@app.route("/habits/delete/<int:habit_id>", methods=["POST"])
@login_required
def delete_habit(habit_id):
    db = get_db()
    result = db.execute("DELETE FROM habits WHERE id = ? AND user_id = ?", (habit_id, session["user_id"]))
    db.commit()
    flash("Habit deleted." if result.rowcount else "Habit not found.",
          "success" if result.rowcount else "danger")
    return redirect(url_for("habits"))


# ---------------------------------------------------------------------------
# Weekly analytics
# ---------------------------------------------------------------------------
@app.route("/analytics")
@login_required
def analytics():
    user_id = session["user_id"]
    data = weekly_data(user_id)

    water_avg = round(sum(data["water"]) / 7)
    sleep_days = [v for v in data["sleep"] if v > 0]
    sleep_avg = round(sum(sleep_days) / len(sleep_days), 2) if sleep_days else 0
    activity_week = sum(data["activity"])
    possible = data["total_habits"] * 7
    habit_overall = percent(sum(data["habits_done"]), possible)
    data["sleep_avg"] = sleep_avg

    return render_template("analytics.html", chart_data=data, water_avg=water_avg, sleep_avg=sleep_avg,
                           activity_week=activity_week, habit_overall=habit_overall)


# ---------------------------------------------------------------------------
# Profile / settings
# ---------------------------------------------------------------------------
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user_id"]
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if not name or not email:
            flash("Name and email are required.", "danger")
        elif "@" not in email or "." not in email:
            flash("Please enter a valid email address.", "danger")
        elif db.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone():
            flash("That email is already used by another account.", "danger")
        else:
            db.execute("UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, user_id))
            db.commit()
            session["user_name"] = name
            flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    goals = get_goals(user_id)
    stats = {
        "water": db.execute("SELECT COUNT(*) c FROM water_records WHERE user_id = ?", (user_id,)).fetchone()["c"],
        "sleep": db.execute("SELECT COUNT(*) c FROM sleep_records WHERE user_id = ?", (user_id,)).fetchone()["c"],
        "activity": db.execute("SELECT COUNT(*) c FROM activity_records WHERE user_id = ?", (user_id,)).fetchone()["c"],
        "habits": db.execute("SELECT COUNT(*) c FROM habits WHERE user_id = ?", (user_id,)).fetchone()["c"],
    }
    return render_template("profile.html", user=user, goals=goals, stats=stats)


@app.route("/profile/goals", methods=["POST"])
@login_required
def update_goals():
    try:
        water_goal = int(request.form.get("water_goal", ""))
        sleep_goal = float(request.form.get("sleep_goal", ""))
    except ValueError:
        flash("Please enter valid numbers for your goals.", "danger")
        return redirect(url_for("profile"))

    if not (500 <= water_goal <= 10000):
        flash("Water goal must be between 500 and 10000 ml.", "danger")
    elif not (1 <= sleep_goal <= 16):
        flash("Sleep target must be between 1 and 16 hours.", "danger")
    else:
        get_goals(session["user_id"])
        db = get_db()
        db.execute("UPDATE user_goals SET daily_water_goal = ?, daily_sleep_goal = ? WHERE user_id = ?",
                   (water_goal, sleep_goal, session["user_id"]))
        db.commit()
        flash("Goals updated successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if not check_password_hash(user["password"], current):
        flash("Current password is incorrect.", "danger")
    elif len(new) < 6:
        flash("New password must be at least 6 characters.", "danger")
    elif new != confirm:
        flash("New passwords do not match.", "danger")
    else:
        db.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(new), user["id"]))
        db.commit()
        flash("Password changed successfully.", "success")
    return redirect(url_for("profile"))


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


# ---------------------------------------------------------------------------
# Start the app
# ---------------------------------------------------------------------------
init_db()   # creates database.db and tables automatically on first run

if __name__ == "__main__":
    app.run(debug=True)
