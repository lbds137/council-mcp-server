"""Tests for loading API keys from systemd user credentials."""

import fcntl
import logging
import os
import subprocess
import time
from unittest.mock import Mock, patch

import pytest

from council import credentials
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


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Keep the decrypt lock and stall marker out of the real runtime dir."""
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    return run / "council"


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
        # The server's stdin carries JSON-RPC; the child must not read from it
        assert mock_run.call_args[1]["stdin"] is subprocess.DEVNULL

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

    @patch("council.credentials.subprocess.run")
    def test_non_utf8_value_is_skipped(self, mock_run, cred_dir):
        """Test a credential that isn't text is skipped instead of stopping startup."""
        mock_run.return_value = Mock(returncode=0, stdout=b"\xff\xfe", stderr=b"")

        assert load_credentials(str(cred_dir)) == []
        assert "OPENROUTER_API_KEY" not in os.environ

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


ZAI_SECRET = "zai-test-secret-value"


@pytest.fixture
def bundle_dir(tmp_path):
    """A credentials directory holding the combined keys.cred."""
    (tmp_path / "keys.cred").write_bytes(b"ciphertext")
    return tmp_path


def bundle(text: str) -> Mock:
    """A decrypt result for keys.cred carrying NAME=value lines."""
    return Mock(returncode=0, stdout=text.encode(), stderr=b"")


class TestCombinedKeysFile:
    """keys.cred holds every key, so startup needs one decrypt."""

    @patch("council.credentials.subprocess.run")
    def test_one_decrypt_loads_every_key(self, mock_run, bundle_dir):
        """Test both keys load from a single systemd-creds call."""
        mock_run.return_value = bundle(
            f"OPENROUTER_API_KEY={SECRET}\nZAI_CODING_API_KEY={ZAI_SECRET}\n"
        )

        loaded = load_credentials(str(bundle_dir))

        assert loaded == ["OPENROUTER_API_KEY", "ZAI_CODING_API_KEY"]
        assert os.environ["ZAI_CODING_API_KEY"] == ZAI_SECRET
        assert mock_run.call_count == 1
        assert "--name=council-keys" in mock_run.call_args[0][0]

    @patch("council.credentials.subprocess.run")
    def test_old_per_key_file_is_not_decrypted_when_the_bundle_has_it(self, mock_run, bundle_dir):
        """Test a leftover NAME.cred costs no decrypt once keys.cred provides NAME."""
        (bundle_dir / "OPENROUTER_API_KEY.cred").write_bytes(b"old ciphertext")
        mock_run.return_value = bundle(f"OPENROUTER_API_KEY={SECRET}\n")

        load_credentials(str(bundle_dir))

        assert mock_run.call_count == 1
        assert os.environ["OPENROUTER_API_KEY"] == SECRET

    @patch("council.credentials.subprocess.run")
    def test_per_key_file_fills_a_name_the_bundle_lacks(self, mock_run, bundle_dir):
        """Test a NAME.cred still loads when keys.cred doesn't carry that name."""
        (bundle_dir / "ZAI_CODING_API_KEY.cred").write_bytes(b"ciphertext")
        mock_run.side_effect = [bundle(f"OPENROUTER_API_KEY={SECRET}\n"), decrypted(ZAI_SECRET)]

        loaded = load_credentials(str(bundle_dir))

        assert loaded == ["OPENROUTER_API_KEY", "ZAI_CODING_API_KEY"]
        assert os.environ["ZAI_CODING_API_KEY"] == ZAI_SECRET

    @patch("council.credentials.subprocess.run")
    def test_environment_beats_the_bundle(self, mock_run, bundle_dir, monkeypatch):
        """Test a variable set before startup isn't replaced by keys.cred."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "explicit")
        mock_run.return_value = bundle(f"OPENROUTER_API_KEY={SECRET}\nZAI_CODING_API_KEY=z\n")

        loaded = load_credentials(str(bundle_dir))

        assert loaded == ["ZAI_CODING_API_KEY"]
        assert os.environ["OPENROUTER_API_KEY"] == "explicit"

    @patch("council.credentials.subprocess.run")
    def test_value_containing_equals_is_kept_whole(self, mock_run, bundle_dir):
        """Test only the first = separates name from value."""
        mock_run.return_value = bundle("OPENROUTER_API_KEY=abc=def==\n")

        load_credentials(str(bundle_dir))

        assert os.environ["OPENROUTER_API_KEY"] == "abc=def=="

    @patch("council.credentials.subprocess.run")
    def test_malformed_lines_are_skipped_without_logging_them(self, mock_run, bundle_dir, caplog):
        """Test bad lines are reported by number only, since they may hold a key."""
        mock_run.return_value = bundle(
            f"{SECRET}\nlower_case={SECRET}\n\nOPENROUTER_API_KEY={SECRET}\n"
        )

        with caplog.at_level(logging.DEBUG):
            loaded = load_credentials(str(bundle_dir))

        assert loaded == ["OPENROUTER_API_KEY"]
        assert "malformed line 1" in caplog.text
        assert "malformed line 2" in caplog.text
        assert SECRET not in caplog.text

    @patch("council.credentials.subprocess.run")
    def test_bundle_decrypt_failure_falls_back_to_per_key_files(self, mock_run, bundle_dir, caplog):
        """Test a keys.cred that won't decrypt is logged, and per-key files still load."""
        (bundle_dir / "OPENROUTER_API_KEY.cred").write_bytes(b"ciphertext")
        mock_run.side_effect = [
            Mock(returncode=1, stdout=b"", stderr=b"TPM unavailable"),
            decrypted(),
        ]

        with caplog.at_level(logging.WARNING):
            loaded = load_credentials(str(bundle_dir))

        assert loaded == ["OPENROUTER_API_KEY"]
        assert "Could not decrypt credential keys.cred: TPM unavailable" in caplog.text


