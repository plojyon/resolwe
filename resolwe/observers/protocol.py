"""Constants used for Observer communication."""

# Group used for individual sessions.
GROUP_SESSIONS = "observers.session.{session_id}"

# Message type for observer item updates.
TYPE_ITEM_UPDATE = "observers.item_update"
# Message type for when the channel is clogged
TYPE_CHANNEL_OVERFILL = "observers.channel_overfill"

# Types of database changes.
CHANGE_TYPE_CREATE = "CREATE"
CHANGE_TYPE_UPDATE = "UPDATE"
CHANGE_TYPE_DELETE = "DELETE"
