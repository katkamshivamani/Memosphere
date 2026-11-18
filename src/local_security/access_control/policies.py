"""
Permission policies and role-based matrix definitions.
"""
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.users import UserRole

# Standard role-based access matrix
DEFAULT_ROLE_POLICIES: dict[UserRole, dict[SecurityModule, set[SecurityAction]]] = {
    # OWNER has full permissions on all modules
    UserRole.OWNER: {
        module: {
            SecurityAction.CREATE,
            SecurityAction.READ,
            SecurityAction.UPDATE,
            SecurityAction.DELETE,
            SecurityAction.EXPORT,
            SecurityAction.SHARE,
        }
        for module in SecurityModule
    },
    # CAREGIVER has read permissions, can log routines and activities, but cannot delete or export
    UserRole.CAREGIVER: {
        SecurityModule.PEOPLE: {SecurityAction.READ},
        SecurityModule.PLACES: {SecurityAction.READ},
        SecurityModule.MEMORIES: {SecurityAction.READ},
        SecurityModule.ACTIVITIES: {SecurityAction.READ, SecurityAction.CREATE},
        SecurityModule.ROUTINES: {SecurityAction.READ, SecurityAction.UPDATE},
        SecurityModule.CONVERSATIONS: {SecurityAction.READ},
        SecurityModule.CAREGIVER_DASHBOARD: {SecurityAction.READ, SecurityAction.CREATE, SecurityAction.UPDATE},
        SecurityModule.SYSTEM: set(),
    },
    # ACCOUNTABILITY_PARTNER has restricted read access to routines and activities
    UserRole.ACCOUNTABILITY_PARTNER: {
        SecurityModule.ROUTINES: {SecurityAction.READ},
        SecurityModule.ACTIVITIES: {SecurityAction.READ},
        SecurityModule.CAREGIVER_DASHBOARD: {SecurityAction.READ},
        SecurityModule.MEMORIES: set(),
        SecurityModule.PEOPLE: set(),
        SecurityModule.PLACES: set(),
        SecurityModule.CONVERSATIONS: set(),
        SecurityModule.SYSTEM: set(),
    },
    # GUEST has minimal read permissions
    UserRole.GUEST: {
        SecurityModule.PEOPLE: set(),
        SecurityModule.PLACES: set(),
        SecurityModule.MEMORIES: set(),
        SecurityModule.ACTIVITIES: set(),
        SecurityModule.ROUTINES: set(),
        SecurityModule.CONVERSATIONS: set(),
        SecurityModule.CAREGIVER_DASHBOARD: set(),
        SecurityModule.SYSTEM: set(),
    },
}
