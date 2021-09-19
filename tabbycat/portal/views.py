import json
import logging
import time
from subprocess import PIPE, Popen

import requests
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import CreateView, FormMixin, FormView
from django_tenants.utils import schema_context

from notifications.models import EmailStatus, SentMessage
from registration.models import Payment
from registration.utils import payment_webhook_received
from utils.mixins import AssistantMixin
from utils.tables import BaseTableBuilder
from utils.views import PostOnlyRedirectView, VueTableTemplateView

from .forms import BackupInstanceForm, InstanceBackupSelectionForm, InstanceCreationForm, InvoicedInstanceCreationForm, UserCreationForm
from .models import Client, Instance
from .utils import get_postgres_url, on_payment_deny, on_payment_success

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def get_instance_url(request, instance):
    return "//" + instance.domain + "/"


class ClientObjectMixin:
    @property
    def client(self):
        if not hasattr(self, "_client"):
            self._client = get_object_or_404(Client, user=self.request.user, schema_name=self.kwargs['schema'])
        return self._client


class CreateAccountView(FormView):
    template_name = 'registration/create_account.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('own-tournaments-list')
    view_role = ""

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.info(self.request, _("Welcome! You've created an account for %s.") % user.username)

        return super().form_valid(form)


class MainPageView(TemplateView):
    template_name = 'main_page.html'
    view_role = "public"


class ListOwnTournamentsView(AssistantMixin, VueTableTemplateView):
    template_name = 'tournaments_list.html'
    page_title = gettext_lazy("Your Tabbycat Sites")

    def get_table(self):
        clients = Client.objects.filter(user=self.request.user)
        table = BaseTableBuilder(view=self, sort_key="date")

        instances = []
        control_links = []
        for c in clients:
            c_row = {'text': c.name}
            try:
                c_row['link'] = get_instance_url(self.request, c.domains.get(is_primary=True))
            except Instance.DoesNotExist:
                c_row['text'] += _(" (Unpaid)")
            instances.append(c_row)
            control_links.append({'link': reverse('tournament-detail', kwargs={'schema': c.schema_name}), 'text': _("Control")})

        table.add_column({'key': 'name', 'title': _("Site Name")}, instances)
        table.add_column({'key': 'control', 'title': _("Control")}, control_links)
        table.add_column(
            {'key': 'date', 'icon': 'clock', 'tooltip': _("When the site was created")},
            [{'text': c.created_on} for c in clients])
        return table


class TournamentDetailView(AssistantMixin, ClientObjectMixin, FormMixin, VueTableTemplateView):
    template_name = "tournament_detail.html"
    form_class = BackupInstanceForm

    def get_table(self):
        if self.client.is_pro:
            empty_title = _("No data available")
        else:
            empty_title = _("The plan of the instance does not include backup storage")

        table = BaseTableBuilder(title=_("Backups"), empty_title=empty_title, sort_key='timestamp')
        qs = self.client.backup_set.all().order_by('-timestamp')

        table.add_column({'key': 'radio', 'name': 'backup', 'title': ""}, [{
            'component': 'radio-cell',
            'checked': False,
            'sort': False,
            'value': b.id,
            'name': 'backup',
        } for b in qs])
        table.add_column({'key': 'name', 'title': _("Name")}, [b.name for b in qs])
        table.add_column({'key': 'timestamp', 'title': _("Time")}, [b.timestamp for b in qs])
        return table

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs['client'] = self.client
        kwargs['page_title'] = self.client.name
        kwargs['domain'] = self.client.get_primary_domain()
        return kwargs


class DeleteInstanceView(AssistantMixin, ClientObjectMixin, TemplateView):
    template_name = 'delete-site.html'

    def get_redirect_url(self, *args, **kwargs):
        return reverse('own-tournaments-list')

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs['client'] = self.client
        return kwargs

    def post(self, request, *args, **kwargs):
        name = self.client.name

        self.client.delete()
        messages.success(request, _("Deleted the %s site" % name))
        return HttpResponseRedirect(self.get_redirect_url(*args, **kwargs))


class ExportInstanceDatabaseView(AssistantMixin, ClientObjectMixin, PostOnlyRedirectView):

    def create_filename(self):
        date = time.strftime("%Y-%m-%d-%H-%M", time.gmtime())
        return "%s-%s.sql" % (self.client.schema_name, date)

    def post(self, request, *args, **kwargs):
        process = Popen(['pg_dump', get_postgres_url(), '-n', self.client.schema_name, '-O', '-x'], stdout=PIPE)
        output, errors = process.communicate()

        response = HttpResponse(content_type='application/sql', content=output)
        response['Content-Disposition'] = "attachment; filename=%s" % (self.create_filename(),)
        return response


class BackupInstanceView(AssistantMixin, ClientObjectMixin, CreateView):
    form_class = BackupInstanceForm

    def get_success_url(self):
        return reverse('tournament-detail', kwargs={'schema': self.client.schema_name})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['client'] = self.client
        return kwargs

    def get(self, request, *args, **kwargs):
        return HttpResponse(status=405)

    def form_valid(self, form):
        messages.success(self.request, _("Created backup"))
        return super().form_valid(form)


