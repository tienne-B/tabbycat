from datetime import date
from subprocess import PIPE, Popen

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.models import DomainMixin, TenantMixin
from pytz import common_timezones


class Client(TenantMixin):
    CURRENCIES = (
        ('aud', _("Australian Dollar")),
        ('cad', _("Canadian Dollar")),
        ('eur', _("European Euro")),
        ('usd', _("United States Dollar")),
    )

    REGULAR_PLAN = 'r'
    PRO_PLAN = 'p'
    PLAN_CHOICES = (
        (REGULAR_PLAN, _("Regular")),
        (PRO_PLAN, _("Pro")),
    )

    user = models.ForeignKey(get_user_model(), models.PROTECT, blank=True, null=True)
    name = models.CharField(max_length=100,
        verbose_name=_("name"),
        help_text=_("The name for the site that will appear in the list of your sites."))
    archive = models.BooleanField(default=False)
    created_on = models.DateField(auto_now_add=True)
    end_date = models.DateField(auto_now_add=False, blank=True, null=True, verbose_name=_("end date"),
        help_text=_("The end date of the site's event. Tournament creation on the site will be disabled afterwards."))

    paid = models.IntegerField(default=0)  # In cents
    currency = models.CharField(max_length=3, choices=CURRENCIES, verbose_name=_("currency"), default='cad',
        help_text=_("Calico supports payment in various currencies to avoid conversion fees."))

    session_id = models.CharField(max_length=100, null=True, blank=True)
    payment_id = models.CharField(max_length=100, null=True, blank=True)

    timezone = models.CharField(
        max_length=len(max(common_timezones, key=len)),
        choices=((t, t) for t in common_timezones),
        default='Australia/Melbourne',  # From settings.TIME_ZONE
        verbose_name=_("time zone"),
        help_text=_("IANA time zone to use when showing times"))

    plan = models.CharField(max_length=1, choices=PLAN_CHOICES, default=REGULAR_PLAN, verbose_name=_("plan"))
    number_tournaments = models.PositiveIntegerField(default=1, verbose_name=_("number of tournaments"))

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = False
    auto_drop_schema = False

    def __str__(self):
        return "%s (%s)" % (self.name, self.schema_name)

    @property
    def is_archived(self):
        return self.archive or (self.end_date is not None and self.end_date < date.today())

    @property
    def is_pro(self):
        return self.plan == self.PRO_PLAN


class Instance(DomainMixin):
    pass


class Backup(models.Model):
    MAX_USER_BACKUPS = 3
    MAX_SYSTEM_BACKUPS = 2

    client = models.ForeignKey(Client, models.CASCADE, verbose_name=_("client"))
    name = models.CharField(max_length=50, blank=True, verbose_name=_("name"),
        help_text=_("Label to easily identify wanted backup, eg. 'After R1'"))
    filename = models.CharField(max_length=100, verbose_name=_("filename"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("timestamp"))
    user_initiated = models.BooleanField(default=False, verbose_name=_("user-initiated"))

    def __str__(self):
        return "%s Backup: %s" % (self.client.name, self.name)

    class Meta:
        verbose_name = _("backup")
        verbose_name_plural = _("backups")

    @property
    def uri(self):
        return "%s%s/%s" % (settings.BACKUPS_S3_BUCKET, self.client.schema_name, self.filename)

    def file_exists(self):
        file_exists = Popen(['aws', 's3', 'ls', self.uri], stdout=PIPE)
        return len(file_exists.communicate()[0]) != 0

    def save(self):
        if self.filename is None or self.filename == '':
            self.filename = '%d.dump.gz' % (int(timezone.now().timestamp()))

        if not self.file_exists():
            async_to_sync(get_channel_layer().send)("backups", {
                "type": "create_backup",
                "uri": self.uri,
                "schema_name": self.client.schema_name,
            })

        return super().save()

    def delete(self):
        process = Popen(['aws', 's3', 'rm', self.uri])
        output, err = process.communicate()
        return super().delete()

    def restore(self):
        if not self.file_exists():  # File does not exist
            self.delete()
            return False

        new_backup = Backup(client=self.client, name="Before restoration of backup", user_initiated=True)
        new_backup.save()

        async_to_sync(get_channel_layer().send)("backups", {
            "type": "restore_backup",
            "uri": self.uri,
            "schema_name": self.client.schema_name,
        })

        return True
