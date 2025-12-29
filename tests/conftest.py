"""Pytest configuration for PyCharm compatibility"""

import atexit
import io
import sys
from pathlib import Path

# Add the project root and src directory to Python path so tests can import properly
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Store the original stdout/stderr
_original_stdout = sys.stdout
_original_stderr = sys.stderr


def ensure_valid_streams():
    """Ensure stdout/stderr are valid file objects"""
    # If stdout is closed or invalid, replace with a StringIO
    try:
        sys.stdout.write("")
    except (ValueError, AttributeError):
        sys.stdout = _original_stdout if _original_stdout else io.StringIO()

    try:
        sys.stderr.write("")
    except (ValueError, AttributeError):
        sys.stderr = _original_stderr if _original_stderr else io.StringIO()


# Register cleanup to run at exit
atexit.register(ensure_valid_streams)


def pytest_configure(config):
    """Configure pytest for PyCharm compatibility"""
    # Ensure streams are valid at start
    ensure_valid_streams()


def pytest_unconfigure(config):
    """Ensure streams are valid at end"""
    ensure_valid_streams()