class TestTpmGuard:
    """Council processes take turns on the TPM and back off after a stalled decrypt."""

    @patch("council.credentials.subprocess.run")
    def test_timeout_marks_the_tpm_stalled_and_later_startups_skip_it(
        self, mock_run, bundle_dir, caplog
    ):
        """Test the startup after a timed-out decrypt doesn't queue another one."""
        mock_run.side_effect = subprocess.TimeoutExpired("systemd-creds", 20)
        assert load_credentials(str(bundle_dir)) == []

        with caplog.at_level(logging.WARNING):
            assert load_credentials(str(bundle_dir)) == []

        assert mock_run.call_count == 1
        assert "TPM is busy or stuck" in caplog.text

    @patch("council.credentials.subprocess.run")
    def test_stall_marker_expires(self, mock_run, bundle_dir, state_dir):
        """Test an old stall marker no longer blocks, and a success clears it."""
        state_dir.mkdir()
        marker = state_dir / "tpm-stalled"
        marker.touch()
        old = time.time() - credentials.STALL_BACKOFF_SECONDS - 1
        os.utime(marker, (old, old))
        mock_run.return_value = bundle(f"OPENROUTER_API_KEY={SECRET}\n")

        assert load_credentials(str(bundle_dir)) == ["OPENROUTER_API_KEY"]
        assert not marker.exists()

    @patch("council.credentials.subprocess.run")
    def test_missing_systemd_creds_does_not_mark_a_stall(self, mock_run, cred_dir, state_dir):
        """Test only a timeout counts as a stuck TPM."""
        mock_run.side_effect = FileNotFoundError("systemd-creds")

        load_credentials(str(cred_dir))

        assert not (state_dir / "tpm-stalled").exists()

    @patch("council.credentials.subprocess.run")
    def test_gives_up_when_another_process_holds_the_tpm(
        self, mock_run, bundle_dir, state_dir, monkeypatch, caplog
    ):
        """Test a startup waits a bounded time for the lock, then skips instead of piling on."""
        monkeypatch.setattr(credentials, "LOCK_WAIT_SECONDS", 0.2)
        state_dir.mkdir()
        with open(state_dir / "decrypt.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with caplog.at_level(logging.WARNING):
                assert load_credentials(str(bundle_dir)) == []

        mock_run.assert_not_called()
        assert "TPM is busy or stuck" in caplog.text

    @patch("council.credentials.subprocess.run")
    def test_lock_is_released_after_each_decrypt(self, mock_run, bundle_dir, monkeypatch):
        """Test back-to-back startups both decrypt."""
        monkeypatch.setattr(credentials, "LOCK_WAIT_SECONDS", 0.2)
        mock_run.return_value = bundle(f"OPENROUTER_API_KEY={SECRET}\n")

        load_credentials(str(bundle_dir))
        os.environ.pop("OPENROUTER_API_KEY")
        load_credentials(str(bundle_dir))

        assert mock_run.call_count == 2

    @patch("council.credentials.subprocess.run")
    def test_waiter_rechecks_the_marker_after_getting_the_lock(
        self, mock_run, bundle_dir, state_dir, monkeypatch
    ):
        """Test a startup that waited out a holder's timeout doesn't decrypt on the stuck TPM."""
        state_dir.mkdir()
        marker = state_dir / "tpm-stalled"
        real_acquire = credentials._acquire

        def acquire_after_holder_timed_out(lock):
            marker.touch()
            return real_acquire(lock)

        monkeypatch.setattr(credentials, "_acquire", acquire_after_holder_timed_out)

        assert load_credentials(str(bundle_dir)) == []
        mock_run.assert_not_called()

    @patch("council.credentials.subprocess.run")
    def test_unusable_lock_file_falls_back_to_an_unguarded_decrypt(
        self, mock_run, bundle_dir, state_dir
    ):
        """Test a lock that can't be opened costs the guard, not the keys."""
        state_dir.mkdir()
        (state_dir / "decrypt.lock").mkdir()  # open(..., "w") raises IsADirectoryError
        mock_run.return_value = bundle(f"OPENROUTER_API_KEY={SECRET}\n")

        assert load_credentials(str(bundle_dir)) == ["OPENROUTER_API_KEY"]

    @patch("council.credentials.subprocess.run")
    def test_marker_write_failure_is_not_fatal(self, mock_run, bundle_dir, monkeypatch):
        """Test a runtime dir that vanishes mid-decrypt doesn't crash startup."""
        mock_run.side_effect = subprocess.TimeoutExpired("systemd-creds", 20)
        monkeypatch.setattr(credentials.Path, "touch", Mock(side_effect=FileNotFoundError("gone")))

        assert load_credentials(str(bundle_dir)) == []
