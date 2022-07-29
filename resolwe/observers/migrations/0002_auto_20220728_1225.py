# Generated by Django 3.2.14 on 2022-07-28 12:25

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import resolwe.observers.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('observers', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='observer',
            unique_together={('table', 'resource_pk', 'change_type')},
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('session_id', models.CharField(max_length=100)),
                ('subscription_id', models.CharField(default=resolwe.observers.models.get_random_hash, max_length=32, unique=True)),
                ('observers', models.ManyToManyField(to='observers.Observer')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RemoveField(
            model_name='observer',
            name='created',
        ),
        migrations.RemoveField(
            model_name='observer',
            name='session_id',
        ),
        migrations.RemoveField(
            model_name='observer',
            name='subscription_id',
        ),
        migrations.RemoveField(
            model_name='observer',
            name='user',
        ),
    ]
