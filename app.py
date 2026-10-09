"""Task Manager - Flask backend.

Run:  python app.py          (then open http://127.0.0.1:5000)
Demo: demo@example.com / demo1234   (created on first run when SEED_DEMO is True)
"""
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, current_app, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import config

PRIORITIES = ("Low", "Medium", "High")
DT_FORMAT = "%Y-%m-%dT%H:%M"          # how due dates are stored / exchanged
TS_FORMAT = "%Y-%m-%d %H:%M:%S"       # how system timestamps are stored
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def ts(dt=None):
    return (dt or datetime.now()).strftime(TS_FORMAT)


def parse_ts(value):
    return datetime.strptime(value, TS_FORMAT)


def parse_due(value):
    """Accept 'YYYY-MM-DDTHH:MM' (optionally with seconds) and normalise it."""
    for fmt in (DT_FORMAT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def err(message, code=400):
    return jsonify(error=message), code


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db(app, seed=False):
    """Create tables (idempotent). Seed the demo user only when the DB file is brand new."""
    db_path = app.config["DATABASE"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    is_new = not os.path.exists(db_path)
    con = sqlite3.connect(db_path)
    with open(os.path.join(config.BASE_DIR, "database", "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    if seed and is_new:
        cur = con.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@example.com", generate_password_hash("demo1234")),
        )
        con.execute("INSERT INTO streaks (user_id) VALUES (?)", (cur.lastrowid,))
        with open(os.path.join(config.BASE_DIR, "database", "seed.sql"), encoding="utf-8") as f:
            con.executescript(f.read())
    con.commit()
    con.close()


def looks_like_image(stream):
    """Check the real file signature, not just the extension."""
    head = stream.read(12)
    stream.seek(0)
    return (head.startswith(b"\xff\xd8\xff")                        # JPEG
            or head.startswith(b"\x89PNG\r\n\x1a\n")                 # PNG
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))      # WebP


# --------------------------------------------------------------------------- #
# Business logic: tasks, rewards, streaks, game unlocks
# --------------------------------------------------------------------------- #
def task_to_dict(row):
    due = parse_due(row["due_datetime"])
    overdue = row["status"] != "Completed" and due is not None and due < datetime.now()
    proof = row["photo_path"] if "photo_path" in row.keys() else None
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "priority": row["priority"],
        "due_datetime": row["due_datetime"],
        "reminder_interval_minutes": row["reminder_interval_minutes"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "overdue": overdue,
        "proof_url": f"/uploads/{proof}" if proof else None,
    }


TASK_SELECT = ("SELECT t.*, p.photo_path FROM tasks t "
               "LEFT JOIN task_proofs p ON p.task_id = t.id ")


def fetch_task(db, task_id, user_id):
    return db.execute(TASK_SELECT + "WHERE t.id = ? AND t.user_id = ?", (task_id, user_id)).fetchone()


def ensure_streak(db, user_id):
    db.execute("INSERT OR IGNORE INTO streaks (user_id) VALUES (?)", (user_id,))


def get_streak(db, user_id):
    """Return streak info; a streak is broken if yesterday had no completed task."""
    ensure_streak(db, user_id)
    row = db.execute("SELECT * FROM streaks WHERE user_id = ?", (user_id,)).fetchone()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    current = row["current_streak"]
    if row["last_active_date"] and row["last_active_date"] < yesterday and current != 0:
        current = 0
        db.execute("UPDATE streaks SET current_streak = 0 WHERE user_id = ?", (user_id,))
        db.commit()
    return {
        "current_streak": current,
        "longest_streak": row["longest_streak"],
        "total_points": row["total_points"],
        "total_completed": row["total_completed"],
        "last_active_date": row["last_active_date"],
    }


def award_completion(db, user_id):
    """Called once when a task becomes Completed: points, streak, lifetime counter, game unlocks."""
    cfg = current_app.config
    today = date.today().isoformat()
    points = cfg["POINTS_PER_TASK"]

    # today's reward row (points now, bonus is settled at the end of the day)
    db.execute(
        "INSERT INTO rewards (user_id, date, tasks_completed, points_earned) VALUES (?, ?, 1, ?) "
        "ON CONFLICT(user_id, date) DO UPDATE SET "
        "tasks_completed = tasks_completed + 1, points_earned = points_earned + excluded.points_earned",
        (user_id, today, points),
    )

    # streak
    st = get_streak(db, user_id)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if st["last_active_date"] == today:
        streak = st["current_streak"]
    elif st["last_active_date"] == yesterday:
        streak = st["current_streak"] + 1
    else:
        streak = 1
    longest = max(st["longest_streak"], streak)
    db.execute(
        "UPDATE streaks SET current_streak = ?, longest_streak = ?, last_active_date = ?, "
        "total_points = total_points + ?, total_completed = total_completed + 1 WHERE user_id = ?",
        (streak, longest, today, points, user_id),
    )

    # game unlocks: one per N lifetime completed tasks
    total_completed = st["total_completed"] + 1
    earned = total_completed // cfg["GAME_UNLOCK_EVERY"]
    existing = db.execute("SELECT COUNT(*) FROM game_unlocks WHERE user_id = ?", (user_id,)).fetchone()[0]
    new_unlocks = max(0, earned - existing)
    for _ in range(new_unlocks):
        db.execute("INSERT INTO game_unlocks (user_id, unlocked_at) VALUES (?, ?)", (user_id, ts()))
    return {"points": points, "streak": streak, "new_unlocks": new_unlocks}


def finalize_past_days(db, user_id):
    """End-of-day settlement: grant the daily bonus for every past, unsettled day where
    ALL tasks due that day were completed by the end of that day."""
    today = date.today().isoformat()
    bonus_points = current_app.config["DAILY_BONUS_POINTS"]
    rows = db.execute(
        "SELECT * FROM rewards WHERE user_id = ? AND date < ? AND finalized = 0", (user_id, today)
    ).fetchall()
    for r in rows:
        counts = db.execute(
            "SELECT COUNT(*) AS due, "
            "COALESCE(SUM(CASE WHEN status = 'Completed' AND substr(completed_at, 1, 10) <= ? THEN 1 ELSE 0 END), 0) AS done "
            "FROM tasks WHERE user_id = ? AND substr(due_datetime, 1, 10) = ?",
            (r["date"], user_id, r["date"]),
        ).fetchone()
        bonus = 1 if counts["due"] > 0 and counts["done"] == counts["due"] else 0
        extra = bonus_points if bonus else 0
        db.execute(
            "UPDATE rewards SET bonus_awarded = ?, points_earned = points_earned + ?, finalized = 1 WHERE id = ?",
            (bonus, extra, r["id"]),
        )
        if extra:
            db.execute("UPDATE streaks SET total_points = total_points + ? WHERE user_id = ?", (extra, user_id))
    if rows:
        db.commit()


def game_status(db, user_id):
    cfg = current_app.config
    ensure_streak(db, user_id)
    total_completed = db.execute("SELECT total_completed FROM streaks WHERE user_id = ?", (user_id,)).fetchone()[0]
    available = db.execute("SELECT COUNT(*) FROM game_unlocks WHERE user_id = ? AND played = 0", (user_id,)).fetchone()[0]
    plays = db.execute("SELECT COUNT(*) FROM game_unlocks WHERE user_id = ? AND played = 1", (user_id,)).fetchone()[0]
    total_unlocks = available + plays

    remaining = 0
    last = db.execute(
        "SELECT played_at FROM game_unlocks WHERE user_id = ? AND played = 1 ORDER BY played_at DESC, id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if last and last["played_at"]:
        elapsed = (datetime.now() - parse_ts(last["played_at"])).total_seconds()
        remaining = max(0, int(cfg["GAME_SESSION_SECONDS"] - elapsed))

    every = cfg["GAME_UNLOCK_EVERY"]
    return {
        "available": available,
        "total_unlocks": total_unlocks,
        "total_plays": plays,
        "unlock_every": every,
        "next_unlock_in": every - (total_completed % every),
        "session_seconds": cfg["GAME_SESSION_SECONDS"],
        "active_remaining": remaining,
    }


def validate_task_payload(data):
    """Return (clean_dict, error_message)."""
    if not isinstance(data, dict):
        return None, "Invalid request."
    title = (data.get("title") or "").strip()
    if not title:
        return None, "Please give the task a title."
    if len(title) > 120:
        return None, "Title is too long (max 120 characters)."
    description = (data.get("description") or "").strip()
    if len(description) > 1000:
        return None, "Description is too long (max 1000 characters)."
    category = (data.get("category") or "General").strip()[:40] or "General"
    priority = data.get("priority") or "Medium"
    if priority not in PRIORITIES:
        return None, "Priority must be Low, Medium or High."
    due = parse_due(data.get("due_datetime"))
    if due is None:
        return None, "Please choose a valid due date and time."
    try:
        interval = int(data.get("reminder_interval_minutes") or 0)
    except (TypeError, ValueError):
        return None, "Reminder interval must be a number of minutes."
    if interval < 0 or interval > 1440:
        return None, "Reminder interval must be between 0 and 1440 minutes."
    return {
        "title": title, "description": description, "category": category,
        "priority": priority, "due_datetime": due.strftime(DT_FORMAT),
        "reminder_interval_minutes": interval,
    }, None


def motivation(points_today, all_done, due):
    if due and all_done:
        return "Perfect day! Everything is done. 🎉"
    if points_today >= 30:
        return "You're on fire today! 🔥"
    if points_today > 0:
        return "Great start, keep the momentum going! 💪"
    return "One small task is all it takes to start. ✨"


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(config)
    if test_config:
        app.config.update(test_config)
    init_db(app, seed=app.config["SEED_DEMO"])

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            uid = session.get("uid")
            user = get_db().execute("SELECT id, name, email FROM users WHERE id = ?", (uid,)).fetchone() if uid else None
            if user is None:
                session.clear()
                if request.path.startswith("/api/"):
                    return err("Please sign in.", 401)
                return redirect(url_for("login_page"))
            g.user = user
            return fn(*args, **kwargs)
        return wrapper

    # ----------------------------- pages -------------------------------- #
    def page(template, name):
        return render_template(template, user=g.user, page=name)

    @app.get("/")
    @login_required
    def dashboard():
        return page("index.html", "dashboard")

    @app.get("/tasks")
    @login_required
    def tasks_page():
        return page("tasks.html", "tasks")

    @app.get("/calendar")
    @login_required
    def calendar_page():
        return page("calendar.html", "calendar")

    @app.get("/rewards")
    @login_required
    def rewards_page():
        return page("rewards.html", "rewards")

    @app.get("/game")
    @login_required
    def game_page():
        return page("game.html", "game")

    @app.get("/login")
    def login_page():
        if session.get("uid"):
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.get("/uploads/<path:filename>")
    @login_required
    def uploads(filename):
        owned = get_db().execute(
            "SELECT 1 FROM task_proofs p JOIN tasks t ON t.id = p.task_id "
            "WHERE p.photo_path = ? AND t.user_id = ?", (filename, g.user["id"])).fetchone()
        if not owned:
            abort(404)
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    # ------------------------------ auth -------------------------------- #
    @app.post("/api/register")
    def api_register():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not name or len(name) > 60:
            return err("Please enter your name (max 60 characters).")
        if not EMAIL_RE.match(email):
            return err("Please enter a valid email address.")
        if len(password) < 6:
            return err("Password must be at least 6 characters.")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return err("An account with this email already exists.", 409)
        cur = db.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                         (name, email, generate_password_hash(password)))
        ensure_streak(db, cur.lastrowid)
        db.commit()
        session.clear()
        session["uid"] = cur.lastrowid
        return jsonify(ok=True, name=name), 201

    @app.post("/api/login")
    def api_login():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], data.get("password") or ""):
            return err("Incorrect email or password.", 401)
        session.clear()
        session["uid"] = row["id"]
        return jsonify(ok=True, name=row["name"])

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    @login_required
    def api_me():
        return jsonify(id=g.user["id"], name=g.user["name"], email=g.user["email"])

    # ------------------------------ tasks ------------------------------- #
    @app.get("/api/tasks")
    @login_required
    def api_tasks():
        """Filters: status, scope=today, date=YYYY-MM-DD, q=search text."""
        db, uid = get_db(), g.user["id"]
        sql, params = TASK_SELECT + "WHERE t.user_id = ?", [uid]
        status = request.args.get("status")
        if status:
            sql += " AND t.status = ?"
            params.append(status)
        day = request.args.get("date")
        if day:
            sql += " AND substr(t.due_datetime, 1, 10) = ?"
            params.append(day)
        if request.args.get("scope") == "today":
            today = date.today().isoformat()
            sql += " AND (substr(t.due_datetime, 1, 10) = ? OR (t.status != 'Completed' AND substr(t.due_datetime, 1, 10) < ?))"
            params += [today, today]
        q = (request.args.get("q") or "").strip()
        if q:
            sql += " AND (t.title LIKE ? OR t.description LIKE ? OR t.category LIKE ?)"
            params += [f"%{q}%"] * 3
        sql += " ORDER BY t.due_datetime ASC, t.id ASC"
        rows = db.execute(sql, params).fetchall()
        return jsonify(tasks=[task_to_dict(r) for r in rows])

    @app.post("/api/tasks")
    @login_required
    def api_create_task():
        clean, error = validate_task_payload(request.get_json(silent=True))
        if error:
            return err(error)
        db = get_db()
        cur = db.execute(
            "INSERT INTO tasks (user_id, title, description, category, priority, due_datetime, reminder_interval_minutes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], clean["title"], clean["description"], clean["category"], clean["priority"],
             clean["due_datetime"], clean["reminder_interval_minutes"]))
        db.commit()
        return jsonify(task=task_to_dict(fetch_task(db, cur.lastrowid, g.user["id"]))), 201

    @app.put("/api/tasks/<int:task_id>")
    @login_required
    def api_update_task(task_id):
        db = get_db()
        if not fetch_task(db, task_id, g.user["id"]):
            return err("Task not found.", 404)
        clean, error = validate_task_payload(request.get_json(silent=True))
        if error:
            return err(error)
        # NOTE: status is deliberately NOT editable here - it only changes via mark-done / proof.
        db.execute(
            "UPDATE tasks SET title=?, description=?, category=?, priority=?, due_datetime=?, "
            "reminder_interval_minutes=?, last_reminded_at=NULL WHERE id=? AND user_id=?",
            (clean["title"], clean["description"], clean["category"], clean["priority"],
             clean["due_datetime"], clean["reminder_interval_minutes"], task_id, g.user["id"]))
        db.commit()
        return jsonify(task=task_to_dict(fetch_task(db, task_id, g.user["id"])))

    @app.delete("/api/tasks/<int:task_id>")
    @login_required
    def api_delete_task(task_id):
        db = get_db()
        row = fetch_task(db, task_id, g.user["id"])
        if not row:
            return err("Task not found.", 404)
        db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, g.user["id"]))
        db.commit()
        if row["photo_path"]:
            try:
                os.remove(os.path.join(app.config["UPLOAD_FOLDER"], row["photo_path"]))
            except OSError:
                pass
        return jsonify(ok=True)

    @app.post("/api/tasks/<int:task_id>/mark-done")
    @login_required
    def api_mark_done(task_id):
        """Step 1 of completing a task: it moves to 'Awaiting Proof' - NOT 'Completed'."""
        db = get_db()
        row = fetch_task(db, task_id, g.user["id"])
        if not row:
            return err("Task not found.", 404)
        if row["status"] == "Completed":
            return err("This task is already completed.")
        db.execute("UPDATE tasks SET status = 'Awaiting Proof' WHERE id = ?", (task_id,))
        db.commit()
        return jsonify(task=task_to_dict(fetch_task(db, task_id, g.user["id"])))

    @app.post("/api/tasks/<int:task_id>/reopen")
    @login_required
    def api_reopen(task_id):
        """Undo 'mark done' (only while still waiting for the proof photo)."""
        db = get_db()
        row = fetch_task(db, task_id, g.user["id"])
        if not row:
            return err("Task not found.", 404)
        if row["status"] != "Awaiting Proof":
            return err("Only tasks waiting for proof can be moved back.")
        db.execute("UPDATE tasks SET status = 'Pending' WHERE id = ?", (task_id,))
        db.commit()
        return jsonify(task=task_to_dict(fetch_task(db, task_id, g.user["id"])))

    @app.post("/api/tasks/<int:task_id>/proof")
    @login_required
    def api_upload_proof(task_id):
        """Step 2: upload a photo. Only now does the task become 'Completed'."""
        db, uid = get_db(), g.user["id"]
        row = fetch_task(db, task_id, uid)
        if not row:
            return err("Task not found.", 404)
        if row["status"] == "Completed":
            return err("This task is already completed.")
        if row["status"] != "Awaiting Proof":
            return err("Mark the task as done first, then upload your proof photo.")

        photo = request.files.get("photo")
        if photo is None or not photo.filename:
            return err("Please choose a photo of your finished work.")
        ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
        if ext not in app.config["ALLOWED_EXTENSIONS"]:
            return err("Photo must be a JPG, PNG or WEBP image.")
        photo.stream.seek(0, os.SEEK_END)
        size = photo.stream.tell()
        photo.stream.seek(0)
        if size == 0:
            return err("That file is empty.")
        if size > app.config["MAX_PHOTO_BYTES"]:
            return err("Photo is too large (max 5 MB).", 413)
        if not looks_like_image(photo.stream):
            return err("That file doesn't look like a valid image.")

        filename = f"{uuid.uuid4().hex}.{'jpg' if ext == 'jpeg' else ext}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        photo.save(path)
        try:
            db.execute("INSERT INTO task_proofs (task_id, photo_path, uploaded_at) VALUES (?, ?, ?)",
                       (task_id, filename, ts()))
            db.execute("UPDATE tasks SET status = 'Completed', completed_at = ? WHERE id = ?", (ts(), task_id))
            result = award_completion(db, uid)
            db.commit()
        except Exception:
            db.rollback()
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        return jsonify(task=task_to_dict(fetch_task(db, task_id, uid)), reward=result)

    # ---------------------------- reminders ----------------------------- #
    @app.get("/api/reminders/due")
    @login_required
    def api_reminders_due():
        """Tasks that need a reminder right now. Each returned task is stamped so it is
        not returned again until its reminder interval has passed."""
        db, uid = get_db(), g.user["id"]
        now = datetime.now()
        horizon = now + timedelta(hours=app.config["REMINDER_WINDOW_HOURS"])
        rows = db.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status != 'Completed' "
            "AND reminder_interval_minutes > 0 AND due_datetime <= ? ORDER BY due_datetime",
            (uid, horizon.strftime(DT_FORMAT))).fetchall()
        due = []
        for r in rows:
            last = parse_ts(r["last_reminded_at"]) if r["last_reminded_at"] else None
            if last is None or (now - last).total_seconds() >= r["reminder_interval_minutes"] * 60:
                due_dt = parse_due(r["due_datetime"])
                minutes_left = int((due_dt - now).total_seconds() // 60)
                due.append({"id": r["id"], "title": r["title"], "status": r["status"],
                            "due_datetime": r["due_datetime"], "minutes_left": minutes_left,
                            "overdue": minutes_left < 0})
                db.execute("UPDATE tasks SET last_reminded_at = ? WHERE id = ?", (ts(now), r["id"]))
        db.commit()
        return jsonify(reminders=due)

    # ----------------------------- calendar ----------------------------- #
    @app.get("/api/calendar")
    @login_required
    def api_calendar():
        """Use ?month=YYYY-MM, or ?start=YYYY-MM-DD&end=YYYY-MM-DD for any range."""
        month = request.args.get("month")
        if month:
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                return err("month must look like 2026-10.")
            start = f"{month}-01"
            y, m = int(month[:4]), int(month[5:])
            nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
            end = (nxt - timedelta(days=1)).isoformat()
        else:
            start, end = request.args.get("start"), request.args.get("end")
            if not (start and end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end)):
                return err("Provide month=YYYY-MM or start and end dates (YYYY-MM-DD).")
        rows = get_db().execute(
            TASK_SELECT + "WHERE t.user_id = ? AND substr(t.due_datetime, 1, 10) BETWEEN ? AND ? "
            "ORDER BY t.due_datetime", (g.user["id"], start, end)).fetchall()
        return jsonify(start=start, end=end, tasks=[task_to_dict(r) for r in rows])

    # ----------------------------- rewards ------------------------------ #
    @app.get("/api/rewards/summary")
    @login_required
    def api_rewards_summary():
        db, uid = get_db(), g.user["id"]
        finalize_past_days(db, uid)
        streak = get_streak(db, uid)
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        counts = db.execute(
            "SELECT COUNT(*) AS due, COALESCE(SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END), 0) AS done "
            "FROM tasks WHERE user_id = ? AND substr(due_datetime, 1, 10) = ?", (uid, today)).fetchone()
        today_row = db.execute("SELECT * FROM rewards WHERE user_id = ? AND date = ?", (uid, today)).fetchone()
        points_today = today_row["points_earned"] if today_row else 0
        all_done = counts["due"] > 0 and counts["done"] == counts["due"]

        y_row = db.execute("SELECT * FROM rewards WHERE user_id = ? AND date = ? AND finalized = 1",
                           (uid, yesterday)).fetchone()
        history = db.execute("SELECT * FROM rewards WHERE user_id = ? ORDER BY date DESC LIMIT 7", (uid,)).fetchall()

        def reward_dict(r):
            return {"date": r["date"], "tasks_completed": r["tasks_completed"],
                    "points_earned": r["points_earned"], "bonus_awarded": bool(r["bonus_awarded"]),
                    "finalized": bool(r["finalized"])}

        return jsonify(
            today={"date": today, "tasks_due": counts["due"], "tasks_due_done": counts["done"],
                   "tasks_completed": today_row["tasks_completed"] if today_row else 0,
                   "points": points_today, "all_done": all_done,
                   "bonus_points": app.config["DAILY_BONUS_POINTS"],
                   "message": motivation(points_today, all_done, counts["due"])},
            yesterday=reward_dict(y_row) if y_row else None,
            history=[reward_dict(r) for r in history],
            streak=streak,
            total_points=streak["total_points"],
            game=game_status(db, uid),
            config={"points_per_task": app.config["POINTS_PER_TASK"],
                    "daily_bonus": app.config["DAILY_BONUS_POINTS"]},
        )

    # ------------------------------- game ------------------------------- #
    @app.get("/api/game/status")
    @login_required
    def api_game_status():
        return jsonify(game_status(get_db(), g.user["id"]))

    @app.post("/api/game/play")
    @login_required
    def api_game_play():
        """Start a relaxation session. Uses up one unlock (limited access).
        If a session is still running (e.g. page reloaded) it is resumed, not charged again."""
        db, uid = get_db(), g.user["id"]
        status = game_status(db, uid)
        if status["active_remaining"] > 0:
            return jsonify(remaining=status["active_remaining"], resumed=True)
        unlock = db.execute(
            "SELECT id FROM game_unlocks WHERE user_id = ? AND played = 0 ORDER BY id LIMIT 1", (uid,)).fetchone()
        if not unlock:
            return err(f"Complete {status['next_unlock_in']} more task(s) to unlock a break.", 403)
        db.execute("UPDATE game_unlocks SET played = 1, played_at = ? WHERE id = ?", (ts(), unlock["id"]))
        db.commit()
        return jsonify(remaining=app.config["GAME_SESSION_SECONDS"], resumed=False)

    # ------------------------------ errors ------------------------------ #
    @app.errorhandler(413)
    def too_large(_e):
        return err("Photo is too large (max 5 MB).", 413)

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return err("Not found.", 404)
        return redirect(url_for("dashboard"))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
