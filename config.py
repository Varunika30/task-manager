"""Application settings. Override any of these with environment variables where noted."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# IMPORTANT: set a long random SECRET_KEY in production (export SECRET_KEY=...)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

DATABASE = os.environ.get("DATABASE", os.path.join(BASE_DIR, "database", "taskmanager.db"))
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))

# Photo proof rules
MAX_PHOTO_BYTES = 5 * 1024 * 1024               # 5 MB per photo
MAX_CONTENT_LENGTH = MAX_PHOTO_BYTES + 512 * 1024  # request limit (photo + form overhead)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# Rewards
POINTS_PER_TASK = 10
DAILY_BONUS_POINTS = 20       # given at the end of a day when every task due that day is completed

# Relaxation game
GAME_UNLOCK_EVERY = 3         # one break unlocks after every N completed tasks (use 2 or 3)
GAME_SESSION_SECONDS = 180    # each unlock gives one short session

# Reminders: remind for tasks due within this many hours (or already overdue)
REMINDER_WINDOW_HOURS = 24

# Create a demo account + sample tasks the first time the database is created
#   On a public website set SEED_DEMO=0 so nobody gets a demo account with a known password.
SEED_DEMO = os.environ.get("SEED_DEMO", "1") == "1"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Set SECURE_COOKIES=1 when the site is served over HTTPS (PythonAnywhere / Render are)
SESSION_COOKIE_SECURE = os.environ.get("SECURE_COOKIES", "0") == "1"
