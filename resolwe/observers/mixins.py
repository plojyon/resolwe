from django.contrib.auth import get_user_model

from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from resolwe.flow.models import Data, DescriptorSchema, Process

from .models import Observer


class ObservableMixin:
    def subscribe(self, request, pk=None, change_types=()):
        """Register an Observer for a resource."""
        model = self.get_queryset().model

        if pk is not None:
            if not model.objects.filter_for_user(request.user).filter(pk=pk).exists():
                resp = {"error": "Item does not exist"}
                return Response(resp, status=status.HTTP_400_BAD_REQUEST)

        subscription_ids = []
        for change_type in change_types:
            observer, _ = Observer.objects.get_or_create(
                table=model._meta.db_table,
                resource_pk=pk,
                change_type=change_type,
                session_id=request.query_params.get("session_id"),
                user=request.user,
            )
            subscription_ids.append(observer.subscription_id)
        return Response(str(subscription_ids))

    @action(detail=True, methods=["post"], url_path="subscribe")
    def subscribe_detail(self, request, pk=None):
        """Subscribe to changes of a specific model instance."""
        return self.subscribe(request, pk=pk, change_types=("UPDATE", "DELETE"))

    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe_list(self, request):
        """Subscribe to creations and deletions of a specific model."""
        return self.subscribe(request, change_types=("CREATE", "DELETE"))

    def unsubscribe(self, subscription_id=None):
        """Unregister a subscription."""
        if subscription_id is None:
            resp = {"error": "Missing subscription_id"}
            return Response(resp, status=status.HTTP_400_BAD_REQUEST)
        Observer.objects.filter(subscription_id=subscription_id).delete()
        return Response()

    @action(detail=True, methods=["post"], url_path="unsubscribe")
    def unsubscribe_detail(self, request, pk=None):
        """Unregister a subscription."""
        return self.unsubscribe(request.query_params.get("subscription_id", None))

    @action(detail=False, methods=["post"], url_path="unsubscribe")
    def unsubscribe_list(self, request):
        """Unregister a subscription."""
        return self.unsubscribe(request.query_params.get("subscription_id", None))
