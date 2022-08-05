"""Mixins for Observable ViewSets."""
import json

from django.contrib.contenttypes.models import ContentType

from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from .models import Subscription
from .protocol import CHANGE_TYPE_CREATE, CHANGE_TYPE_DELETE, CHANGE_TYPE_UPDATE


class ObservableMixin:
    """A Mixin to make a model ViewSet observable.

    Adds the /subscribe and /unsubscribe endpoints to the list view.
    """

    def user_has_permission(self, id, user):
        """Verify that an object exists for a given user."""
        return self.get_queryset().filter(pk=id).filter_for_user(user).exists()

    @action(detail=False, methods=["post"])
    def subscribe(self, request):
        """Register an Observer for a resource."""
        ids = dict(request.query_params).get("ids", None)
        session_id = request.query_params.get("session_id")
        content_type = ContentType.objects.get_for_model(self.get_queryset().model)
        subscription = Subscription.objects.create(
            user=request.user, session_id=session_id
        )

        if ids is None:
            # Subscribe to the whole table.
            subscription.subscribe(content_type, [None], (CHANGE_TYPE_CREATE,))
        else:
            # Verify all ids exists and user has permissions to view them.
            for id in ids:
                if not self.user_has_permission(id, request.user):
                    raise NotFound(f"Item {id} does not exist")

            change_types = (CHANGE_TYPE_UPDATE, CHANGE_TYPE_DELETE)
            subscription.subscribe(content_type, ids, change_types)

        resp = json.dumps({"subscription_id": subscription.subscription_id})
        return Response(resp)

    @action(detail=False, methods=["post"])
    def unsubscribe(self, request):
        """Unregister a subscription."""
        subscription_id = request.query_params.get("subscription_id", None)
        subscriptions = Subscription.objects.filter(
            pk=subscription_id, user=request.user
        )

        if subscriptions.count() != 1:
            raise NotFound(f"{subscription_id} is an invalid subscription_id")

        subscriptions.first().delete()
        return Response()
