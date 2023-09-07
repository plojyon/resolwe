"""Entity viewset."""
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F, Func, OuterRef, Prefetch, Subquery
from django.db.models.functions import Coalesce

from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.response import Response

from resolwe.flow.filters import EntityFilter
from resolwe.flow.models import AnnotationValue, Data, DescriptorSchema, Entity
from resolwe.flow.models.annotations import AnnotationField, HandleMissingAnnotations
from resolwe.flow.serializers import EntitySerializer
from resolwe.flow.serializers.annotations import (
    AnnotationsSerializer,
    AnnotationValueSerializer,
)
from resolwe.observers.mixins import ObservableMixin
from resolwe.observers.views import BackgroundTaskSerializer
from resolwe.process.descriptor import ValidationError

from .collection import BaseCollectionViewSet
from .utils import get_collection_for_user


class EntityViewSet(ObservableMixin, BaseCollectionViewSet):
    """API view for entities."""

    serializer_class = EntitySerializer
    filterset_class = EntityFilter
    qs_descriptor_schema = DescriptorSchema.objects.select_related("contributor")

    data_count_subquery = (
        Data.objects.filter(entity_id=OuterRef("pk"))
        .annotate(count=Func(F("id"), function="Count"))
        .values("count")
    )
    data_status_subquery = (
        Data.objects.filter(entity_id=OuterRef("pk"))
        .annotate(
            count=Coalesce(
                Func(
                    F("status"),
                    function="ARRAY_AGG",
                    template="%(function)s(DISTINCT %(expressions)s)",
                ),
                [],
            )
        )
        .values("count")
    )
    queryset = (
        Entity.objects.select_related("contributor", "descriptor_schema__contributor")
        .prefetch_related(
            Prefetch("collection", queryset=BaseCollectionViewSet.queryset)
        )
        .annotate(data_statuses=Subquery(data_status_subquery))
        .annotate(data_count=Subquery(data_count_subquery))
    )

    def order_queryset(self, queryset):
        """Order queryset by annotation values.

        The format of the ordering field is annotations__field_id, possibly prefixed by
        a minus sign. The minus sign indicates descending order.
        """
        if ordering := self.request.query_params.get("ordering"):
            order_by = []
            regex = re.compile(r"-?annotations__(?P<field_id>\d+)")
            fields = [field.strip() for field in ordering.split(",")]
            for match in filter(None, map(regex.match, fields)):
                field_id = match.group("field_id")
                # Always filter by user-visible attribute annotation_label.
                annotation_value = AnnotationValue.objects.filter(
                    entity_id=OuterRef("pk"), field_id=field_id
                ).values("_value__label")
                annotate = {f"_order_{field_id}": Subquery(annotation_value)}
                queryset = queryset.annotate(**annotate)
                sign = "-" if match.string.startswith("-") else ""
                order_by.append(f"{sign}_order_{field_id}")
            if order_by:
                queryset = queryset.order_by(*order_by)
        return queryset

    def filter_queryset(self, queryset):
        """Filter queryset."""
        # First apply the default filters.
        queryset = super().filter_queryset(queryset)
        # Order by annotation values if required.
        return self.order_queryset(queryset)

    def _get_entities(self, user, ids):
        """Return entities queryset based on provided entity ids."""
        queryset = Entity.objects.filter(id__in=ids).filter_for_user(user)
        actual_ids = queryset.values_list("id", flat=True)
        missing_ids = list(set(ids) - set(actual_ids))
        if missing_ids:
            raise exceptions.ParseError(
                "Entities with the following ids not found: {}".format(
                    ", ".join(map(str, missing_ids))
                )
            )

        return queryset

    @action(detail=False, methods=["post"])
    def move_to_collection(self, request, *args, **kwargs):
        """Move samples from source to destination collection.

        The request accepts argument 'handle_missing_annotations'.The possible
        values for it are 'ADD' and 'REMOVE'. When 'REMOVE' is set without
        arguments the 'confirm_annotations_delete' argument must be set to
        True.

        :raises ValidationError: when handle_missing_annotations has incorrect
            value.
        :raises ValidationError: when handle_missing_annotations is set to
            'REMOVE' and 'confirm_annotations_delete' is set.
        """

        ids = self.get_ids(request.data)
        dst_collection_id = self.get_id(request.data, "destination_collection")
        dst_collection = get_collection_for_user(dst_collection_id, request.user)
        entity_qs = self._get_entities(request.user, ids)

        missing_annotations = {
            entity: AnnotationField.objects.filter(collection=entity.collection)
            .exclude(collection=dst_collection)
            .distinct()
            for entity in entity_qs
        }

        if missing_annotations:
            # How to handle annotation fields present in the current collection
            # but missing in new one. We have two options:
            # - add (default): add the missing annotation fields to the new
            #   collection and keep the values.
            # - delete: remove the missing annotation values from the samples.
            #   This option requires explicit confirmation by 'confirm_remove'
            #   argument or exception with explanation is raised.
            try:
                handle_missing_annotations = HandleMissingAnnotations(
                    request.data.get(
                        "handle_missing_annotations", HandleMissingAnnotations.ADD.name
                    )
                )
            except ValueError:
                possible_values = HandleMissingAnnotations._member_names_
                raise ValidationError(
                    "Attribute 'handle_missing_annotations' must be one of "
                    f"{possible_values}."
                )

            if handle_missing_annotations == HandleMissingAnnotations.REMOVE:
                if request.data.get("confirm_annotations_remove", False) is not True:
                    raise ValidationError(
                        "All annotations not present in the target collection will be "
                        "removed. Set 'confirm_action' argument to 'True' to confirm."
                    )

        entity_qs.move_to_collection(dst_collection, handle_missing_annotations)
        return Response()

    # NOTE: This can be deleted when DRF will support select_for_update
    #       on updates and ResolweUpdateModelMixin will use it.
    #       https://github.com/encode/django-rest-framework/issues/4675
    def update(self, request, *args, **kwargs):
        """Update an entity.

        Original queryset produces a temporary database table whose rows
        cannot be selected for an update. As a workaround, we patch
        get_queryset function to return only Entity objects without
        additional data that is not needed for the update.
        """
        orig_get_queryset = self.get_queryset

        def patched_get_queryset():
            """Patched get_queryset method."""
            entity_ids = orig_get_queryset().values_list("id", flat=True)
            return Entity.objects.filter(id__in=entity_ids)

        self.get_queryset = patched_get_queryset

        resp = super().update(request, *args, **kwargs)

        self.get_queryset = orig_get_queryset
        return resp

    @action(detail=False, methods=["post"])
    def duplicate(self, request, *args, **kwargs):
        """Duplicate (make copy of) ``Entity`` models.

        The objects are duplicated in the background and the details of the background
        task handling the duplication are returned.
        """
        if not request.user.is_authenticated:
            raise exceptions.NotFound

        inherit_collection = request.data.get("inherit_collection", False)
        ids = self.get_ids(request.data)
        queryset = Entity.objects.filter(id__in=ids).filter_for_user(request.user)
        actual_ids = queryset.values_list("id", flat=True)
        missing_ids = list(set(ids) - set(actual_ids))
        if missing_ids:
            raise exceptions.ParseError(
                "Entities with the following ids not found: {}".format(
                    ", ".join(map(str, missing_ids))
                )
            )

        task = queryset.duplicate(
            contributor=request.user, inherit_collection=inherit_collection
        )
        serializer = BackgroundTaskSerializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def set_annotations(self, request, pk=None):
        """Add the given list of AnnotaitonFields to the given collection."""
        # No need to check for permissions, since post requires edit by default.
        entity = self.get_object()
        # Read and validate the request data.
        serializer = AnnotationsSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        annotations = [
            (entry["field"], entry["value"]) for entry in serializer.validated_data
        ]
        annotation_fields = [e[0] for e in annotations]
        # The following dict is a mapping from annotation field id to the annotation
        # value id.
        existing_annotations = dict(
            entity.annotations.filter(field__in=annotation_fields).values_list(
                "field_id", "id"
            )
        )

        validation_errors = []
        to_create = []
        to_update = []
        for field, value in annotations:
            annotation_id = existing_annotations.get(field.id)
            append_to = to_create if annotation_id is None else to_update
            annotation = AnnotationValue(
                entity_id=entity.id, field_id=field.id, value=value, id=annotation_id
            )
            try:
                annotation.validate()
            except DjangoValidationError as e:
                validation_errors += e
            append_to.append(annotation)

        if validation_errors:
            raise DjangoValidationError(validation_errors)

        with transaction.atomic():
            AnnotationValue.objects.bulk_create(to_create)
            AnnotationValue.objects.bulk_update(to_update, ["_value"])
        return Response()

    @action(detail=True, methods=["get"])
    def get_annotations(self):
        """Get the annotations on this sample."""
        entity = self.get_object()
        serializer = AnnotationValueSerializer(entity.annotations.all(), many=True)
        return Response(serializer.data)
