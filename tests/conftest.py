"""Pytest configuration for PyCharm compatibility"""

import sys
import io
import atexit


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