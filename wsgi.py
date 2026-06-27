import sys
import os

# ---------------------------------------------------------------------------
# PythonAnywhere WSGI entry point
# ---------------------------------------------------------------------------
# 1. Replace '/home/yourusername/SIEM_simulator' with the path where you
#    uploaded this project on PythonAnywhere.
# 2. In the PythonAnywhere Web tab, set the WSGI configuration file to point
#    to this file.
# ---------------------------------------------------------------------------

PROJECT_PATH = '/home/yourusername/SIEM_simulator'
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Activate the virtual environment if you created one (recommended)
VENV_PATH = os.path.join(PROJECT_PATH, 'venv')
if os.path.isdir(VENV_PATH):
    activate = os.path.join(VENV_PATH, 'bin', 'activate_this.py')
    if os.path.exists(activate):
        exec(open(activate).read(), {'__file__': activate})

from app import app as application
