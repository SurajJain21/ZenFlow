# ZenFlow – Smart Wellness Tracker

A simple full-stack website, built with **Python (Flask)** and **SQLite**, for tracking daily **water intake, sleep, physical activity and habits**, with weekly charts (Chart.js).

B.Tech college project. Easy to read, easy to run, no paid APIs, no AI/ML.

---

## 1. Technology used

| Part      | Technology                                   |
|-----------|----------------------------------------------|
| Frontend  | HTML5, CSS3, JavaScript, Bootstrap 5         |
| Backend   | Python 3 + Flask                             |
| Database  | SQLite (one file: `database.db`)             |
| Charts    | Chart.js                                     |
| Security  | Werkzeug password hashing (comes with Flask) |

Bootstrap, Bootstrap Icons, Chart.js and the Google Font load from free CDNs, so **you need internet the first time you open the pages**.

---

## 2. Folder structure

```
zenflow/
├── app.py               ← all Python code (routes + database + logic)
├── requirements.txt     ← Python packages to install (only Flask)
├── database.db          ← created automatically on first run
├── README.md
├── templates/           ← HTML pages (Jinja2 templates)
│   ├── base.html        ← common layout: sidebar, mobile menu, messages
│   ├── flash.html       ← success / error message box
│   ├── index.html       ← home / landing page
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── water.html
│   ├── sleep.html
│   ├── activity.html
│   ├── habits.html
│   ├── analytics.html
│   ├── profile.html
│   └── 404.html         ← "page not found"
└── static/
    ├── css/style.css    ← all design / colours
    └── js/
        ├── charts.js    ← draws Chart.js charts from real database data
        └── main.js      ← form validation, delete confirmation, sleep preview
```

---

## 3. Installation and running (Windows / Mac / Linux)

You need **Python 3.9 or newer**. Check with `python --version`.

```bash
# 1. Open a terminal inside the zenflow folder
cd zenflow

# 2. (Recommended) create a virtual environment
python -m venv venv

# 3. Activate it
#    Windows:
venv\Scripts\activate
#    Mac / Linux:
source venv/bin/activate

# 4. Install Flask
pip install -r requirements.txt

# 5. Start the website
python app.py
```

Now open **http://127.0.0.1:5000** in your browser.

- Press `Ctrl + C` in the terminal to stop the server.
- On Mac/Linux, use `python3` and `pip3` if `python` does not work.

### Database setup

There is nothing to set up by hand. When `app.py` starts it calls `init_db()`, which creates `database.db` and all 7 tables if they don't exist yet.
To start fresh, stop the server, delete `database.db`, and run `python app.py` again.

---

## 4. How to demo it (for viva)

1. Open the home page → click **Get Started** → register an account.
2. Log in → you land on the **Dashboard**.
3. **Water:** click +250 / +500 / +750 ml or type a custom amount. Change the goal. Delete a wrong entry.
4. **Sleep:** enter bedtime 11:00 PM and wake-up 7:00 AM → it saves **8h 0m** (overnight handled).
5. **Activity:** choose Running, 30 minutes, 5 km, 6000 steps → see today's totals and the weekly chart.
6. **Habits:** click a suggestion (e.g. "Meditate") or create your own → tick it as completed → click **Undo** to reverse it.
7. **Analytics:** all 4 weekly charts and averages, built from your saved records.
8. **Profile:** change your name/email, goals and password.
9. Go back to the Dashboard: every card has updated.
10. Register a second account to show that each user only sees their own data.

---

## 5. Database tables

| Table               | Columns                                                         |
|---------------------|-----------------------------------------------------------------|
| `users`             | id, name, email (unique), password (hashed), created_at         |
| `water_records`     | id, user_id, amount_ml, date, time                              |
| `sleep_records`     | id, user_id, bedtime, wakeup_time, duration (hours), date       |
| `activity_records`  | id, user_id, activity_type, duration (min), distance, steps, date |
| `habits`            | id, user_id, habit_name, created_at                             |
| `habit_completions` | id, habit_id, user_id, completion_date, completed (1/0)         |
| `user_goals`        | id, user_id, daily_water_goal (ml), daily_sleep_goal (hours)    |

Every record table has a `user_id` column linked to `users.id`. Every query includes `WHERE user_id = ?`, so a user can only read, change or delete **their own** records.

