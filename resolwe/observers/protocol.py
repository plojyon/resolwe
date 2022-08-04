"""Constants used for Observer communication."""
from django import dispatch

# Group used for individual sessions.
GROUP_SESSIONS = "observers.session.{session_id}"

# Message type for observer item updates.
TYPE_ITEM_UPDATE = "observers.item_update"

# Types of database changes.
CHANGE_TYPE_CREATE = "CREATE"
CHANGE_TYPE_UPDATE = "UPDATE"
CHANGE_TYPE_DELETE = "DELETE"

# Signal to be sent before and after PermissionObject.set_permission is called
# or before and after a PermissionObject's container is changed.
pre_permission_changed = dispatch.Signal(providing_args=["instance"])
post_permission_changed = dispatch.Signal(providing_args=["instance"])
