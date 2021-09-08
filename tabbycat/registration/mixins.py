import stripe
from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy
from django.views.generic.base import ContextMixin

from utils.misc import reverse_tournament
from utils.mixins import TabbycatPageTitlesMixin

from .models import Institution, Payment, Tournament

stripe.api_key = settings.STRIPE_SECRET_KEY


class TournamentMixin(TabbycatPageTitlesMixin):
    tournament_slug_url_kwarg = "tournament_slug"

    @property
    def tournament(self):
        # First look in self,
        if not hasattr(self, "_tournament_from_reg"):
            self._tournament_from_reg = get_object_or_404(Tournament, slug=self.kwargs[self.tournament_slug_url_kwarg])

        return self._tournament_from_reg

    def get_context_data(self, **kwargs):
        kwargs.update({
            'tournament': self.tournament,
            'pref': self.tournament.preferences.by_name(),
        })
        return super().get_context_data(**kwargs)


class RegistrationFormTitlesMixin(ContextMixin):
    form_title = ''
    form_text = ''
    explain_text = ''
    submit_title = gettext_lazy("Submit")

    def get_context_data(self, **kwargs):
        kwargs['form_title'] = self.form_title
        kwargs['form_text'] = self.form_text
        kwargs['explain_text'] = self.explain_text
        kwargs['submit_title'] = self.submit_title
        return super().get_context_data(**kwargs)


class AdminMixin(TournamentMixin, UserPassesTestMixin, ContextMixin):
    view_role = "reg-admin"

    def get_context_data(self, **kwargs):
        kwargs["user_role"] = self.view_role
        return super().get_context_data(**kwargs)

    def test_func(self):
        return self.tournament.manager == self.request.user


class InstitutionMixin(TournamentMixin, UserPassesTestMixin, ContextMixin):
    view_role = "institution"

    @property
    def institution(self):
        if not hasattr(self, "_institution"):
            queryset = Institution.objects.filter(pk=self.kwargs['pk'], tournament=self.tournament)
            self._institution = get_object_or_404(queryset)
        return self._institution

    def get_context_data(self, **kwargs):
        kwargs["user_role"] = self.view_role
        kwargs["institution"] = self.institution
        return super().get_context_data(**kwargs)

    def test_func(self):
        return self.institution.manager == self.request.user


class PaymentSessionMixin:

    acss_customer_type = None

    payment_methods = {
        'card': lambda currency, country: True,
        'acss_debit': lambda currency, country: True,
        'wechat_pay': lambda currency, country: currency[:2] == country,
    }

    def get_price(self, participant_type):
        product_name = "%s Registration" % (participant_type,)
        currency = self.tournament.pref('currency').lower()
        amount = self.tournament.pref('%s_fee' % (participant_type.lower().replace(' ', '_')))

        products = stripe.Product.list(active=True, stripe_account=self.tournament.connected_account)
        product = None
        for p in products['data']:
            if p['name'] == product_name:
                product = p
                break
        else:
            product = stripe.Product.create(name=product_name, stripe_account=self.tournament.connected_account)

        price = None
        prices = stripe.Price.list(
            active=True, currency=currency, product=product['id'], type="one_time",
            stripe_account=self.tournament.connected_account)
        for p in prices['data']:
            if p['unit_amount'] == amount:
                price = p
                break
        else:
            price = stripe.Price.create(
                unit_amount=amount, currency=currency,
                product=product['id'], stripe_account=self.tournament.connected_account)

        return price['id'], amount

    def create_coupon(self, amount):
        coupon = stripe.Coupon.create(
            amount_off=amount,
            currency=self.tournament.pref('currency').lower(),
            max_redeptions=1,
        )
        return coupon['id']

    def get_account(self):
        return stripe.Account.retrieve(self.tournament.connected_account)

    def create_session(self, adjudicators=0, teams=0, missing_adjs=0, discount=0, institution=None, email=None):
        currency = self.tournament.pref('currency')
        items = []
        total = 0

        for ptype, ps in (('Adjudicator', adjudicators), ('Team', teams), ('Missing Adjudicator', missing_adjs)):
            count = ps if type(ps) is int else len(ps)
            if count > 0:
                price = self.get_price(ptype)
                item = {
                    'price': price[0],
                    'quantity': count,
                }
                if hasattr(ps, '__iter__'):
                    item['description'] = ", ".join([item.name for item in ps])
                items.append(item)
                total += price[1] * count

        coupons = []
        if discount > 0:
            coupons.append(self.create_coupon(discount))

        session = stripe.checkout.Session.create(
            payment_method_types=[key for key, f in self.payment_methods.items() if f(currency, self.get_account()['country'])],
            line_items=items,
            discounts=coupons,
            payment_intent_data={
                'application_fee_amount': round(total * self.tournament.fee_rate),
                'description': "Registration for %s" % (self.tournament.name,),
            },
            payment_method_options={
                'acss_debit': {
                    'mandate_options': {
                        'payment_schedule': 'sporadic',
                        'transaction_type': self.acss_customer_type,
                    },
                },
                'wechat_pay': {
                    'client': 'web',
                },
            },
            customer_email=email,
            mode='payment',
            cancel_url=self.request.build_absolute_uri(reverse_tournament('cancel-payment', self.tournament)),
            success_url=self.request.build_absolute_uri(reverse_tournament('success-payment', self.tournament)),
            stripe_account=self.tournament.connected_account,
        )

        p = Payment(
            tournament=self.tournament, payment_intent=session['payment_intent'], processor=Payment.PROCESSOR_STRIPE,
            amount_paid=total, currency=currency,
            institution=institution, num_teams=teams if type(teams) is int else len(teams),
            num_adjudicators=adjudicators if type(adjudicators) is int else len(adjudicators))
        p.save()

        if hasattr(teams, '__iter__'):
            p.teams_paid.set(teams)
        if hasattr(adjudicators, '__iter__'):
            p.adjudicators_paid.set(adjudicators)

        return session['url'], p
