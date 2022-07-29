"""Mixins for Observable ViewSets."""
import json

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Observer, Subscription
from .protocol import CHANGE_TYPE_CREATE, CHANGE_TYPE_DELETE, CHANGE_TYPE_UPDATE


class ObservableMixin:
    """A Mixin to make a model ViewSet observable.

    Adds the /subscribe and /unsubscribe endpoints to the list view.
    """

    def _id_exists_for_user(self, id, user):
        return self.get_queryset().filter_for_user(user).filter(pk=id).exists()

    @action(detail=False, methods=["post", "get"])
    def subscribe(self, request):
        """Register an Observer for a resource."""
        ids = dict(request.query_params).get("ids", [None])
        session_id = request.query_params.get("session_id")
        if ids == [None]:
            change_types = (CHANGE_TYPE_CREATE,)
        else:
            change_types = (CHANGE_TYPE_UPDATE, CHANGE_TYPE_DELETE)

            # Verify all ids exists and user has permissions to view them.
            for id in ids:
                if not self._id_exists_for_user(id, request.user):
                    resp = json.dumps({"error": f"Item {id} does not exist"})
                    return Response(resp, status=status.HTTP_400_BAD_REQUEST)

        table = self.get_queryset().model._meta.db_table
        subscription = Subscription.objects.create(
            user=request.user, session_id=session_id
        )
        subscription.subscribe(table, ids, change_types)
        return Response(subscription.subscription_id)

    @action(detail=False, methods=["post"])
    def unsubscribe(self, request):
        """Unregister a subscription."""
        subscription_id = request.query_params.get("subscription_id", None)
        subscriptions = Subscription.objects.filter(pk=subscription_id)

        if subscriptions.count() != 1:
            resp = json.dumps({"error": "Invalid subscription_id"})
            return Response(resp, status=status.HTTP_400_BAD_REQUEST)

        subscriptions.first().delete()
        return Response()
