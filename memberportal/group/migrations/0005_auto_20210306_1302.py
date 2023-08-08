# Generated by Django 3.1.4 on 2021-03-06 03:02

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("group", "0004_auto_20210102_1536"),
    ]

    operations = [
        migrations.AlterField(
            model_name="group",
            name="description",
            field=models.CharField(max_length=100, verbose_name="Group Description"),
        ),
        migrations.AlterField(
            model_name="group",
            name="name",
            field=models.CharField(
                max_length=20, unique=True, verbose_name="Group Name"
            ),
        ),
    ]
