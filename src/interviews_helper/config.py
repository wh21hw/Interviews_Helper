import os
from pathlib import Path

# Installed CLI state belongs to the directory in which the Agent runs. An explicit
# home makes service/automation runs independent of their process working directory.
PROJECT_ROOT = Path(os.environ.get("INTERVIEWS_HELPER_HOME", Path.cwd())).expanduser().resolve()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
IMAGE_DIR = DATA_DIR / "images"
RUN_DIR = DATA_DIR / "runs"
DEFAULT_OUTPUT = PROJECT_ROOT / "interviews.html"
DEFAULT_PROFILE = PROJECT_ROOT / ".browser-profile-xhs-2"
DEFAULT_PROFILE_ROOT = PROJECT_ROOT
CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
]
