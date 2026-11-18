"""
Unit tests for session management and application lock manager.
"""
import time

import pytest

from local_security.app_lock.lock_manager import ApplicationLockManager, LockState
from local_security.app_lock.session_manager import SessionManager
from local_security.core.configuration import LockConfig
from local_security.core.exceptions import SessionExpiredError


def test_session_lifecycle():
    sm = SessionManager(inactivity_timeout_seconds=2)
    assert not sm.has_active_session

    session = sm.create_session("u-1", "alice", "owner")
    assert sm.has_active_session
    assert session.username == "alice"
    assert sm.get_current_session().session_id == session.session_id

    # Touch session
    time.sleep(0.5)
    sm.touch()
    assert sm.has_active_session

    # Invalidate session
    sm.invalidate_session()
    assert not sm.has_active_session
    assert sm.get_current_session() is None


def test_session_inactivity_timeout():
    sm = SessionManager(inactivity_timeout_seconds=1)
    sm.create_session("u-timeout", "bob", "owner")
    assert sm.has_active_session

    # Wait for timeout
    time.sleep(1.2)
    assert not sm.has_active_session

    with pytest.raises(SessionExpiredError):
        sm.get_current_session()


def test_lock_manager_transitions_and_callbacks():
    cfg = LockConfig(inactivity_timeout_seconds=1, lock_on_restart=True)
    sm = SessionManager(cfg.inactivity_timeout_seconds)
    lock_mgr = ApplicationLockManager(cfg, sm)

    assert lock_mgr.is_locked

    state_transitions = []
    lock_mgr.register_state_listener(lambda s: state_transitions.append(s))

    # Unlock with session
    session = sm.create_session("u-1", "alice", "owner")
    lock_mgr.unlock_application(session)
    assert not lock_mgr.is_locked
    assert state_transitions == [LockState.UNLOCKED]

    # Manual lock
    lock_mgr.lock_application(reason="manual_test")
    assert lock_mgr.is_locked
    assert not sm.has_active_session
    assert state_transitions == [LockState.UNLOCKED, LockState.LOCKED]


def test_lock_manager_inactivity_detection():
    cfg = LockConfig(inactivity_timeout_seconds=1, lock_on_restart=False)
    sm = SessionManager(cfg.inactivity_timeout_seconds)
    lock_mgr = ApplicationLockManager(cfg, sm)

    session = sm.create_session("u-idle", "charlie", "owner")
    lock_mgr.unlock_application(session)
    assert not lock_mgr.is_locked

    # Before timeout
    assert not lock_mgr.check_inactivity()
    assert not lock_mgr.is_locked

    # Wait past timeout
    time.sleep(1.2)
    did_lock = lock_mgr.check_inactivity()
    assert did_lock is True
    assert lock_mgr.is_locked
