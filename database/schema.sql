-- Task Manager schema (SQLite).
-- Portability note for MySQL / PostgreSQL:
--   * replace "INTEGER PRIMARY KEY AUTOINCREMENT" with AUTO_INCREMENT (MySQL) or SERIAL/IDENTITY (PostgreSQL)
--   * replace datetime('now','localtime') defaults with CURRENT_TIMESTAMP
--   * dates are stored as ISO text ('YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DDTHH:MM'); use DATETIME columns there.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title                     TEXT NOT NULL,
    description               TEXT NOT NULL DEFAULT '',
    category                  TEXT NOT NULL DEFAULT 'General',
    priority                  TEXT NOT NULL DEFAULT 'Medium' CHECK (priority IN ('Low','Medium','High')),
    due_datetime              TEXT NOT NULL,                 -- 'YYYY-MM-DDTHH:MM'
    reminder_interval_minutes INTEGER NOT NULL DEFAULT 0,    -- 0 = no reminders
    last_reminded_at          TEXT,
    status                    TEXT NOT NULL DEFAULT 'Pending'
                              CHECK (status IN ('Pending','Awaiting Proof','Completed')),
    created_at                TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    completed_at              TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_user      ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due       ON tasks(due_datetime);
CREATE INDEX IF NOT EXISTS idx_tasks_user_stat ON tasks(user_id, status);

-- One photo per task. A task only becomes 'Completed' after a row is added here.
CREATE TABLE IF NOT EXISTS task_proofs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    photo_path  TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- One row per user per day. points_earned includes the end-of-day bonus once finalized.
CREATE TABLE IF NOT EXISTS rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            TEXT NOT NULL,                  -- 'YYYY-MM-DD'
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    points_earned   INTEGER NOT NULL DEFAULT 0,
    bonus_awarded   INTEGER NOT NULL DEFAULT 0,     -- 1 when the daily bonus was granted
    finalized       INTEGER NOT NULL DEFAULT 0,     -- 1 once the day has ended and been settled
    UNIQUE (user_id, date)
);
CREATE INDEX IF NOT EXISTS idx_rewards_user_date ON rewards(user_id, date);

CREATE TABLE IF NOT EXISTS streaks (
    user_id          INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    current_streak   INTEGER NOT NULL DEFAULT 0,
    longest_streak   INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    total_points     INTEGER NOT NULL DEFAULT 0,
    total_completed  INTEGER NOT NULL DEFAULT 0     -- lifetime completed tasks (drives game unlocks)
);

-- Each unlock = one short relaxation session.
CREATE TABLE IF NOT EXISTS game_unlocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unlocked_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    played      INTEGER NOT NULL DEFAULT 0,
    played_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_unlocks_user ON game_unlocks(user_id, played);
