# Generated by Django 2.1.3 on 2020-02-21 19:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("codecov_auth", "0003_auto_20200221_1919"),
    ]

    operations = [
        migrations.AlterField(
            model_name="owner", name="free", field=models.SmallIntegerField(default=0),
        ),
    ]
