# Generated by Django 2.1.3 on 2020-12-18 00:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("codecov_auth", "0011_owner_plan_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="owner",
            name="parent_service_id",
            field=models.TextField(null=True),
        ),
    ]
