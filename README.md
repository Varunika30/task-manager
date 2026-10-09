# TaskNest — Task Management App

A simple, attractive task manager with a few custom features that keep you motivated and accountable.

| Layer    | Technology                          |
|----------|-------------------------------------|
| Frontend | HTML + CSS + vanilla JavaScript     |
| Backend  | Python (Flask)                      |
| Database | SQL (SQLite — schema is portable)   |

## Features

- **Tasks** — add, edit, delete; title, notes, category, priority (Low/Medium/High), due date/time.
- **Frequent reminders** — pick an interval per task (15 min … 3 h). In-app toasts plus optional browser notifications, repeating until the task is completed.
- **Photo proof of completion** — "Mark done" moves a task to *Awaiting Proof*. Only after you upload a photo (JPG/PNG/WEBP, max 5 MB) does it become *Completed*.
- **Calendar** — month, week and list views; colour-coded by status; click a day to see or add tasks.
- **End-of-day reward** — 10 points per completed task, plus a 20-point bonus when every task due that day is done. A summary card shows yesterday's result. Streak counter and badges included.
- **Frequent updates** — the page refreshes itself every 45 seconds; reminders are checked every minute.
- **Relaxation break** — after every 3 completed tasks, one short (3-minute) bubble-pop session unlocks. Limited access: each unlock = one session. Easy to reach from the nav bar, the dashboard and a popup.
- **Design** — soft colours, rounded cards, mobile-friendly layout, dark mode toggle.

## Setup

```bash
# 1. (optional) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. install requirements
pip install -r requirements.txt

# 3. run the app (the database is created automatically on first run)
python app.py
```

Open **http://127.0.0.1:5000**.

First run creates `database/taskmanager.db` and a demo account with sample tasks:

- email: `demo@example.com`
- password: `demo1234`

You can also register your own account on the sign-in page. To start fresh, stop the app and delete `database/taskmanager.db` (and the files in `uploads/`).

### Run the tests

```bash
python -m unittest discover -s tests -v
```

## Project structure

```
task-manager/
├── app.py                 Flask app: pages + JSON API + business logic
├── config.py              Settings (points, bonus, unlock interval, limits)
├── requirements.txt
├── database/
│   ├── schema.sql         Tables, constraints, indexes
│   └── seed.sql           Sample tasks for the demo user
├── templates/             base, login, index (dashboard), tasks, calendar, rewards, game
├── static/
│   ├── css/style.css
│   └── js/                app.js (shared + pages), game.js, auth.js
├── uploads/               Proof photos (private; served only to their owner)
└── tests/test_flow.py
```

## Settings you may want to change (`config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `POINTS_PER_TASK` | 10 | Points per completed task |
| `DAILY_BONUS_POINTS` | 20 | End-of-day bonus when all of the day's tasks are done |
| `GAME_UNLOCK_EVERY` | 3 | Completed tasks per game unlock (use 2 or 3) |
| `GAME_SESSION_SECONDS` | 180 | Length of one relaxation session |
| `REMINDER_WINDOW_HOURS` | 24 | Reminders start this long before a task is due |
| `SECRET_KEY` | dev value | **Set your own** via the `SECRET_KEY` environment variable |

## Database tables

`users`, `tasks`, `task_proofs`, `rewards`, `streaks`, `game_unlocks` — see `database/schema.sql`. All queries use parameters (no string-built SQL). To move to MySQL or PostgreSQL, adapt the comments at the top of `schema.sql` and swap the `sqlite3` connection in `app.py`.

## API overview

| Method & path | Purpose |
|---|---|
| `POST /api/register`, `/api/login`, `/api/logout` | Accounts |
| `GET /api/tasks` (`status`, `scope=today`, `date`, `q`) | List tasks |
| `POST /api/tasks` · `PUT/DELETE /api/tasks/<id>` | Create, edit, delete |
| `POST /api/tasks/<id>/mark-done` | Step 1 → *Awaiting Proof* |
| `POST /api/tasks/<id>/proof` | Step 2 → photo upload → *Completed* |
| `POST /api/tasks/<id>/reopen` | Undo "mark done" while awaiting proof |
| `GET /api/reminders/due` | Tasks that need a reminder now |
| `GET /api/calendar?month=YYYY-MM` (or `start`/`end`) | Tasks for the calendar |
| `GET /api/rewards/summary` | Points, streak, daily summary, history |
| `GET /api/game/status` · `POST /api/game/play` | Relaxation break |

## Notes

- Times use the server's local clock, which is ideal for personal use on one computer.
- Before deploying publicly: set a strong `SECRET_KEY`, serve over HTTPS, and run with a production server (for example `gunicorn "app:create_app()"`) instead of `python app.py`.
