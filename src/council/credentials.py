"""Load API keys stored as systemd user credentials.

Each key lives in `<directory>/NAME.cred`, encrypted by scripts/set-secret.sh
with `systemd-creds encrypt --user`, so only this user on this machine can
decrypt it and the key never sits in a plaintext file.
"""

import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CREDENTIAL_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
DECRYPT_TIMEOUT_SECONDS = 20


def load_credentials(directory: str) -> list[str]:
    """Decrypt each NAME.cred in directory into os.environ[NAME].

    A variable that is already set wins, so an explicit environment override
    still works. Failures are logged and skipped; values are never logged.

    Args:
        directory: Directory holding the .cred files.

    Returns:
        Names of the variables that were loaded.
    """
    credential_dir = Path(directory)
    if not credential_dir.is_dir():
        return []

    loaded = []
    for path in sorted(credential_dir.glob("*.cred")):
        name = path.stem
        if not CREDENTIAL_NAME_PATTERN.match(name):
            logger.warning(f"Skipping credential with invalid name: {path.name}")
            continue
        if name in os.environ:
            logger.info(f"{name} already set in the environment; skipping its credential")
            continue

        try:
            result = subprocess.run(
                ["systemd-creds", "decrypt", "--user", f"--name={name}", str(path), "-"],
                capture_output=True,
                timeout=DECRYPT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Could not run systemd-creds for {name}: {e}")
            continue

        if result.returncode != 0:
            error = result.stderr.decode(errors="replace").strip()
            logger.warning(f"Could not decrypt credential {name}: {error}")
            continue

        os.environ[name] = result.stdout.decode().strip()
        loaded.append(name)

    if loaded:
        logger.info(f"Loaded credentials: {', '.join(loaded)}")
    return loaded
