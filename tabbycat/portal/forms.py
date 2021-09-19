import stripe
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms.widgets import DateInput, Select
from django.utils.translation import gettext_lazy as _
from pytz import common_timezones

from .models import Backup, Client, Instance

stripe.api_key = settings.STRIPE_SECRET_KEY


class DatalistWidget(Select):
    input_type = 'text'
    template_name = 'widgets/datalist.html'


class CalendarDateInputWidget(DateInput):
    input_type = 'date'


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        fields = ("username", "email")
        labels = {"email": _("E-mail address")}


class InstanceCreationForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ("name", "schema_name", "end_date", "timezone", "currency")
        labels = {
            "schema_name": _("Slug"),
        }
        help_texts = {
            "schema_name": _("The name used in the URL of the site. Must be alphanumeric."),
        }
        widgets = {
            "end_date": CalendarDateInputWidget,
            "timezone": DatalistWidget,
        }

    def clean_timezone(self):
        tz = self.cleaned_data['timezone']
        if tz not in common_timezones:
            raise ValidationError(_("Invalid timezone"))
        return tz

    def clean_schema_name(self):
        name = self.cleaned_data['schema_name']
        main_domain = Instance.objects.get(tenant__schema_name='public', is_primary=True).domain
        if Client.objects.filter(Q(schema_name=name) | Q(domains__domain=name + main_domain)).exists():
            raise ValidationError(_("A site with that slug already exists!"))
        return name

    def create_schema(self, client):
        async_to_sync(get_channel_layer().send)("portal", {
            "type": "create_schema",
            "client": client.id,
        })

    def save(self, commit=True):
        client = super().save(commit=False)

        if commit:
            client.save()
            self.create_schema(client)

        return client


class InvoicedInstanceCreationForm(InstanceCreationForm):

    invoice = forms.CharField(label=_("Invoice Number"))

    def clean_invoice(self):
        try:
            invoice = stripe.Invoice.retrieve(self.cleaned_data['invoice'])
            return invoice['payment_intent']
        except stripe.InvalidRequestError:
            raise ValidationError(_("No invoice with that ID exists."))

    def save(self, commit=True):
        client = super().save(commit=False)
        client.payment_id = self.cleaned_data['invoice']['payment_intent']
        client.paid = self.cleaned_data['invoice']['total']

        if commit:
            client.save()
            self.create_schema(client)
        return client


class BackupInstanceForm(forms.ModelForm):

    class Meta:
        model = Backup
        fields = ('name',)

    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False

    def save(self, commit=True):
        backup = super().save(commit=False)
        backup.client = self.client
        backup.user_initiated = True

        if commit:
            backup.save()

        return backup


class InstanceBackupSelectionForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.backups = kwargs.pop('backups')
        super().__init__(*args, **kwargs)

        self.fields['backup'] = forms.ModelChoiceField(widget=forms.RadioSelect, queryset=self.backups)

    def save(self, commit=True):
        return self.cleaned_data['backup']