class InstanceBackupsActionView(AssistantMixin, ClientObjectMixin, FormView):
    form_class = InstanceBackupSelectionForm

    def get_success_url(self):
        return reverse('tournament-detail', kwargs={'schema': self.client.schema_name})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['backups'] = self.client.backup_set.all()
        return kwargs

    def get(self, request, *args, **kwargs):
        return HttpResponse(status=405)

    def form_valid(self, form):
        return {
            'delete': self.delete,
            'restore': self.restore,
            'download': self.download,
        }[self.request.POST.get('submit')](form, form.save())

    def delete(self, form, backup):
        backup.delete()
        return super().form_valid(form)

    def restore(self, form, backup):
        backup.restore()
        return super().form_valid(form)

    def download(self, form, backup):
        s3_process = Popen(['aws', 's3', 'cp', backup.uri, '-'], stdout=PIPE)
        data, errors = s3_process.communicate()

        response = HttpResponse(content_type='application/sql', content=data)
        response['Content-Disposition'] = "attachment; filename=%s" % (backup.filename,)
        return response


class CreateInstanceFormView(AssistantMixin, FormView):
    template_name = 'create_instance_form.html'
    form_class = InstanceCreationForm
    initial = {'currency': 'cad'}

    def get_context_data(self, **kwargs):
        kwargs['STRIPE_PUBLIC_KEY'] = settings.STRIPE_PUBLISH_KEY
        kwargs['main_domain'] = Instance.objects.get(tenant__schema_name='public', is_primary=True).domain
        return super().get_context_data(**kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['data'] = json.loads(self.request.body)
        return kwargs

    def form_valid(self, form):
        self.object = form.save()
        currency_amounts = {
            'aud': 5500,
            'cad': 5000,
            'eur': 3500,
            'usd': 4000,
        }
        customer = stripe.Customer.create(email=self.request.user.email)
        intent = stripe.PaymentIntent.create(
            amount=currency_amounts.get(self.object.currency, 5000),
            currency=self.object.currency,
            description=self.object.name,
            customer=customer['id'],
            metadata={
                "product": "Calico Site",
                "application": "portal",
                "name": self.object.name,
                "slug": self.object.schema_name,
                "timezone": self.object.timezone,
                "user": self.request.user.username,
            },
        )
        self.object.payment_id = intent['id']
        self.object.user = self.request.user
        self.object.save()
        return JsonResponse({'clientSecret': intent['client_secret']})

    def form_invalid(self, form):
        return JsonResponse(form.errors.get_json_data(escape_html=True))


class InvoicedCreateInstanceFormView(AssistantMixin, FormView):
    template_name = 'base_create_instance_form.html'
    form_class = InvoicedInstanceCreationForm

    def form_valid(self, form):
        self.object = form.save()
        self.object.user = self.request.user
        self.object.save()

        main_instance = Instance.objects.get(tenant__schema_name='public', is_primary=True).domain
        self.instance = Instance(tenant=self.object, domain=self.object.schema_name + "." + main_instance, is_primary=True).save()

        return super().form_valid(form)

    def get_success_url(self):
        return get_instance_url(self.request, self.instance)


class StripeWebhookView(View):

    def post(self, request, *args, **kwargs):
        signature = request.META['HTTP_STRIPE_SIGNATURE']
        logger.info(signature)

        try:
            event = stripe.Webhook.construct_event(request.body, signature, settings.STRIPE_ENDPOINT_SEC)
        except ValueError:  # Invalid payload
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:  # Invalid signature
            return HttpResponse(status=400)

        args = []
        application = event['data']['object']['metadata'].get('application', 'portal')
        if application == 'portal':
            actions = {
                'payment_intent.succeeded': on_payment_success,
                'payment_intent.canceled': on_payment_deny,
                'payment_intent.payment_failed': on_payment_deny,
            }
            try:
                args.append(Client.objects.get(payment_id=event['data']['object']['id']))
            except Client.DoesNotExist:
                return HttpResponse(status=204)
        elif application == 'registration':
            actions = {
                'payment_intent.succeeded': payment_webhook_received,
                'payment_intent.canceled': payment_webhook_received,
                'payment_intent.payment_failed': payment_webhook_received,
            }
            try:
                args.append(Payment.objects.get(payment_intent=event['data']['object']['id']))
            except Payment.DoesNotExist:
                return HttpResponse(status=204)

        args.append(event['data']['object'])
        if event['type'] in actions:
            actions[event['type']](*args)

        return HttpResponse(status=200)


class SESWebhookView(View):

    def post(self, request, *args, **kwargs):
        if kwargs['wh_key'] != settings.SES_WEBHOOK_KEY:
            return HttpResponse(status=401)
        body = json.loads(request.body.decode('utf-8'))

        # Subscribe to SNS
        if body.get('Type') == "SubscriptionConfirmation":
            requests.get(body.get('SubscribeURL'))
            return HttpResponse(status=200)

        message_body = json.loads(body['Message'])
        status = None
        if 'bounce' in message_body:
            status = EmailStatus.EVENT_TYPE_BOUNCED
        elif 'complaint' in message_body:
            status = EmailStatus.EVENT_TYPE_SPAM
        elif 'delivery' in message_body:
            status = EmailStatus.EVENT_TYPE_DELIVERED

        mail_body = message_body.get('mail', {})
        headers = {h['name']: h['value'] for h in mail_body.get('headers', {})}

        logger.info("Notification %s from %s", headers.get('X-HOOKID'), headers.get('X-TCSITE'))
        if headers.get('X-TCSITE') is None:  # Test emails don't include header
            return HttpResponse(status=200)

        with schema_context(headers.get('X-TCSITE')):
            bn, to, rand = headers.get('X-HOOKID').split('-')
            message, created = SentMessage.objects.get_or_create(hook_id=headers.get('X-HOOKID'), defaults={
                'notification_id': bn,
                'recipient_id': to,
                'method': SentMessage.METHOD_TYPE_EMAIL,
                'email': mail_body.get("destination", [None])[0],
            })
            message.emailstatus_set.create(event=status)

        return HttpResponse(status=200)
