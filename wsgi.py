"""Entry point for hosting (PythonAnywhere, Render/gunicorn, etc.).

The app compares due dates with the server's clock, and hosting servers run in UTC.
So we set the timezone to India time here. Change TZ_NAME if your users live elsewhere.
"""
import os
import time

TZ_NAME = os.environ.get("APP_TZ", "Asia/Kolkata")
os.environ["TZ"] = TZ_NAME
if hasattr(time, "tzset"):      # Linux servers; not needed on Windows
    time.tzset()

from app import create_app  # noqa: E402

application = create_app()       # PythonAnywhere looks for the name "application"
app = application                # gunicorn wsgi:app
