# Channel used for routing tasks to appropriate groups.
CHANNEL_MAIN = "observers.main"
# Group used for individual sessions.
GROUP_SESSIONS = "observers.session.{session_id}"

# # Message type for ORM table change notifications.
# TYPE_ORM_NOTIFY = "observers.orm_notify"
# Message type for observer item updates.
TYPE_ITEM_UPDATE = "observers.item_update"
# Message type for observer permission updates.
TYPE_PERM_UPDATE = "observers.permission_update"

# Types of database changes
CHANGE_TYPE_CREATE = "create"
CHANGE_TYPE_UPDATE = "update"
CHANGE_TYPE_DELETE = "delete"
