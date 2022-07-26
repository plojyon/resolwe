from django.contrib.auth import get_user_model

from rest_framework import exceptions, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from resolwe.flow.models import Data, DescriptorSchema, Process

from .models import Observer


class ObservableMixin:
    def subscribe(self, request, pk=None, change_types=()):
        model = self.get_queryset().model

        if pk is not None:
            if not model.objects.filter_for_user(request.user).filter(pk=pk).exists():
                return Response({"error": "Item does not exist"}, status=400)

        for change_type in change_types:
            Observer.objects.get_or_create(
                table=model._meta.db_table,
                resource_pk=pk,
                change_type=change_type,
                session_id=request.query_params.get("session_id"),
                user=request.user,
            )
        return Response(f"Thank u for subscribing to {model.__name__} c:")

    # TODO: require auth, disable GET
    @action(detail=True, methods=["post"], url_path="subscribe")
    def subscribe_detail(self, request, pk=None):
        return self.subscribe(request, pk=pk, change_types=("UPDATE", "DELETE"))

    # TODO: require auth, disable GET
    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe_list(self, request):
        return self.subscribe(request, change_types=("CREATE", "DELETE"))

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
