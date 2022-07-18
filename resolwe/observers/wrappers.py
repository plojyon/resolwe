from django.db import models
from .protocol import (
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
    GROUP_SESSIONS,
    TYPE_ITEM_UPDATE,
    TYPE_PERM_UPDATE,
)
from django.db import models
from django.db.models import Q
from .models import Observer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def get_observers(self, table, pk=None):
    """Find all observers watching for changes of a given item/table."""
    query = Q(table=table, change_type=CHANGE_TYPE_CREATE)
    query &= Q(resource_pk=pk) | Q(resource_pk__isnull=True)
    return list(Observer.objects.filter(query))


def observable_queryset(fallback=models.QuerySet):
    class ObservableQuerySet(fallback):
        """All observable models' querysets must inherit from this."""

        def create(self, *args, **kwargs):
            created = super().create(*args, **kwargs)

            # The message to be sent to observers.
            message = {
                "type": TYPE_ITEM_UPDATE,
                "table": created._meta.db_table,
                "type_of_change": CHANGE_TYPE_CREATE,
                "primary_key": str(created.pk),
                "app_label": created._meta.app_label,
                "model_name": created._meta.object_name,
            }

            observers = _get_observers(created._meta.db_table, created.pk)

            # Forward the message to the appropriate groups.
            channel_layer = get_channel_layer()
            for observer in observers:
                group = GROUP_SESSIONS.format(session_id=observer.session_id)
                async_to_sync(channel_layer.send)(group, message)

            return created

        def delete(self, *args, **kwargs):
            """TODO: Handle mass deletion."""
            super().delete(*args, **kwargs)

        def update(self, *args, **kwargs):
            """TODO: Handle mass updation."""
            super().update(*args, **kwargs)

    return ObservableQuerySet


def observed_save(old_method):
    """Wrapper for a save method that sends a signal to interested observers."""

    def wrapped(self, *args, **kwargs):
        saved = old_method(self, *args, **kwargs)
        print("saving", self)
        # The message to be sent to observers.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": self._meta.db_table,
            "type_of_change": CHANGE_TYPE_UPDATE,
            "primary_key": str(self.pk),
            "app_label": self._meta.app_label,
            "model_name": self._meta.object_name,
        }

        observers = _get_observers(self._meta.db_table, self.pk)

        # Forward the message to the appropriate groups.
        channel_layer = get_channel_layer()
        for observer in observers:
            group = GROUP_SESSIONS.format(session_id=observer.session_id)
            async_to_sync(channel_layer.send)(group, message)
        print("sent update")
        return saved

    return wrapped


def observed_create(old_method):
    def wrapped(self, *args, **kwargs):
        created = old_method(*args, **kwargs)

        # The message to be sent to observers.
        message = {
            "type": TYPE_ITEM_UPDATE,
            "table": created._meta.db_table,
            "type_of_change": CHANGE_TYPE_CREATE,
            "primary_key": str(created.pk),
            "app_label": created._meta.app_label,
            "model_name": created._meta.object_name,
        }

        observers = _get_observers(created._meta.db_table, created.pk)

        # Forward the message to the appropriate groups.
        channel_layer = get_channel_layer()
        for observer in observers:
            group = GROUP_SESSIONS.format(session_id=observer.session_id)
            async_to_sync(channel_layer.send)(group, message)

        return created

    return wrapped


def observable_queryset(qs):
    methods = dict(qs.__dict__)
    old_create = methods.pop("create")
    methods["create"] = observed_create(old_create)
    return type.__new__(type(qs), qs.__name__, qs.__bases__, methods)


def observable(cls):
    """Make a class observable."""

    setattr(cls, "save", observed_save(cls.save))
    return cls
    # methods = dict(cls.__dict__)
    # old_save = methods.pop("save")
    # methods["save"] = observed_save(old_save)
    # return type.__new__(type(cls), cls.__name__, cls.__bases__, methods)

    # return type(cls)(cls.__name__, cls.__bases__, cls.__dict__)
    # {"save": lambda self: self, **cls.__dict__},

    # class Observable(cls):
    #     def save(self, *args, **kwargs):
    #         # The message to be sent to observers.
    #         message = {
    #             "type": TYPE_ITEM_UPDATE,
    #             "table": self._meta.db_table,
    #             "type_of_change": CHANGE_TYPE_UPDATE,
    #             "primary_key": str(self.pk),
    #             "app_label": self._meta.app_label,
    #             "model_name": self._meta.object_name,
    #         }
    #
    #         observers = _get_observers(self._meta.db_table, self.pk)
    #
    #         # Forward the message to the appropriate groups.
    #         channel_layer = get_channel_layer()
    #         for observer in observers:
    #             group = GROUP_SESSIONS.format(session_id=observer.session_id)
    #             async_to_sync(channel_layer.send)(group, message)
    #
    #         saved = super().save(self, *args, **kwargs)
    #         return saved
    #
    # return Observable
