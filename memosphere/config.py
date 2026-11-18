# memosphere/config.py
# Global configuration for the Circle of Trust module.

# Role types used throughout the application
ROLE_FAMILY = "Family"
ROLE_CAREGIVER = "Caregiver"
ROLE_STUDY_BUDDY = "Study Buddy"
ROOMMATE = "Roommate"

VALID_ROLES = [ROLE_FAMILY, ROLE_CAREGIVER, ROLE_STUDY_BUDDY, ROOMMATE]

# Permission levels for routine access
PERMISSION_VIEW = "view"
PERMISSION_SHARE = "share"
PERMISSION_ADMIN = "admin"

# Default grace period in minutes (configurable)
DEFAULT_GRACE_PERIOD_MINUTES = 30

# Priority levels
PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_LOW = "Low"

VALID_PRIORITIES = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]