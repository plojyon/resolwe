from django.contrib.auth import get_user_model

from rest_framework import exceptions, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from resolwe.flow.models import Data, DescriptorSchema, Process

from .models import Observer


class ObservableMixin:
    # TODO: require auth, support detail=False
    @action(detail=True, methods=["post", "get"])
    def subscribe(self, request, pk=None):
        model = self.get_queryset().model
        if pk is not None:
            for change in ("UPDATE", "DELETE"):
                Observer.objects.get_or_create(
                    table=model._meta.db_table,
                    resource_pk=pk,
                    change_type=change,
                    session_id=request.query_params.get("session_id"),
                    user=get_user_model().objects.get(pk=1),  # TODO:
                )
            return Response(f"Thank u for subscribing to {model.__name__} c:")
        else:
            return Response("Sorry :c")

    # def unsubscribe(self, request, pk=None):
    #     pass

    # @action(detail=False, methods=["get"])
    # def make_data(self, request, pk=None):
    #     user = get_user_model().objects.create(
    #         username="bobber3",
    #         email="user@test.com",
    #         first_name="John",
    #         last_name="Williams",
    #     )
    #     process = Process.objects.create(name="Dummy process", contributor=user)
    #     data = Data.objects.create(
    #         pk=1,
    #         name="Public data",
    #         slug="public-data2",
    #         contributor=user,
    #         process=process,
    #         size=0,
    #     )
    #     serializer = self.get_serializer(data)
    #     return Response(serializer.data)
