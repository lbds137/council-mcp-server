"""Load API keys stored as systemd user credentials.

Keys live in `<directory>/keys.cred`, one encrypted credential holding
NAME=value lines, written by scripts/set-secret.sh with
`systemd-creds encrypt --user`. Only this user on this machine can decrypt it,
and the key never sits in a plaintext file. One file means one decrypt at
startup: each takes about 3 seconds on the TPM, which handles one at a time.

Per-key `<directory>/NAME.cred` files (the earlier layout) still load, for any
name keys.cred doesn't provide.
"""

import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CREDENTIAL_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
DECRYPT_TIMEOUT_SECONDS = 20
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


def _decrypt(path: Path, credential_name: str) -> str | None:
    """Decrypt one credential file, or log why not and return None."""
    try:
        # stdin is the MCP server's JSON-RPC channel: keep the child off it
        result = subprocess.run(
            ["systemd-creds", "decrypt", "--user", f"--name={credential_name}", str(path), "-"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=DECRYPT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Could not run systemd-creds for {path.name}: {e}")
        return None

    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        logger.warning(f"Could not decrypt credential {path.name}: {error}")
        return None

    try:
        return str(result.stdout.decode())
    except UnicodeDecodeError:
        logger.warning(f"Credential {path.name} is not valid UTF-8; skipping it")
        return None
