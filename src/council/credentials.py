"""Load API keys stored as systemd user credentials.

Keys live in `<directory>/keys.cred`, one encrypted credential holding
NAME=value lines, written by scripts/set-secret.sh with
`systemd-creds encrypt --user`. Only this user on this machine can decrypt it,
and the key never sits in a plaintext file. One file means one decrypt at
startup: each takes about 3 seconds on the TPM, which handles one at a time.

Per-key `<directory>/NAME.cred` files (the earlier layout) still load, for any
name keys.cred doesn't provide.

Every council process on the machine shares the TPM, so decrypts take turns
through a lock file, and a decrypt that times out leaves a marker that makes
the next few minutes of startups skip the TPM instead of queueing behind it.
A burst of headless `claude -p` runs once stacked dozens of decrypts on a
stalled TPM this way (2026-09-24).
"""

import fcntl
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import IO

logger = logging.getLogger(__name__)

CREDENTIAL_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
DECRYPT_TIMEOUT_SECONDS = 20
# Long enough for a handful of sessions starting together (about 3 s each)
LOCK_WAIT_SECONDS = 30
STALL_BACKOFF_SECONDS = 300
BUNDLE_FILE = "keys.cred"
BUNDLE_CREDENTIAL_NAME = "council-keys"


def load_credentials(directory: str) -> list[str]:
    """Decrypt the stored keys into os.environ.

    A variable that is already set wins, so an explicit environment override
    still works. Failures are logged and skipped; values are never logged.

    Args:
        directory: Directory holding keys.cred and any per-key NAME.cred files.

    Returns:
        Names of the variables that were loaded.
    """
    credential_dir = Path(directory)
    if not credential_dir.is_dir():
        return []

    loaded: list[str] = []
    bundle = credential_dir / BUNDLE_FILE
    if bundle.is_file():
        text = _decrypt(bundle, BUNDLE_CREDENTIAL_NAME)
        if text is not None:
            for number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                name, separator, value = line.partition("=")
                if not separator or not CREDENTIAL_NAME_PATTERN.match(name):
                    # Name the line, never its content: it may hold a key
                    logger.warning(f"Skipping malformed line {number} in {BUNDLE_FILE}")
                    continue
                _set(name, value.strip(), loaded)

    for path in sorted(credential_dir.glob("*.cred")):
        name = path.stem
        if path.name == BUNDLE_FILE or name in loaded:
            continue
        if not CREDENTIAL_NAME_PATTERN.match(name):
            logger.warning(f"Skipping credential with invalid name: {path.name}")
            continue
        if name in os.environ:
            # Checked before decrypting, which is the slow part
            logger.info(f"{name} already set in the environment; skipping its credential")
            continue
        decrypted = _decrypt(path, name)
        if decrypted is not None:
            _set(name, decrypted.strip(), loaded)

    if loaded:
        logger.info(f"Loaded credentials: {', '.join(loaded)}")
    return loaded


def _set(name: str, value: str, loaded: list[str]) -> None:
    """Export one key unless the environment already sets it."""
    if name in os.environ:
        logger.info(f"{name} already set in the environment; skipping its credential")
        return
    os.environ[name] = value
    loaded.append(name)


def _state_dir() -> Path:
    """Where the lock and stall marker live; the runtime dir is cleared at reboot."""
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    state = Path(base) / "council"
    state.mkdir(mode=0o700, exist_ok=True)
    return state


def _decrypt(path: Path, credential_name: str) -> str | None:
    """Decrypt one credential file, taking turns on the TPM with other council processes."""
    try:
        state = _state_dir()
    except OSError as e:
        logger.warning(f"No state directory for the decrypt lock ({e}); decrypting unguarded")
        return _run_decrypt(path, credential_name, None)

    stall_marker = state / "tpm-stalled"
    if _stalled_recently(stall_marker):
        logger.warning(
            f"Skipping {path.name}: a decrypt timed out in the last "
            f"{STALL_BACKOFF_SECONDS // 60} min, so the TPM is likely stuck "
            "(a reboot clears it). Reconnect council later to retry."
        )
        return None

    with open(state / "decrypt.lock", "w") as lock:
        if not _acquire(lock):
            logger.warning(
                f"Skipping {path.name}: another council process held the TPM for "
                f"{LOCK_WAIT_SECONDS} s. Reconnect council later to retry."
            )
            return None
        return _run_decrypt(path, credential_name, stall_marker)


def _stalled_recently(marker: Path) -> bool:
    try:
        return time.time() - marker.stat().st_mtime < STALL_BACKOFF_SECONDS
    except FileNotFoundError:
        return False


def _acquire(lock: IO[str]) -> bool:
    """Take the lock, waiting up to LOCK_WAIT_SECONDS. Closing the file releases it."""
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)


def _run_decrypt(path: Path, credential_name: str, stall_marker: Path | None) -> str | None:
    """Run systemd-creds once, or log why not and return None."""
    try:
        # stdin is the MCP server's JSON-RPC channel: keep the child off it
        result = subprocess.run(
            ["systemd-creds", "decrypt", "--user", f"--name={credential_name}", str(path), "-"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=DECRYPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        logger.warning(f"Could not run systemd-creds for {path.name}: {e}")
        if stall_marker is not None:
            stall_marker.touch()
        return None
    except OSError as e:
        logger.warning(f"Could not run systemd-creds for {path.name}: {e}")
        return None

    if stall_marker is not None:
        stall_marker.unlink(missing_ok=True)

    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        logger.warning(f"Could not decrypt credential {path.name}: {error}")
        return None

    try:
        return str(result.stdout.decode())
    except UnicodeDecodeError:
        logger.warning(f"Credential {path.name} is not valid UTF-8; skipping it")
        return None
