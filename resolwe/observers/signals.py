"""ORM signal handlers."""

from django import dispatch
from django.db.models import signals as model_signals

from resolwe.permissions.models import PermissionObject

from .models import Observer
from .protocol import ChangeType

# Global 'in migrations' flag to ignore signals during migrations.
# Signal handlers that access the database can crash the migration process.
IN_MIGRATIONS = False


@dispatch.receiver(model_signals.pre_migrate)
def model_pre_migrate(*args, **kwargs):
    """Set 'in migrations' flag."""
    global IN_MIGRATIONS
    IN_MIGRATIONS = True


@dispatch.receiver(model_signals.post_migrate)
def model_post_migrate(*args, **kwargs):
    """Clear 'in migrations' flag."""
    global IN_MIGRATIONS
    IN_MIGRATIONS = False


@dispatch.receiver(model_signals.post_save, sender=PermissionObject)
def observe_model_modification(
    sender: type, instance: PermissionObject, created: bool = False, **kwargs
):
    """Receive model updates."""

    # Create signals will be caught when the PermissionModel is added.
    if created:
        return

    if not IN_MIGRATIONS:
        Observer.observe_instance_changes(instance, ChangeType.UPDATE)


@dispatch.receiver(model_signals.pre_delete, sender=PermissionObject)
def observe_model_deletion(sender: type, instance: PermissionObject, **kwargs):
    """Receive model deletions."""
    if not IN_MIGRATIONS:
        Observer.observe_instance_changes(instance, ChangeType.DELETE)
