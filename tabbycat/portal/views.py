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
from django.views.generic.edit import FormView
from django_tenants.utils import schema_context

from notifications.models import EmailStatus, SentMessage
from utils.mixins import AssistantMixin
from utils.tables import BaseTableBuilder
from utils.views import PostOnlyRedirectView, VueTableTemplateView

from .forms import InstanceCreationForm, UserCreationForm
from .models import Client, Instance

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def get_instance_url(request, instance):
    return "//" + instance.domain + "/"


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
                c_row['link'] = reverse('stripe-payment-redirect', kwargs={'schema': c.schema_name})
                c_row['text'] += _(" (Unpaid)")
            instances.append(c_row)
            control_links.append({'link': reverse('tournament-detail', kwargs={'schema': c.schema_name}), 'text': _("Control")})

        table.add_column({'key': 'name', 'title': _("Site Name")}, instances)
        table.add_column({'key': 'control', 'title': _("Control")}, control_links)
        table.add_column(
            {'key': 'date', 'icon': 'clock', 'tooltip': _("When the site was created")},
            [{'text': c.created_on} for c in clients])
        return table


class TournamentDetailView(AssistantMixin, TemplateView):
    template_name = "tournament_detail.html"

    def get_context_data(self, **kwargs):
        client = get_object_or_404(Client, user=self.request.user, schema_name=self.kwargs['schema'])
        kwargs = super().get_context_data(**kwargs)
        kwargs['client'] = client
        kwargs['page_title'] = client.name
        kwargs['domain'] = client.get_primary_domain()
        return kwargs


class DeleteInstanceView(AssistantMixin, TemplateView):
    template_name = 'delete-site.html'

    def get_redirect_url(self, *args, **kwargs):
        return reverse('own-tournaments-list')

    def get_context_data(self, **kwargs):
        client = get_object_or_404(Client, user=self.request.user, schema_name=self.kwargs['schema'])
        kwargs = super().get_context_data(**kwargs)
        kwargs['client'] = client
        return kwargs

    def post(self, request, *args, **kwargs):
        client = get_object_or_404(Client, user=request.user, schema_name=self.kwargs['schema'])
        name = client.name

        client.delete()
        messages.success(request, _("Deleted the %s site" % name))
        return HttpResponseRedirect(self.get_redirect_url(*args, **kwargs))


class BackupInstanceView(AssistantMixin, PostOnlyRedirectView):

    def create_filename(self):
        date = time.strftime("%Y-%m-%d-%H-%M", time.gmtime())
        return "%s-%s.sql" % (self.client.schema_name, date)

    def get_postgres_params(self):
        db = settings.DATABASES['default']
        return [
            'pg_dump',
            'postgres://%s:%s@%s:%s/%s' % (db['USER'], db['PASSWORD'], db['HOST'], db['PORT'], db['NAME']),
            '-n', self.client.schema_name,
            '-O', '-x',
        ]

    def post(self, request, *args, **kwargs):
        self.client = get_object_or_404(Client, user=request.user, schema_name=self.kwargs['schema'])

        process = Popen(self.get_postgres_params(), stdout=PIPE)
        output, errors = process.communicate()

        response = HttpResponse(content_type='application/sql', content=output)
        response['Content-Disposition'] = "attachment; filename=%s" % (self.create_filename(),)
        return response


class CreateInstanceFormView(AssistantMixin, FormView):
    template_name = 'create_instance_form.html'
    form_class = InstanceCreationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        self.object = form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('stripe-payment-redirect', kwargs={'schema': self.object.schema_name})


class StripeSessionView(AssistantMixin, View):

    def post(self, request, *args, **kwargs):
        body = json.loads(request.body)
        client = get_object_or_404(Client, user=request.user, pk=body['client_id'])

        if client.session_id:
            return JsonResponse({'sessionId': client.session_id}, status=201)

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': settings.INSTANCE_PRICE_ID,
                'quantity': 1,
                'description': client.name,
            }],
            mode='payment',
            success_url=request.build_absolute_uri(reverse('successful-payment')) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri(reverse('cancelled-payment')),
        )
        client.session_id = session['id']
        client.payment_id = session['payment_intent']
        client.save()
        return JsonResponse({'sessionId': session['id']}, status=201)


class StripeRedirectView(AssistantMixin, TemplateView):
    template_name = 'square_redirect.html'

    def get(self, request, *args, **kwargs):
        self.client = Client.objects.get(schema_name=self.kwargs['schema'])
        if self.client.paid > 1000:  # Some number, but redirect if already paid
            return HttpResponseRedirect(get_instance_url(request, self.client.get_primary_domain()))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs['client'] = self.client
        kwargs['stripe_public_key'] = settings.STRIPE_PUBLISH_KEY
        return kwargs


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

        actions = {
            'payment_intent.succeeded': self.on_payment_success,
            'payment_intent.canceled': self.on_payment_deny,
            'payment_intent.payment_failed': self.on_payment_deny,
        }
        if event['type'] in actions:
            actions[event['type']](event['data']['object'])

        return HttpResponse(status=200)

    def on_payment_success(self, payment):
        client = get_object_or_404(Client, payment_id=payment['id'])
        client.paid = payment.get('amount', 0)
        client.save()

        # Add domain
        main_instance = Instance.objects.get(tenant__schema_name='public', is_primary=True)
        Instance.objects.get_or_create(tenant=client, domain=client.schema_name.lower() + "." + main_instance.domain)

    def on_payment_deny(self, payment):
        client = get_object_or_404(Client, payment_id=payment['id'])
        client.delete(force_drop=not client.domains.exists())


class CancelledPaymentRedirectView(View):
    redirect_url = reverse_lazy('global-main-page')

    def get(self, request, *args, **kwargs):
        messages.error(self.request, _("The payment was cancelled."))
        return HttpResponseRedirect(self.redirect_url)


class SuccessfulPaymentLandingView(View):

    def get(self, request, *args, **kwargs):
        session_id = self.request.GET.get('session_id')
        if session_id is None:
            return HttpResponseRedirect(reverse('create-instance'))

        client = Client.objects.get(session_id=session_id)
        return HttpResponseRedirect(get_instance_url(request, client.get_primary_domain()))


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
