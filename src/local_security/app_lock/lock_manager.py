"""
Application Lock Manager enforcing automatic inactivity lock, manual lock, and secure state transitions.
"""
import contextlib
import threading
import time
from collections.abc import Callable
from enum import StrEnum

from local_security.app_lock.session_manager import ActiveSession, SessionManager
from local_security.core.configuration import LockConfig


class LockState(StrEnum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class ApplicationLockManager:
    """
    Orchestrates application locking lifecycle.
    Monitors user inactivity, responds to window focus/minimize events, and
    notifies listeners when transitioning between locked and unlocked states.
    """

    def __init__(self, lock_config: LockConfig | None = None, session_manager: SessionManager | None = None):
        self.config = lock_config or LockConfig()
        self.session_manager = session_manager or SessionManager(self.config.inactivity_timeout_seconds)
        self._lock = threading.RLock()
        self._state = LockState.LOCKED if self.config.lock_on_restart else LockState.UNLOCKED
        self._listeners: list[Callable[[LockState], None]] = []
        self._last_user_activity = time.time()
        self._monitor_active = False
        self._monitor_thread: threading.Thread | None = None

    @property
    def is_locked(self) -> bool:
        with self._lock:
            # Check if session has expired
            if self._state == LockState.UNLOCKED and not self.session_manager.has_active_session:
                self._state = LockState.LOCKED
            return self._state == LockState.LOCKED

    def register_state_listener(self, listener: Callable[[LockState], None]) -> None:
        """Registers a callback invoked whenever the application locks or unlocks."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def _notify_listeners(self, state: LockState) -> None:
        for callback in self._listeners:
            with contextlib.suppress(Exception):
                callback(state)

    def record_user_activity(self) -> None:
        """Invoked on user input (keypress, mouse move, touch) to refresh idle timer."""
        with self._lock:
            self._last_user_activity = time.time()
            if self._state == LockState.UNLOCKED and self.session_manager.has_active_session:
                try:
                    self.session_manager.touch()
                except Exception:
                    self.lock_application(reason="session_expired")

    def check_inactivity(self) -> bool:
        """
        Evaluates elapsed time against configured timeout.
        Returns True if application was locked due to inactivity.
        """
        with self._lock:
            if self._state == LockState.UNLOCKED:
                idle_seconds = time.time() - self._last_user_activity
                if idle_seconds >= self.config.inactivity_timeout_seconds:
                    self.lock_application(reason="inactivity")
                    return True
            return False

    def lock_application(self, reason: str = "manual") -> None:
        """Locks application, clears session, and notifies UI."""
        with self._lock:
            if self._state != LockState.LOCKED:
                self._state = LockState.LOCKED
                self.session_manager.invalidate_session()
                self._notify_listeners(LockState.LOCKED)

    def unlock_application(self, session: ActiveSession) -> None:
        """Unlocks application with verified authenticated session."""
        with self._lock:
            self._state = LockState.UNLOCKED
            self._last_user_activity = time.time()
            self._notify_listeners(LockState.UNLOCKED)

    def on_window_minimized(self) -> None:
        """Invoked when desktop window is minimized."""
        if self.config.lock_on_minimize:
            self.lock_application(reason="window_minimized")

    def on_window_focus_lost(self) -> None:
        """Invoked when desktop window loses focus."""
        if self.config.lock_on_focus_loss:
            self.lock_application(reason="focus_lost")

    def start_background_idle_monitor(self, poll_interval_seconds: float = 1.0) -> None:
        """Starts a lightweight daemon thread to monitor inactivity."""
        with self._lock:
            if self._monitor_active:
                return
            self._monitor_active = True

            def _monitor_loop():
                while self._monitor_active:
                    time.sleep(poll_interval_seconds)
                    self.check_inactivity()

            self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="IdleLockMonitor")
            self._monitor_thread.start()

    def stop_background_idle_monitor(self) -> None:
        """Stops the idle monitoring thread."""
        with self._lock:
            self._monitor_active = False
            self._monitor_thread = None
