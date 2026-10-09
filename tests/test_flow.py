"""Tests for the core flow: mark done -> upload proof -> completed, rewards, reminders, game.

Run from the project folder:   python -m unittest discover -s tests -v
"""
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import create_app  # noqa: E402

# smallest valid-looking PNG (signature + a few bytes) - enough for the signature check
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def due(hours=2):
    return (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


class TaskFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True, "SEED_DEMO": False,
            "DATABASE": os.path.join(self.tmp.name, "test.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp.name, "uploads"),
        })
        self.c = self.app.test_client()
        r = self.c.post("/api/register", json={"name": "Tester", "email": "t@example.com", "password": "secret1"})
        self.assertEqual(r.status_code, 201)

    def tearDown(self):
        self.tmp.cleanup()

    # helpers
    def new_task(self, title="Write report", hours=2, interval=0):
        r = self.c.post("/api/tasks", json={"title": title, "due_datetime": due(hours),
                                            "reminder_interval_minutes": interval})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["task"]

    def complete(self, task_id, data=PNG, name="work.png"):
        self.c.post(f"/api/tasks/{task_id}/mark-done")
        return self.c.post(f"/api/tasks/{task_id}/proof",
                           data={"photo": (io.BytesIO(data), name)}, content_type="multipart/form-data")

    # ---- auth ----
    def test_requires_login(self):
        anon = self.app.test_client()
        self.assertEqual(anon.get("/api/tasks").status_code, 401)
        self.assertEqual(anon.get("/").status_code, 302)

    def test_login_wrong_password(self):
        anon = self.app.test_client()
        r = anon.post("/api/login", json={"email": "t@example.com", "password": "nope"})
        self.assertEqual(r.status_code, 401)

    # ---- validation ----
    def test_task_validation(self):
        bad = self.c.post("/api/tasks", json={"title": "  ", "due_datetime": due()})
        self.assertEqual(bad.status_code, 400)
        bad = self.c.post("/api/tasks", json={"title": "x", "due_datetime": "not a date"})
        self.assertEqual(bad.status_code, 400)

    # ---- the key rule: proof photo required ----
    def test_cannot_complete_without_proof(self):
        t = self.new_task()
        # cannot upload proof before marking done
        r = self.c.post(f"/api/tasks/{t['id']}/proof", data={"photo": (io.BytesIO(PNG), "a.png")},
                        content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        # mark done -> only 'Awaiting Proof'
        r = self.c.post(f"/api/tasks/{t['id']}/mark-done")
        self.assertEqual(r.get_json()["task"]["status"], "Awaiting Proof")
        # status cannot be forced through the edit endpoint
        self.c.put(f"/api/tasks/{t['id']}", json={"title": "x", "due_datetime": due(), "status": "Completed"})
        tasks = self.c.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(tasks[0]["status"], "Awaiting Proof")

    def test_proof_completes_task_and_awards_points(self):
        t = self.new_task()
        r = self.complete(t["id"])
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertEqual(body["task"]["status"], "Completed")
        self.assertTrue(body["task"]["proof_url"])
        self.assertEqual(body["reward"]["points"], 10)
        s = self.c.get("/api/rewards/summary").get_json()
        self.assertEqual(s["total_points"], 10)
        self.assertEqual(s["streak"]["current_streak"], 1)
        # the photo is served back to its owner only
        self.assertEqual(self.c.get(body["task"]["proof_url"]).status_code, 200)
        self.assertEqual(self.app.test_client().get(body["task"]["proof_url"]).status_code, 302)

    def test_bad_photos_rejected(self):
        t = self.new_task()
        self.c.post(f"/api/tasks/{t['id']}/mark-done")
        url = f"/api/tasks/{t['id']}/proof"
        r = self.c.post(url, data={"photo": (io.BytesIO(b"hello"), "notes.txt")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)                                    # wrong extension
        r = self.c.post(url, data={"photo": (io.BytesIO(b"not an image"), "fake.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)                                    # fake image
        big = PNG + b"\x00" * (5 * 1024 * 1024)
        r = self.c.post(url, data={"photo": (io.BytesIO(big), "big.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 413)                                    # too large
        tasks = self.c.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(tasks[0]["status"], "Awaiting Proof")                  # still not completed

    # ---- game ----
    def test_game_unlocks_after_three_tasks_and_is_limited(self):
        ids = [self.new_task(f"t{i}")["id"] for i in range(3)]
        self.assertEqual(self.c.post("/api/game/play").status_code, 403)         # locked
        results = [self.complete(i).get_json() for i in ids]
        self.assertEqual([r["reward"]["new_unlocks"] for r in results], [0, 0, 1])
        g = self.c.get("/api/game/status").get_json()
        self.assertEqual(g["available"], 1)
        first = self.c.post("/api/game/play")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["remaining"], self.app.config["GAME_SESSION_SECONDS"])
        again = self.c.post("/api/game/play")                                    # same running session: resumed, not charged
        self.assertTrue(again.get_json()["resumed"])
        g = self.c.get("/api/game/status").get_json()
        self.assertEqual((g["available"], g["total_plays"]), (0, 1))

    # ---- reminders ----
    def test_reminders_repeat_by_interval_and_stop_when_completed(self):
        t = self.new_task("Soon", hours=1, interval=30)
        self.new_task("No reminder", hours=1, interval=0)
        first = self.c.get("/api/reminders/due").get_json()["reminders"]
        self.assertEqual([r["id"] for r in first], [t["id"]])
        self.assertEqual(self.c.get("/api/reminders/due").get_json()["reminders"], [])   # not again right away
        con = sqlite3.connect(self.app.config["DATABASE"])                               # pretend 31 min passed
        old = (datetime.now() - timedelta(minutes=31)).strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE tasks SET last_reminded_at = ?", (old,)); con.commit(); con.close()
        self.assertEqual(len(self.c.get("/api/reminders/due").get_json()["reminders"]), 1)
        self.complete(t["id"])
        con = sqlite3.connect(self.app.config["DATABASE"])
        con.execute("UPDATE tasks SET last_reminded_at = ?", (old,)); con.commit(); con.close()
        self.assertEqual(self.c.get("/api/reminders/due").get_json()["reminders"], [])

    # ---- calendar ----
    def test_calendar_month_and_range(self):
        self.new_task("Today")
        month = date.today().strftime("%Y-%m")
        r = self.c.get(f"/api/calendar?month={month}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/api/calendar?month=2026-13").status_code, 400)
        r = self.c.get(f"/api/calendar?start={date.today()}&end={date.today() + timedelta(days=7)}")
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(len(r.get_json()["tasks"]), 1)   # the task is due today or (late at night) tomorrow

    # ---- end-of-day bonus ----
    def test_end_of_day_bonus(self):
        yesterday = date.today() - timedelta(days=1)
        t = self.new_task("Y task")
        self.complete(t["id"])
        con = sqlite3.connect(self.app.config["DATABASE"])    # move everything back one day
        y = yesterday.isoformat()
        con.execute("UPDATE rewards SET date = ?", (y,))
        con.execute("UPDATE tasks SET due_datetime = ?, completed_at = ?", (y + "T10:00", y + " 11:00:00"))
        con.execute("UPDATE streaks SET last_active_date = ?", (y,))
        con.commit(); con.close()
        s = self.c.get("/api/rewards/summary").get_json()
        self.assertEqual(s["yesterday"]["bonus_awarded"], True)
        self.assertEqual(s["yesterday"]["points_earned"], 10 + self.app.config["DAILY_BONUS_POINTS"])
        self.assertEqual(s["total_points"], 10 + self.app.config["DAILY_BONUS_POINTS"])
        self.assertEqual(s["streak"]["current_streak"], 1)                       # still alive (active yesterday)

    # ---- isolation ----
    def test_users_cannot_touch_each_others_tasks(self):
        t = self.new_task()
        other = self.app.test_client()
        other.post("/api/register", json={"name": "Other", "email": "o@example.com", "password": "secret2"})
        self.assertEqual(other.delete(f"/api/tasks/{t['id']}").status_code, 404)
        self.assertEqual(other.post(f"/api/tasks/{t['id']}/mark-done").status_code, 404)
        self.assertEqual(other.get("/api/tasks").get_json()["tasks"], [])


if __name__ == "__main__":
    unittest.main()
