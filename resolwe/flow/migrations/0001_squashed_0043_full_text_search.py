# Generated by Django 3.1.7 on 2021-10-12 10:39

from django.conf import settings
from django.contrib.postgres.operations import CITextExtension, TrigramExtension
import django.contrib.postgres.fields
import django.contrib.postgres.fields.citext
import django.contrib.postgres.search
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import fernet_fields.fields
import resolwe.flow.models.fields
import uuid
import versionfield.fields


class Migration(migrations.Migration):

    replaces = [
        ("flow", "0001_squashed_0030_change_slug_field"),
        ("flow", "0002_set_process_owners"),
        ("flow", "0003_data_dependency_1"),
        ("flow", "0004_data_dependency_2"),
        ("flow", "0005_data_dependency_3"),
        ("flow", "0006_add_total_size"),
        ("flow", "0007_data_size"),
        ("flow", "0008_compute_size"),
        ("flow", "0009_make_size_mandatory"),
        ("flow", "0010_add_secret"),
        ("flow", "0011_preserve_parents"),
        ("flow", "0012_recreate_empty_parents"),
        ("flow", "0013_migration_history"),
        ("flow", "0014_track_resources"),
        ("flow", "0015_refactor_relations_1"),
        ("flow", "0016_refactor_relations_2"),
        ("flow", "0017_refactor_relations_3"),
        ("flow", "0018_process_is_active"),
        ("flow", "0019_relation_type_cicharfield"),
        ("flow", "0020_process_category_default"),
        ("flow", "0021_collection_tags"),
        ("flow", "0022_process_entity_1"),
        ("flow", "0023_process_entity_2"),
        ("flow", "0024_process_entity_3"),
        ("flow", "0025_entity_type"),
        ("flow", "0026_data_scheduled"),
        ("flow", "0027_data_purged"),
        ("flow", "0028_add_data_location"),
        ("flow", "0029_storage_m2m"),
        ("flow", "0030_add_data_duplicate"),
        ("flow", "0031_add_entity_duplicate"),
        ("flow", "0032_add_collection_duplicate"),
        ("flow", "0033_move_purged"),
        ("flow", "0034_callable_defaults"),
        ("flow", "0035_process_entity_new"),
        ("flow", "0036_add_m2o_fields"),
        ("flow", "0037_migrate_m2o"),
        ("flow", "0038_remove_m2m_fields"),
        ("flow", "0039_entity_collection_cascade"),
        ("flow", "0040_remove_entity_descriptor_completed"),
        ("flow", "0041_remove_download_perm"),
        ("flow", "0042_delete_obsolete_perms"),
        ("flow", "0043_full_text_search"),
    ]

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        CITextExtension(),
        TrigramExtension(),
        migrations.CreateModel(
            name="Collection",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                ("description", models.TextField(blank=True)),
                ("settings", models.JSONField(default=dict)),
                ("descriptor", models.JSONField(default=dict)),
                ("descriptor_dirty", models.BooleanField(default=False)),
                (
                    "tags",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        size=None,
                    ),
                ),
                ("search", django.contrib.postgres.search.SearchVectorField(null=True)),
                ("duplicated", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "permissions": (
                    ("view_collection", "Can view collection"),
                    ("edit_collection", "Can edit collection"),
                    ("share_collection", "Can share collection"),
                    ("owner_collection", "Is owner of the collection"),
                ),
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="Data",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "scheduled",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("started", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "finished",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("duplicated", models.DateTimeField(blank=True, null=True)),
                (
                    "checksum",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        validators=[
                            django.core.validators.RegexValidator(
                                code="invalid_checksum",
                                message="Checksum is exactly 40 alphanumerics",
                                regex="^[0-9a-f]{64}$",
                            )
                        ],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("UP", "Uploading"),
                            ("RE", "Resolving"),
                            ("WT", "Waiting"),
                            ("PP", "Preparing"),
                            ("PR", "Processing"),
                            ("OK", "Done"),
                            ("ER", "Error"),
                            ("DR", "Dirty"),
                        ],
                        default="RE",
                        max_length=2,
                    ),
                ),
                ("process_pid", models.PositiveIntegerField(blank=True, null=True)),
                ("process_progress", models.PositiveSmallIntegerField(default=0)),
                ("process_rc", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "process_info",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "process_warning",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "process_error",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        size=None,
                    ),
                ),
                ("input", models.JSONField(default=dict)),
                ("output", models.JSONField(default=dict)),
                ("size", models.BigIntegerField()),
                ("descriptor", models.JSONField(default=dict)),
                ("descriptor_dirty", models.BooleanField(default=False)),
                ("named_by_user", models.BooleanField(default=False)),
                (
                    "tags",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        size=None,
                    ),
                ),
                ("process_memory", models.PositiveIntegerField(default=0)),
                ("process_cores", models.PositiveSmallIntegerField(default=0)),
                ("search", django.contrib.postgres.search.SearchVectorField(null=True)),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="data",
                        to="flow.collection",
                    ),
                ),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("view_data", "Can view data"),
                    ("edit_data", "Can edit data"),
                    ("share_data", "Can share data"),
                    ("owner_data", "Is owner of the data"),
                ),
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="DescriptorSchema",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                ("description", models.TextField(blank=True)),
                ("schema", models.JSONField(default=list)),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("view_descriptorschema", "Can view descriptor schema"),
                    ("edit_descriptorschema", "Can edit descriptor schema"),
                    ("share_descriptorschema", "Can share descriptor schema"),
                    ("owner_descriptorschema", "Is owner of the description schema"),
                ),
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="Entity",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                ("description", models.TextField(blank=True)),
                ("settings", models.JSONField(default=dict)),
                ("descriptor", models.JSONField(default=dict)),
                ("descriptor_dirty", models.BooleanField(default=False)),
                (
                    "tags",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        size=None,
                    ),
                ),
                ("search", django.contrib.postgres.search.SearchVectorField(null=True)),
                (
                    "type",
                    models.CharField(
                        blank=True, db_index=True, max_length=100, null=True
                    ),
                ),
                ("duplicated", models.DateTimeField(blank=True, null=True)),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="flow.collection",
                    ),
                ),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "descriptor_schema",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="flow.descriptorschema",
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("view_entity", "Can view entity"),
                    ("edit_entity", "Can edit entity"),
                    ("share_entity", "Can share entity"),
                    ("owner_entity", "Is owner of the entity"),
                ),
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="Process",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "type",
                    models.CharField(
                        max_length=100,
                        validators=[
                            django.core.validators.RegexValidator(
                                code="invalid_type",
                                message="Type may be alphanumerics separated by colon",
                                regex="^data:[a-z0-9:]+:$",
                            )
                        ],
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        default="Other:",
                        max_length=200,
                        validators=[
                            django.core.validators.RegexValidator(
                                code="invalid_category",
                                message="Category may be alphanumerics separated by colon",
                                regex="^([a-zA-Z0-9]+[:\\-])*[a-zA-Z0-9]+:$",
                            )
                        ],
                    ),
                ),
                (
                    "persistence",
                    models.CharField(
                        choices=[("RAW", "Raw"), ("CAC", "Cached"), ("TMP", "Temp")],
                        default="RAW",
                        max_length=3,
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="active")),
                ("description", models.TextField(default="")),
                ("data_name", models.CharField(blank=True, max_length=200, null=True)),
                ("input_schema", models.JSONField(blank=True, default=list)),
                ("output_schema", models.JSONField(blank=True, default=list)),
                (
                    "entity_type",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                (
                    "entity_descriptor_schema",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                (
                    "entity_input",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("entity_always_create", models.BooleanField(default=False)),
                ("run", models.JSONField(default=dict)),
                ("requirements", models.JSONField(default=dict)),
                (
                    "scheduling_class",
                    models.CharField(
                        choices=[("IN", "Interactive"), ("BA", "Batch")],
                        default="BA",
                        max_length=2,
                    ),
                ),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("view_process", "Can view process"),
                    ("share_process", "Can share process"),
                    ("owner_process", "Is owner of the process"),
                ),
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="Relation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "category",
                    django.contrib.postgres.fields.citext.CICharField(max_length=100),
                ),
                (
                    "unit",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("s", "Second"),
                            ("min", "Minute"),
                            ("hr", "Hour"),
                            ("d", "Day"),
                            ("wk", "Week"),
                        ],
                        max_length=3,
                        null=True,
                    ),
                ),
                (
                    "collection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="flow.collection",
                    ),
                ),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("view_relation", "Can view relation"),
                    ("edit_relation", "Can edit relation"),
                    ("share_relation", "Can share relation"),
                    ("owner_relation", "Is owner of the relation"),
                ),
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="RelationType",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                ("ordered", models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name="Worker",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("started", models.DateTimeField(auto_now=True)),
                ("finished", models.DateTimeField(null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PR", "Processing data"),
                            ("NR", "Unresponsive"),
                            ("PP", "Preparing data"),
                            ("CM", "Finished"),
                        ],
                        max_length=2,
                    ),
                ),
                (
                    "data",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="worker",
                        to="flow.data",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Storage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    resolwe.flow.models.fields.ResolweSlugField(
                        max_length=100, populate_from="name", unique_with=("version",)
                    ),
                ),
                ("version", versionfield.fields.VersionField(default="0.0.0")),
                ("name", models.CharField(max_length=100)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                ("json", models.JSONField()),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "data",
                    models.ManyToManyField(related_name="storages", to="flow.Data"),
                ),
            ],
            options={
                "get_latest_by": "version",
                "abstract": False,
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="Secret",
            fields=[
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "handle",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("value", fernet_fields.fields.EncryptedTextField()),
                ("metadata", models.JSONField(default=dict)),
                ("expires", models.DateTimeField(db_index=True, null=True)),
                (
                    "contributor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RelationPartition",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(
                        blank=True, db_index=True, null=True
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        blank=True, db_index=True, max_length=30, null=True
                    ),
                ),
                (
                    "entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="flow.entity"
                    ),
                ),
                (
                    "relation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="flow.relation"
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="relation",
            name="entities",
            field=models.ManyToManyField(
                through="flow.RelationPartition", to="flow.Entity"
            ),
        ),
        migrations.AddField(
            model_name="relation",
            name="type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="flow.relationtype"
            ),
        ),
        migrations.CreateModel(
            name="ProcessMigrationHistory",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("migration", models.CharField(db_index=True, max_length=255)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("metadata", models.JSONField(default=dict)),
                (
                    "process",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="migration_history",
                        to="flow.process",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="DataMigrationHistory",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("migration", models.CharField(db_index=True, max_length=255)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("metadata", models.JSONField(default=dict)),
                (
                    "data",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="migration_history",
                        to="flow.data",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="DataDependency",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("io", "Input/output dependency"),
                            ("subprocess", "Subprocess"),
                            ("duplicate", "Duplicate"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parents_dependency",
                        to="flow.data",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children_dependency",
                        to="flow.data",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="data",
            name="descriptor_schema",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="flow.descriptorschema",
            ),
        ),
        migrations.AddField(
            model_name="data",
            name="entity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="data",
                to="flow.entity",
            ),
        ),
    ]