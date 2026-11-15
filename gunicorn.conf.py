"""Prepare the profile-photo schema before Render starts Gunicorn workers."""

import os
from pathlib import Path
import subprocess
import sys


def on_starting(server):
    if os.environ.get("RENDER") != "true":
        return
    project_root = Path(__file__).resolve().parent
    subprocess.run(
        [sys.executable, str(project_root / "manage.py"), "prepare_profile_photo_schema"],
        cwd=project_root,
        check=True,
        timeout=90,
    )
