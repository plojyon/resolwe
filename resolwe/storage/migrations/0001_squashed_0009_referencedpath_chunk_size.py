# Generated by Django 3.1.7 on 2021-10-12 10:39

from django.db import migrations, models
import django.db.models.deletion
import django.db.models.manager


class Migration(migrations.Migration):

    replaces = [
        ("storage", "0001_initial"),
        ("storage", "0002_create_filestorage_objects"),
        ("storage", "0003_add_hash_fields_to_referenced_path"),
        ("storage", "0004_calculate_hashes"),
        ("storage", "0005_referencedpath_storage_locations"),
        ("storage", "0006_assign_referenced_paths"),
        ("storage", "0007_remove_referencedpath_file_storage"),
        ("storage", "0008_accesslog_cause"),
        ("storage", "0009_referencedpath_chunk_size"),
    ]

    dependencies = [
        ("flow", "0001_squashed_0043_full_text_search"),
    ]

    operations = [
        migrations.CreateModel(
            name="FileStorage",
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
                ("created", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="StorageLocation",
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
                ("url", models.CharField(max_length=60)),
                ("connector_name", models.CharField(max_length=30)),
                ("last_update", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PR", "Preparing"),
                            ("UP", "Uploading"),
                            ("OK", "Done"),
                            ("DE", "Deleting"),
                        ],
                        default="PR",
                        max_length=2,
                    ),
                ),
                (
                    "file_storage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="storage_locations",
                        to="storage.filestorage",
                    ),
                ),
            ],
            options={
                "unique_together": {("url", "connector_name")},
            },
            managers=[
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="ReferencedPath",
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
                ("path", models.TextField(db_index=True)),
                ("size", models.BigIntegerField(default=-1)),
                ("md5", models.CharField(max_length=32)),
                ("crc32c", models.CharField(max_length=8)),
                ("awss3etag", models.CharField(max_length=50)),
                ("chunk_size", models.IntegerField(default=8388608)),
                (
                    "storage_locations",
                    models.ManyToManyField(
                        related_name="files", to="storage.StorageLocation"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AccessLog",
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
                ("started", models.DateTimeField(auto_now_add=True)),
                ("finished", models.DateTimeField(blank=True, null=True)),
                ("reason", models.CharField(max_length=120)),
                (
                    "cause",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_logs",
                        to="flow.data",
                    ),
                ),
                (
                    "storage_location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_logs",
                        to="storage.storagelocation",
                    ),
                ),
            ],
        ),
    ]