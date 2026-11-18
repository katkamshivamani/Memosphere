# memosphere/utils/decorators.py
# Permission‑dependent decorators for Streamlit functions.

from functools import wraps
import streamlit as st


def role_required(allowed_roles):
    """Decorator that restricts a Streamlit function to users whose role is in allowed_roles."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Retrieve the current user from session state
            user = st.session_state.get("current_user")
            if user is None:
                st.error("Please log in to access this page.")
                st.stop()
            if user.role not in allowed_roles:
                st.error("You do not have permission to access this page.")
                st.stop()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def permission_routine(routine, allowed_actions=("view",)):
    """Decorator that checks per‑routine permission for the current user.

    Parameters
    ----------
    routine : Routine
        The routine instance to check permission against.
    allowed_actions : tuple of str
        Actions that are permitted (e.g., ("view", "share")).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = st.session_state.get("current_user")
            if user is None:
                st.error("Please log in.")
                st.stop()
            from memosphere.services.permission_service import check_permission
            if not check_permission(user, routine, action=allowed_actions[0]):
                st.error("You do not have permission to perform this action on this routine.")
                st.stop()
            return func(*args, **kwargs)
        return wrapper
    return decorator