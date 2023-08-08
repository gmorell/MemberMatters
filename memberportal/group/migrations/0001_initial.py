# Generated by Django 3.0.10 on 2020-11-18 12:10

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Group",
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
                    "name",
                    models.CharField(
                        max_length=20, unique=True, verbose_name="Cause Name"
                    ),
                ),
                (
                    "description",
                    models.CharField(max_length=100, verbose_name="Cause Description"),
                ),
                (
                    "item_code",
                    models.CharField(max_length=50, verbose_name="Xero Item Code"),
                ),
                ("account_code", models.IntegerField(verbose_name="Xero Account Code")),
                ("hidden", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name": "Member Group",
                "verbose_name_plural": "Member Groups",
                "permissions": [("manage_member_groups", "Can manage member groups")],
            },
        ),
    ]
