"""
Unit tests for PIN authentication, Argon2id hashing, lockout, and AuthenticationManager.
"""
from pathlib import Path

import pytest

from local_security.authentication.auth_manager import AuthenticationManager
from local_security.authentication.pin_auth import PINAuthenticator
from local_security.core.configuration import Argon2Config, LockConfig
from local_security.core.exceptions import InvalidCredentialsError, PINLockedError
from local_security.database.database_manager import DatabaseManager


@pytest.fixture
def pin_auth() -> PINAuthenticator:
    # Use fast argon2 parameters for unit testing speed
    a2_cfg = Argon2Config(time_cost=1, memory_cost=8192, parallelism=1)
    lock_cfg = LockConfig(max_failed_attempts=3, base_backoff_seconds=1.0)
    return PINAuthenticator(argon2_config=a2_cfg, lock_config=lock_cfg)


@pytest.fixture
def auth_mgr(tmp_path: Path) -> AuthenticationManager:
    db_path = tmp_path / "test_auth_vault.db"
    db = DatabaseManager(db_path)
    # 32 byte key
    db.connect(b"01234567890123456789012345678901")
    a2_cfg = Argon2Config(time_cost=1, memory_cost=8192, parallelism=1)
    lock_cfg = LockConfig(max_failed_attempts=3, base_backoff_seconds=1.0)
    pin_auth = PINAuthenticator(argon2_config=a2_cfg, lock_config=lock_cfg)
    return AuthenticationManager(db, pin_authenticator=pin_auth)


def test_pin_validation_policies(pin_auth: PINAuthenticator):
    # Too short
    valid, err = pin_auth.validate_pin_policy("123", min_length=6)
    assert not valid
    assert "at least 6" in err

    # Trivial PINs
    valid, err = pin_auth.validate_pin_policy("123456")
    assert not valid
    assert "too common" in err

    # Repeating digits (not in trivial list)
    valid, err = pin_auth.validate_pin_policy("7777777")
    assert not valid
    assert "repeating" in err

    # Valid non-trivial PIN
    valid, err = pin_auth.validate_pin_policy("839201")
    assert valid
    assert err is None


def test_pin_hash_and_verify(pin_auth: PINAuthenticator):
    user_id = "user-101"
    pin = "749204"
    pin_hash = pin_auth.create_pin_hash(pin, pin)
    assert pin_hash.startswith("$argon2id$")
    assert pin not in pin_hash

    # Verify correct PIN
    valid, needs_rehash = pin_auth.verify_pin(user_id, pin, pin_hash)
    assert valid is True

    # Verify incorrect PIN
    with pytest.raises(InvalidCredentialsError):
        pin_auth.verify_pin(user_id, "999998", pin_hash)


def test_pin_lockout_after_consecutive_failures(pin_auth: PINAuthenticator):
    user_id = "user-lockout"
    pin_hash = pin_auth.create_pin_hash("948201", "948201")

    # 1st failure
    with pytest.raises(InvalidCredentialsError):
        pin_auth.verify_pin(user_id, "111112", pin_hash)

    # 2nd failure
    with pytest.raises(InvalidCredentialsError):
        pin_auth.verify_pin(user_id, "111113", pin_hash)

    # 3rd failure reaches max_failed_attempts=3 -> PINLockedError
    with pytest.raises(PINLockedError) as exc_info:
        pin_auth.verify_pin(user_id, "111114", pin_hash)
    assert exc_info.value.retry_after_seconds > 0

    # Subsequent check while locked raises PINLockedError immediately
    with pytest.raises(PINLockedError):
        pin_auth.check_lockout(user_id)


def test_auth_manager_setup_and_login(auth_mgr: AuthenticationManager):
    assert not auth_mgr.is_setup_completed()

    user = auth_mgr.setup_initial_user(
        username="jane_doe",
        display_name="Jane Doe",
        pin="492018",
        confirm_pin="492018",
        enable_biometrics=False,
    )
    assert auth_mgr.is_setup_completed()
    assert user.username == "jane_doe"

    # Authenticate with correct PIN
    authenticated_user = auth_mgr.authenticate_with_pin("jane_doe", "492018")
    assert authenticated_user.user_id == user.user_id

    # Change PIN
    auth_mgr.change_pin(user.user_id, "492018", "681920", "681920")

    # Old PIN fails
    with pytest.raises(InvalidCredentialsError):
        auth_mgr.authenticate_with_pin("jane_doe", "492018")

    # New PIN succeeds
    reauth = auth_mgr.authenticate_with_pin("jane_doe", "681920")
    assert reauth.user_id == user.user_id
