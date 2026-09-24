"""Tests for loading API keys from systemd user credentials."""

import logging
import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from council.credentials import load_credentials

SECRET = "sk-test-secret-value"


def decrypted(value: str = SECRET, returncode: int = 0, stderr: bytes = b"") -> Mock:
    """A subprocess.run result for systemd-creds decrypt."""
    return Mock(returncode=returncode, stdout=f"{value}\n".encode(), stderr=stderr)


@pytest.fixture
def cred_dir(tmp_path):
    """A credentials directory holding one valid credential file."""
    (tmp_path / "OPENROUTER_API_KEY.cred").write_bytes(b"ciphertext")
    return tmp_path


@pytest.fixture(autouse=True)
def clean_env():
    """Start without the variables these tests load, and restore the environment after."""
    with patch.dict(os.environ):
        for name in ("OPENROUTER_API_KEY", "ZAI_CODING_API_KEY"):
            os.environ.pop(name, None)
        yield


class TestLoadCredentials:
    """Tests for load_credentials()."""

    @patch("council.credentials.subprocess.run")
    def test_loads_decrypted_value_into_environment(self, mock_run, cred_dir):
        """Test a credential file becomes an environment variable."""
        mock_run.return_value = decrypted()

        loaded = load_credentials(str(cred_dir))

        assert loaded == ["OPENROUTER_API_KEY"]
        assert os.environ["OPENROUTER_API_KEY"] == SECRET
        args = mock_run.call_args[0][0]
        assert args[:4] == ["systemd-creds", "decrypt", "--user", "--name=OPENROUTER_API_KEY"]

    @patch("council.credentials.subprocess.run")
    def test_existing_environment_variable_wins(self, mock_run, cred_dir, monkeypatch):
        """Test an explicitly set variable is not replaced."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "explicit")

        loaded = load_credentials(str(cred_dir))

        assert loaded == []
        mock_run.assert_not_called()
        assert os.environ["OPENROUTER_API_KEY"] == "explicit"

    @patch("council.credentials.subprocess.run")
    def test_skips_invalid_names(self, mock_run, tmp_path):
        """Test files whose names aren't environment-variable names are ignored."""
        (tmp_path / "lowercase.cred").write_bytes(b"x")
        (tmp_path / "BAD-NAME.cred").write_bytes(b"x")

        assert load_credentials(str(tmp_path)) == []
        mock_run.assert_not_called()

    @patch("council.credentials.subprocess.run")
    def test_decrypt_failure_is_logged_and_skipped(self, mock_run, cred_dir, caplog):
        """Test one failed credential doesn't stop the others."""
        (cred_dir / "ZAI_CODING_API_KEY.cred").write_bytes(b"ciphertext")
        mock_run.side_effect = [
            decrypted(returncode=1, stderr=b"Failed to decrypt"),
            decrypted("zai-secret"),
        ]

        with caplog.at_level(logging.WARNING):
            loaded = load_credentials(str(cred_dir))

        assert loaded == ["ZAI_CODING_API_KEY"]
        assert "Could not decrypt credential OPENROUTER_API_KEY" in caplog.text

    @patch("council.credentials.subprocess.run")
    def test_missing_systemd_creds_is_skipped(self, mock_run, cred_dir):
        """Test a machine without systemd-creds loads nothing and doesn't crash."""
        mock_run.side_effect = FileNotFoundError("systemd-creds")

        assert load_credentials(str(cred_dir)) == []

    @patch("council.credentials.subprocess.run")
    def test_timeout_is_skipped(self, mock_run, cred_dir):
        """Test a hung decrypt is abandoned."""
        mock_run.side_effect = subprocess.TimeoutExpired("systemd-creds", 20)

        assert load_credentials(str(cred_dir)) == []

    def test_missing_directory_loads_nothing(self, tmp_path):
        """Test a machine without a credentials directory is fine."""
        assert load_credentials(str(tmp_path / "absent")) == []

    @patch("council.credentials.subprocess.run")
    def test_value_never_logged(self, mock_run, cred_dir, caplog):
        """Test the decrypted value doesn't reach the logs."""
        mock_run.return_value = decrypted()

        with caplog.at_level(logging.DEBUG):
            load_credentials(str(cred_dir))

        assert "OPENROUTER_API_KEY" in caplog.text
        assert SECRET not in caplog.text
