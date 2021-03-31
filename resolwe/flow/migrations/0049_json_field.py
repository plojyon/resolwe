# Generated by Django 3.1.5 on 2021-03-02 08:03

# Migrate from django.contrib.postgres.fields.JSONField to
# django.db.models.JSONField

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("flow", "0048_worker"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collection",
            name="descriptor",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="collection",
            name="settings",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="data",
            name="descriptor",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="data",
            name="input",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="data",
            name="output",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="datamigrationhistory",
            name="metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="descriptorschema",
            name="schema",
            field=models.JSONField(default=list),
        ),
        migrations.AlterField(
            model_name="entity",
            name="descriptor",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="entity",
            name="settings",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="process",
            name="input_schema",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="process",
            name="output_schema",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="process",
            name="requirements",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="process",
            name="run",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="processmigrationhistory",
            name="metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="secret",
            name="metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="storage",
            name="json",
            field=models.JSONField(),
        ),
    ]