"""Mixins for Observable ViewSets."""
import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from resolwe.flow.models import Data, DescriptorSchema, Process
from resolwe.permissions.models import Permission, get_anonymous_user

from .models import Subscription
from .protocol import CHANGE_TYPE_CREATE, CHANGE_TYPE_DELETE, CHANGE_TYPE_UPDATE
from resolwe.permissions.models import Permission, get_anonymous_user


class ObservableMixin:
    """A Mixin to make a model ViewSet observable.

    Adds the /subscribe and /unsubscribe endpoints to the list view.
    """

    def user_has_permission(self, id, user):
        """Verify that an object exists for a given user."""
        return self.get_queryset().filter_for_user(user).filter(pk=id).exists()

    @action(detail=False, methods=["post"])
    def subscribe(self, request):
        """Register an Observer for a resource."""
        ids = dict(request.query_params).get("ids", [None])
        session_id = request.query_params.get("session_id")
        request.user = get_user_model().objects.get(
            username="bobber3"
        )  # TODO: remove!!

        if ids == [None]:
            change_types = (CHANGE_TYPE_CREATE,)
        else:
            change_types = (CHANGE_TYPE_UPDATE, CHANGE_TYPE_DELETE)

            # Verify all ids exists and user has permissions to view them.
            for id in ids:
                if not self.user_has_permission(id, request.user):
                    raise NotFound(f"Item {id} does not exist")

        content_type = ContentType.objects.get_for_model(self.get_queryset().model)
        subscription = Subscription.objects.create(
            user=request.user, session_id=session_id
        )
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

    # TODO: remove!!!
    @action(detail=True, methods=["get"])
    def make_data(self, request, pk=None):
        try:
            user, _ = get_user_model().objects.get_or_create(
                username="bobber3",
                email="user@test.com",
                first_name="John",
                last_name="Williams",
            )
        except Exception as e:
            print("STAGE 1 FAILURE", e)

        try:
            process, _ = Process.objects.get_or_create(
                name="Dummy process", contributor=user
            )
        except Exception as e:
            print("STAGE 2 FAILURE", e)

        try:
            data, _ = Data.objects.get_or_create(
                pk=pk,
                name="Public data",
                slug=f"public-data{pk}",
                contributor=user,
                process=process,
                size=0,
            )
            data.set_permission(Permission.VIEW, get_anonymous_user())
        except Exception as e:
            print("STAGE 3 FAILURE", e)

        if Data.objects.filter(id=pk).filter_for_user(get_anonymous_user()).exists():
            print("VISIBILITY OK")
        else:
            print("VISIBILITY FAILED")
        serializer = self.get_serializer(data)
        return Response(serializer.data)

    # TODO: remove!!!
    @action(detail=False, methods=["get", "post"])
    def change(self, request):
        pk = request.query_params.get("ids")

        user = get_user_model().objects.get(username="bobber3")
        data = Data.objects.get(pk=pk)

        @transaction.atomic
        def alter(data, i):
            data.name = f"iter{i}"
            data.save()

        for i in range(10):
            alter(data, i)

        return Response()