---

## 6. Important Python functions explained

All of these are in `app.py`.

### Database
- **`get_db()`** – opens a connection to `database.db` (once per request) and returns it. `row_factory = sqlite3.Row` lets us write `row["name"]` instead of `row[1]`.
- **`close_db()`** – runs automatically after every request and closes the connection.
- **`init_db()`** – runs `CREATE TABLE IF NOT EXISTS ...` for all tables when the app starts.

### Login and security
- **`register()`** – checks the form (all fields filled, valid email, password ≥ 6 characters, passwords match, email not already used). It saves the password with `generate_password_hash()`, so the real password is **never stored**.
- **`login()`** – finds the user by email and checks the password with `check_password_hash()`. If correct, it stores `user_id` and `user_name` in the **session** (a signed cookie).
- **`logout()`** – clears the session.
- **`login_required`** – a *decorator*. Writing `@login_required` above a route means: "if the user is not logged in, send them to the login page". It protects every private page.

### Helpers
- **`today_str()`** – today's date as `"YYYY-MM-DD"`.
- **`last_7_days()`** – list of the last 7 dates, used for weekly charts.
- **`percent(value, goal)`** – percentage of a goal, capped at 100. Example: `percent(1500, 2500) → 60`.
- **`get_goals(user_id)`** – returns the user's water and sleep goals (default 2500 ml / 8 h).
- **`safe_next()`** – after a quick action (e.g. +250 ml on the dashboard) it sends the user back to the same page, and only allows pages on this website.

### Water
- **`water_total(user_id, day)`** – `SUM(amount_ml)` for one day.
- **`add_water()`** – validates the amount (must be a number, > 0 and ≤ 5000 ml) and saves it with the current date and time.
- **`set_water_goal()`** / **`delete_water()`** – change the goal / delete one record.

### Sleep
- **`calculate_sleep_duration(bedtime, wakeup_time)`** – converts both times to datetimes. **If wake-up is earlier than bedtime, the person slept past midnight, so 1 day is added.**
  `23:00 → 07:00` = 8.0 hours, `22:30 → 06:15` = 7.75 hours.
- **`add_sleep()`** – validates the inputs, calculates the duration and saves it.

### Activity
- **`add_activity()`** – checks the type is in the allowed list, the duration is 1–1440 minutes, and the optional distance/steps are not negative.
- **`activity()`** – shows the selected day's totals (minutes, steps, km), the history, and a summary by activity type using `GROUP BY activity_type`.

### Habits
- **`toggle_habit(habit_id)`** – if there is no completion for today it inserts one (completed). If there is one, it flips `completed` between 1 and 0 (**Undo**).
- **`calculate_streaks(habit_id)`** – reads every completed date in order.
  - *Longest streak:* counts the longest run of consecutive days.
  - *Current streak:* counts backwards from today (or from yesterday, if today isn't ticked yet) while each day is completed.

### Dashboard and analytics
- **`habit_counts(user_id, day)`** – returns (total habits, completed that day).
- **`weekly_data(user_id)`** – builds 7-day lists of water, sleep, activity and habit % from the database. Flask passes it to the page as JSON (`window.chartData`), and `charts.js` draws the charts. **No random or dummy values.**
- **`dashboard()`** – calculates every card. *Overall daily progress* = average of water %, sleep %, activity % (target 30 min/day) and habit %.
- **`analytics()`** – weekly water average, average sleep (days with records), total weekly activity minutes, and overall habit completion = completions ÷ (habits × 7).

---

## 7. Validation and messages

- Browser side: Bootstrap validation in `main.js` stops empty or invalid forms.
- Server side: every route checks the input again in Python (so it is safe even if JavaScript is off).
- `flash("message", "success" / "danger")` shows green success or red error messages at the top of the page.
- Delete buttons ask "Are you sure?" before deleting.

---

## 8. Common problems

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'flask'` | Run `pip install -r requirements.txt` (inside the activated venv). |
| Page has no styling / charts | Check your internet connection (Bootstrap & Chart.js load from a CDN). |
| Port 5000 already in use | Change the last line to `app.run(debug=True, port=5001)`. |
| Want to reset all data | Stop the server and delete `database.db`. |

Before deploying anywhere public, change `app.secret_key` in `app.py` to your own random text and turn off `debug=True`.
