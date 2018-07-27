# Generated by Django 2.0.7 on 2018-07-27 09:34

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('causes', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('access', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('logtype', models.CharField(choices=[('generic', 'Generic log entry'), ('usage', 'Generic usage access'), ('stripe', 'Stripe related event'), ('spacebucks', 'Spacebucks related event'), ('profile', 'Member profile edited'), ('interlock', 'Interlock related event'), ('door', 'Door related event'), ('email', 'Email send event'), ('admin', 'Generic admin event'), ('error', 'Some event that causes an error')], max_length=30, verbose_name='Type of action/event')),
                ('description', models.CharField(max_length=500, verbose_name='Description of action/event')),
                ('data', models.TextField(verbose_name='Extra data for debugging action/event')),
                ('date', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='MemberTypes',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=20, verbose_name='Member Type Name')),
                ('conditions', models.CharField(max_length=100, verbose_name='Membership Conditions')),
                ('cost', models.IntegerField(verbose_name='Monthly Cost')),
            ],
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password_reset_key', models.UUIDField(default=None, null=True)),
                ('password_reset_expire', models.DateTimeField(default=None, null=True)),
                ('state', models.CharField(choices=[('noob', 'New Member'), ('active', 'Active Member'), ('inactive', 'Inactive Member')], default='noob', max_length=8)),
                ('rfid', models.CharField(blank=True, max_length=20, null=True, unique=True, verbose_name='RFID Tag')),
                ('spacebucks_balance', models.FloatField(default=0.0)),
                ('stripe_customer_id', models.CharField(default='', max_length=100, null=True)),
                ('stripe_card_expiry', models.CharField(default='', max_length=10, null=True)),
                ('stripe_card_last_digits', models.CharField(default='', max_length=4, null=True)),
                ('causes', models.ManyToManyField(to='causes.Causes')),
                ('doors', models.ManyToManyField(blank=True, to='access.Doors')),
                ('member_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='member_type', to='profile.MemberTypes')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='UserEventLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('logtype', models.CharField(choices=[('generic', 'Generic log entry'), ('usage', 'Generic usage access'), ('stripe', 'Stripe related event'), ('spacebucks', 'Spacebucks related event'), ('profile', 'Member profile edited'), ('interlock', 'Interlock related event'), ('door', 'Door related event'), ('email', 'Email send event'), ('admin', 'Generic admin event'), ('error', 'Some event that causes an error')], max_length=30, verbose_name='Type of action/event')),
                ('description', models.CharField(max_length=500, verbose_name='Description of action/event')),
                ('data', models.TextField(verbose_name='Extra data for debugging action/event')),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete='User affected by action', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
