"""Constants used for Observer communication."""

# Group used for individual sessions.
GROUP_SESSIONS = "observers.session.{session_id}"

# Message type for observer item updates.
TYPE_ITEM_UPDATE = "observers.item_update"

# Types of database changes.
CHANGE_TYPE_CREATE = "CREATE"
CHANGE_TYPE_UPDATE = "UPDATE"
CHANGE_TYPE_DELETE = "DELETE"

# Throttle constants
THROTTLE_CACHE_PREFIX = "resolwe_observer_throttle_"
THROTTLE_SEMAPHORE_DELAY = "delay"
THROTTLE_SEMAPHORE_EVALUATE = "evaluate"
THROTTLE_SEMAPHORE_IGNORE = "ignore"


def throttle_cache_key(observer_id):
    return "{}{}".format(THROTTLE_CACHE_PREFIX, observer_id)
