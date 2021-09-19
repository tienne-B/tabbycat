import requests
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.http.response import Http404
from django.utils.translation import gettext as _, gettext_lazy, ngettext
from django.views.generic import TemplateView, View
from django.views.generic.edit import CreateView, FormView
from dynamic_preferences.views import PreferenceFormView

from utils.misc import reverse_tournament
from utils.mixins import AssistantMixin
from utils.tables import BaseTableBuilder
from utils.views import ModelFormSetView, PostOnlyRedirectView, VueTableTemplateView

from .forms import (AdjudicatorDetailsForm, CreateInstitutionForm, CreateTournamentFromURL,
    InstitutionApproveForm, TeamDetailsForm, tournament_preference_form_builder)
from .mixins import AdminMixin, InstitutionMixin, PaymentSessionMixin, RegistrationFormTitlesMixin, TournamentMixin
from .models import Adjudicator, Discount, Institution, Payment, Person, SpeakerCategory, Team, Tournament
from .preferences import AdjudicatorsPerTeamRule
from .registries import tournament_preferences_registry

stripe.api_key = settings.STRIPE_SECRET_KEY


# =============================================================================
# Tournaments
# =============================================================================

class ListManagedObjectsView(AssistantMixin, VueTableTemplateView):
    page_title = gettext_lazy("My Managed")
    page_subtitle = gettext_lazy("Tournaments and institutions")

    def get_institutions_table(self):
        table = BaseTableBuilder(view=self, title=_("My institutions"))
        qs = Institution.objects.filter(manager=self.request.user).order_by('tournament__date')

        table.add_column({'key': 'name', 'title': _("Tournament")}, [{'text': i.tournament.name} for i in qs])
        table.add_column({'key': 'inst', 'title': _("Institution")}, [{'text': i.name,
            'link': reverse_tournament('institution-index', i.tournament, kwargs={'institution_pk': i.pk})} for i in qs])

        return table

    def get_tournaments_table(self):
        table = BaseTableBuilder(view=self, title=_("My tournaments"))
        qs = Tournament.objects.filter(manager=self.request.user).order_by('date')
        table.add_column({'key': 'name', 'title': _("Tournament")}, [{'text': t.name,
            'link': reverse_tournament('admin-tournament-home', t)} for t in qs])
        table.add_column({'key': 'inst', 'title': _("Date")}, [{'text': t.date} for t in qs])

        return table

    def get_tables(self):
        return [self.get_institutions_table(), self.get_tournaments_table()]


class PublicTournamentIndexView(TournamentMixin, TemplateView):
    template_name = 'reg_tournament_index.html'

    def get_context_data(self, **kwargs):
        if not self.request.user.is_anonymous:
            kwargs['own_institutions'] = Institution.objects.filter(tournament=self.tournament, manager=self.request.user)
        return super().get_context_data(**kwargs)


class AdminPreferencesView(AdminMixin, TournamentMixin, PreferenceFormView):
    registry = tournament_preferences_registry
    template_name = "preferences_set.html"

    def form_valid(self, *args, **kwargs):
        messages.success(self.request, _("Tournament options saved."))
        return super().form_valid(*args, **kwargs)

    def get_success_url(self):
        return reverse_tournament('tournament-home', self.tournament)

    def get_form_class(self, *args, **kwargs):
        return tournament_preference_form_builder(instance=self.tournament, section=None)


class AdminRegistrationListView(AdminMixin, TournamentMixin, VueTableTemplateView):
    page_title = gettext_lazy("Participants")

    def get_tables(self):
        return [self.get_adjs_table(), self.get_teams_table()]

    def get_adjs_table(self):
        table = BaseTableBuilder(view=self, title=_("Adjudicators"))
        qs = Adjudicator.objects.filter(tournament=self.tournament).select_related('institution').annotate(paid=Exists(
            Payment.adjudicators_paid.through.objects.filter(status=Payment.STATUS_SUCCEEDED, adjudicators_paid=OuterRef('id'))))

        table.add_column({'key': 'name', 'title': _("Name")}, [adj.name for adj in qs])
        self.add_column({
            'key': "institution",
            'icon': 'home',
            'tooltip': _("Institution"),
        }, [adj.institution.code if adj.institution else _("-") for adj in qs])

        self.add_boolean_column({
            'key': 'independent',
            'tooltip': _("Independent Adjudicator"),
            'icon': 'user-plus',
        }, [adj.independent for adj in qs])

        self.add_boolean_column({
            'key': 'paid',
            'tooltip': _("Paid?"),
            'icon': 'credit-card',
        }, [adj.paid for adj in qs])
        return table

    def get_teams_table(self):
        table = BaseTableBuilder(view=self, title=_("Teams"))
        qs = Team.objects.filter(tournament=self.tournament).select_related('institution').annotate(paid=Exists(
            Payment.teams_paid.through.objects.filter(status=Payment.STATUS_SUCCEEDED, adjudicators_paid=OuterRef('id'))))

        table.add_column({'key': 'name', 'title': _("Name")}, [team.short_name for team in qs])
        self.add_column({
            'key': "institution",
            'icon': 'home',
            'tooltip': _("Institution"),
        }, [team.institution.name if team.institution else _("-") for team in qs])

        self.add_boolean_column({
            'key': 'paid',
            'tooltip': _("Paid?"),
            'icon': 'credit-card',
        }, [team.paid for team in qs])
        return table


class AdminInstitutionsListView(AdminMixin, TournamentMixin, VueTableTemplateView, FormView):
    template_name = 'admin_institutions_list.html'
    form_class = InstitutionApproveForm

    def get_context_data(self, **kwargs):
        # Populate the form here, so we can save it in self.form
        self.form = self.get_form()
        kwargs['form'] = self.form

        return super().get_context_data(**kwargs)

    def get_table(self):
        table = BaseTableBuilder(view=self, title=_("Institutions"))
        qs = self.get_queryset()

        table.add_column({'key': 'institution', 'title': _("Name")}, [{
            'text': _("%(institution)s (%(code)s)") % {'institution': i.name, 'code': i.code},
            'link': reverse_tournament('admin-institution-detail', self.tournament, kwargs={'pk': i.pk}),
        } for i in qs])

        if self.tournament.pref('require_slots'):
            table.add_column({'key': 'req_teams', 'title': _("Requested Teams")}, [i.requested_teams for i in qs])
            table.add_column({'key': 'app_teams', 'title': _("Approved")}, [str(self.form.get_table_field(i, 'teams')) for i in qs])

            table.add_column({'key': 'req_adjs', 'title': _("Requested Adjudicators")}, [i.requested_adjudicators for i in qs])
            table.add_column({'key': 'app_adjs', 'title': _("Approved")}, [str(self.form.get_table_field(i, 'adjs')) for i in qs])
        else:
            table.add_column({'key': 'teams', 'title': _("Teams")}, [i.nteams for i in qs])
            table.add_column({'key': 'adjs', 'title': _("Adjudicators")}, [i.nadjs for i in qs])

        return table

    def get_queryset(self):
        return self.tournament.institution_set.all().prefetch_related('team_set', 'adjudicator_set').annotate(
            nadjs=Count('adjudicator'), nteams=Count('team'))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tournament'] = self.tournament
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Institution allocations have been updated."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_tournament('tournament-home', self.tournament)


class AdminImportTournamentView(AdminMixin, PostOnlyRedirectView):
    pass


class CreateTournamentView(AssistantMixin, RegistrationFormTitlesMixin, FormView):
    form_title = gettext_lazy("Create Tournament")

    form_class = CreateTournamentFromURL
    template_name = 'reg_create_tournament.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        return reverse_tournament('tournament-home', self.tournament)

    def form_valid(self, form):
        self.tournament = form.save()

        # Populate speaker categories
        if form.cleaned_data.get('api_key') is not None:
            categories_request = requests.get(self.tournament.api_url + "/speaker-categories",
                headers={'Authorization': 'Token %s' % form.cleaned_data['api_key']})
            categories_request.raise_for_status()
            for c in categories_request.json():
                if not c['public']:
                    continue
                SpeakerCategory.objects.create(tournament=self.tournament, name=c['name'], seq=c['seq'], api_url=c['url'])

        return super().form_valid(form)


class AdminExportParticipantsView(AdminMixin, PostOnlyRedirectView):
    pass


# =============================================================================
# Participants
# =============================================================================

class EditAdjudicatorsView(InstitutionMixin, ModelFormSetView):
    template_name = 'adjudicators_edit.html'
    formset_model = Adjudicator

    def get_formset_factory_kwargs(self):
        fields = ['name', 'email', 'gender']
        if not self.tournament.pref('select_gender'):
            fields.pop('gender')

        nexisting = self.institution.adjudicator_set.all().count()
        if self.tournament.pref('maximum_adjudicators') < 0:
            extra = 5
        else:
            extra = max(self.tournament.pref('maximum_adjudicators') - nexisting, 0)

        return {'fields': fields, 'can_delete': True, 'exclude': [], 'extra': extra}

    def get_formset_kwargs(self):
        initial = []
        for adj in self.get_formset_queryset():
            initial.append({'name': adj.name, 'email': adj.email, 'gender': adj.gender})
        return {'initial': initial}

    def get_formset_queryset(self):
        return self.institution.adjudicator_set.filter(api_url__isnull=True)

    def get_success_url(self):
        return reverse_tournament('institution-home', self.tournament, kwargs={'institution_id': self.institution})

    def formset_valid(self, formset):
        adjudicators = formset.save(commit=False)
        for adj in adjudicators:
            adj.tournament = self.tournament
            adj.institution = self.institution
            adj.save()

        for adj in formset.deleted_objects:
            if adj.api_url is None:
                adj.delete()

        count = len(adjudicators)
        if count > 0:
            messages.success(self.request, ngettext("%(count)d adjudicator has been saved.",
                "%(count)d adjudicators have been saved.", count) % {'count': count})

        count = len(formset.deleted_objects)
        if count > 0:
            messages.success(self.request, ngettext("%(count)d adjudicator has been deleted.",
                "%(count)d adjudicators have been deleted.", count) % {'count': count})

        return super().formset_valid(formset)


class EditTeamsView(InstitutionMixin, ModelFormSetView):
    template_name = 'teams_edit.html'
    formset_model = Team

    def get_formset_factory_kwargs(self):
        if self.tournament.pref('cap_teams') < 0:
            extra = 2
        else:
            extra = max(self.institution.accepted_teams - self.institution.team_set.count(), 0)
        return {'form': TeamDetailsForm, 'can_delete': True, 'extra': extra}

    def get_formset_queryset(self):
        return self.institution.team_set.filter(api_url__isnull=True).prefetch_related('speaker_set', 'speaker_set__categories')

    def get_success_url(self):
        return reverse_tournament('institution-home', self.tournament, kwargs={'institution_id': self.institution})

    def get_form_kwargs(self):
        return {'tournament': self.tournament, 'institution': self.institution}

    def get_formset_kwargs(self):
        initial = []
        for team in self.get_formset_queryset():
            team_dict = {'reference': team.reference, 'emoji': team.emoji}
            for i, speaker in enumerate(team.speaker_set.all()):
                team_dict.extend({
                    TeamDetailsForm._get_speaker_name_field(i): speaker.name,
                    TeamDetailsForm._get_speaker_email_field(i): speaker.email,
                    TeamDetailsForm._get_speaker_gender_field(i): speaker.gender,
                    TeamDetailsForm._get_speaker_categories_field(i): speaker.categories.all(),
                })
            initial.append(team_dict)
        return {'initial': initial}


class CreateInstitutionView(LoginRequiredMixin, TournamentMixin, RegistrationFormTitlesMixin, CreateView):
    form_title = gettext_lazy("Institutional Registration")
    submit_title = gettext_lazy("Add Institution")

    template_name = 'base_form.html'
    form_class = CreateInstitutionForm

    def get_success_url(self):
        return reverse_tournament('institution-index', self.tournament, kwargs={'pk': self.object.id})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['tournament'] = self.tournament
        return kwargs


class InstitutionIndexView(InstitutionMixin, TemplateView):
    template_name = 'institution_index.html'

    def get_context_data(self, **kwargs):
        kwargs['institution'] = Institution.objects.prefetch_related(
            Prefetch('team_set', queryset=Team.objects.all().prefetch_related('speaker_set', 'speaker_set__categories').annotate(
                paid=Exists(Payment.objects.filter(status=Payment.STATUS_SUCCEEDED, teams_paid=OuterRef('id'))))),
            Prefetch('adjudicator_set', queryset=Adjudicator.objects.all().annotate(
                paid=Exists(Payment.objects.filter(status=Payment.STATUS_SUCCEEDED, adjudicators_paid=OuterRef('id'))))),
        ).get(pk=self.institution.pk)
        return super().get_context_data(**kwargs)


class AdminInstitutionDetailView(AdminMixin, TemplateView):
    # template_name = 'admin_institutions_list.html'
    pass


class CreateTeamView(TournamentMixin, RegistrationFormTitlesMixin, FormView):
    form_title = gettext_lazy("Team Registration")
    submit_title = gettext_lazy("Add Team")

    template_name = 'base_form.html'
    form_class = TeamDetailsForm

    def get_success_url(self):
        return reverse_tournament('tournament-home', self.tournament)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tournament'] = self.tournament
        kwargs['institution'] = None
        return kwargs


class CreateAdjudicatorView(TournamentMixin, RegistrationFormTitlesMixin, CreateView):
    form_title = gettext_lazy("Adjudicator Registration")
    submit_title = gettext_lazy("Add Adjudicator")

    template_name = 'base_form.html'
    form_class = AdjudicatorDetailsForm

    def get_success_url(self):
        messages.success(self.request, _("Successfully registered as an adjudicator"))
        return reverse_tournament('tournament-home', self.tournament)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tournament'] = self.tournament
        kwargs['user'] = self.request.user
        return kwargs


# =============================================================================
# Payment views
# =============================================================================

class ConnectStripeAccountView(AdminMixin, TournamentMixin, PostOnlyRedirectView):

    def get_redirect_url(self, *args, **kwargs):
        return reverse_tournament('tournament-home', self.tournament)

    def post(self, request, *args, **kwargs):
        account = stripe.Account.create(type='standard')
        self.tournament.connected_account = account['id']
        self.tournament.save()

        account_link = stripe.AccountLink.create(
            account=account['id'],
            refresh_url=request.build_absolute_uri(reverse_tournament('tournament-home', self.tournament)),
            return_url=request.build_absolute_uri(reverse_tournament('tournament-home', self.tournament)),
            type='account_onboarding',
        )
        return HttpResponseRedirect(account_link.get('url'))


class InstitutionPaymentView(InstitutionMixin, PaymentSessionMixin, VueTableTemplateView):
    template_name = "registration_payment.html"
    acss_customer_type = "personal"

    def get_tables(self):
        if self.tournament.pref('pay_per_registration'):
            return [self.get_adjs_table(), self.get_teams_table(), self.get_registered_total_table()]
        return [self.get_numerical_total_table()]

    def get_adjs_table(self):
        table = BaseTableBuilder(view=self, title=_("Adjudicators"))

        adjs = self.institution.adjudicator_set.filter(independent=False).annotate(
            payed=Count('payment', filter=Q(payment__status=Payment.STATUS_SUCCEEDED)),
            discounts=Coalesce(Sum('discount__amount'), Value(0)))

        table.add_column({'key': 'name', 'title': _("Name")}, [{
            'text': adj.name,
            'class': "text-muted" if adj.payed > 0 else "",
        } for adj in adjs])
        table.add_column({'key': 'discounts', 'title': _("Discounts")}, [{
            'text': "-${:,.2f}".format(adj.discounts / 100),
            'class': "text-muted" if adj.payed > 0 else "",
        } for adj in adjs])

        return table

    def get_teams_table(self):
        table = BaseTableBuilder(view=self, title=_("Teams"))

        teams = self.institution.team_set.all().annotate(
            payed=Count('payment', filter=Q(payment__status=Payment.STATUS_SUCCEEDED)),
            discounts=Coalesce(Sum('discount__amount'), Value(0)))

        table.add_column({'key': 'name', 'title': _("Name")}, [{
            'text': team.name,
            'class': "text-muted" if team.payed > 0 else "",
        } for team in teams])
        table.add_column({'key': 'discounts', 'title': _("Discounts")}, [{
            'text': "-${:,.2f}".format(team.discounts / 100),
            'class': "text-muted" if team.payed > 0 else "",
        } for team in teams])

        return table

    def get_registered_total_table(self):
        table = BaseTableBuilder(view=self, title=_("Summary"))

        adjs = self.institution.adjudicator_set.filter(independent=False).exclude(
            payment__status=Payment.STATUS_SUCCEEDED,
        ).prefetch_related('discount_set').annotate(discounts=Coalesce(Sum('discount__amount'), Value(0)))
        nadjs = adjs.count()
        madjs = AdjudicatorsPerTeamRule.choice_functions[self.tournament.pref('adjudicator_rule')](nadjs)
        adiscounts = sum(a.discounts for a in adjs)

        teams = self.institution.team_set.exclude(payment__status=Payment.STATUS_SUCCEEDED).prefetch_related(
            'discount_set').annotate(discounts=Coalesce(Sum('discount__amount'), Value(0)))
        nteams = teams.count()
        tdiscounts = sum(t.discounts for t in teams)

        idiscounts = self.institution.discount_set.aggregate(discount=Coalesce(Sum('amount',
            filter=Q(currency=self.tournament.pref('currency')) & ~Q(payment__status=Payment.STATUS_SUCCEEDED)), Value(0)))['discount']

        discounts = adiscounts + tdiscounts
        subtotal = self.tournament.pref('adjudicator_fee') * nadjs + self.tournament.pref('team_fee') * nteams
        subtotal += self.tournament.pref('missing_adjudicator_fee') * madjs

        table.add_column({'key': 'item', 'title': _("Item")}, [
            {'text': _("Adjudicators")},
            {'text': _("Teams")},
            {'text': _("Missing Adjudicators")},
            {'text': _("Subtotal"), 'class': 'text-info'},
            {'text': _("Institutional Discounts")},
            {'text': _("Total"), 'class': 'text-info'},
        ])
        table.add_column({'key': 'price', 'title': _("Price")}, [
            *[{'text': "${:,.2f}".format(self.tournament.pref(i+'_fee') / 100)} for i in ('adjudicator', 'team', 'missing_adjudicator')],
            *[{'text': ''} for i in range(3)],
        ])
        table.add_column({'key': 'qtd', 'title': _("Quantity")}, [
            {'text': str(nadjs)},
            {'text': str(nteams)},
            {'text': str(madjs)},
            *[{'text': ''} for i in range(3)],
        ])
        table.add_column({'key': 'discounts', 'title': _("Discounts")}, [
            {'text': "-${:,.2f}".format(adiscounts / 100)},
            {'text': "-${:,.2f}".format(tdiscounts / 100)},
            {'text': ""},
            {'text': "-${:,.2f}".format(discounts / 100), 'class': 'text-info'},
            {'text': "-${:,.2f}".format(idiscounts / 100)},
            {'text': ""},
        ])
        table.add_column({'key': 'total', 'title': _("Total")}, [
            *[{'text': "${:,.2f}".format((self.tournament.pref(i+'_fee')*qtd-d) / 100)} for i, qtd, d in (
                ('adjudicator', nadjs, adiscounts), ('team', nteams, tdiscounts), ('missing_adjudicator', madjs, 0))],
            {'text': "${:,.2f}".format(subtotal / 100), 'class': 'text-info'},
            {'text': "-${:,.2f}".format(idiscounts / 100)},
            {'text': "${:,.2f}".format((subtotal - idiscounts) / 100), 'class': 'text-info'},
        ])
        return table

    def get_numerical_total_table(self):
        table = BaseTableBuilder(view=self, title=_("Summary"))

        nadjs = (self.institution.accepted_adjudicators or 0) - Payment.adjudicators_paid.through.objects.filter(
            payment__status=Payment.STATUS_SUCCEEDED, adjudicator__institution=self.institution, adjudicator__independent=False).count()
        nteams = (self.institution.accepted_teams or 0) - Payment.teams_paid.through.objects.filter(
            payment__status=Payment.STATUS_SUCCEEDED, team__institution=self.institution).count()
        madjs = AdjudicatorsPerTeamRule.choice_functions[self.tournament.pref('adjudicator_rule')](nadjs)

        idiscounts = self.institution.discount_set.aggregate(discount=Coalesce(Sum('amount',
            filter=Q(currency=self.tournament.pref('currency')) & ~Q(payment__status=Payment.STATUS_SUCCEEDED)), Value(0)))['discount']

        subtotal = self.tournament.pref('adjudicator_fee') * nadjs + self.tournament.pref('team_fee') * nteams
        subtotal += self.tournament.pref('missing_adjudicator_fee') * madjs

        table.add_column({'key': 'item', 'title': _("Item")}, [
            {'text': _("Adjudicators")},
            {'text': _("Teams")},
            {'text': _("Missing Adjudicators")},
            {'text': _("Subtotal"), 'class': 'text-info'},
            {'text': _("Institutional Discounts")},
            {'text': _("Total"), 'class': 'text-info'},
        ])
        table.add_column({'key': 'price', 'title': _("Price")}, [
            *[{'text': "${:,.2f}".format(self.tournament.pref(i+'_fee') / 100)} for i in ('adjudicator', 'team', 'missing_adjudicator')],
            *[{'text': ''} for i in range(3)],
        ])
        table.add_column({'key': 'qtd', 'title': _("Quantity")}, [
            {'text': str(nadjs)},
            {'text': str(nteams)},
            {'text': str(madjs)},
            *[{'text': ''} for i in range(3)],
        ])
        table.add_column({'key': 'total', 'title': _("Total")}, [
            *[{'text': "${:,.2f}".format(self.tournament.pref(i+'_fee')*qtd / 100)} for i, qtd in (
                ('adjudicator', nadjs), ('team', nteams), ('missing_adjudicator', madjs))],
            {'text': "${:,.2f}".format(subtotal / 100), 'class': 'text-info'},
            {'text': "-${:,.2f}".format(idiscounts / 100)},
            {'text': "${:,.2f}".format((subtotal - idiscounts) / 100), 'class': 'text-info'},
        ])
        return table

    def create_payment_intent(self):
        if self.tournament.pref('pay_per_registration'):
            teams = self.institution.team_set.exclude(Exists(
                Payment.teams_paid.through.objects.filter(payment__status=Payment.STATUS_SUCCEEDED, team_id=OuterRef('id'))))
            adjs = self.institution.adjudicator_set.exclude(Exists(Payment.adjudicators_paid.through.objects.filter(
                payment__status=Payment.STATUS_SUCCEEDED, adjudicator_id=OuterRef('id'))), independent=True)
            nadjs = adjs.count()
            discounts = Discount.objects.filter((Q(payment__isnull=True) | ~Q(payment__status=Payment.STATUS_SUCCEEDED)) & (
                Q(team__in=teams) | Q(adjudicator__in=adjs) | Q(institution=self.institution)))
        else:
            teams = (self.institution.accepted_teams or 0) - Payment.teams_paid.through.objects.filter(
                payment__status=Payment.STATUS_SUCCEEDED, team__institution=self.institution).count()
            adjs = (self.institution.accepted_adjudicators or 0) - Payment.adjudicators_paid.through.objects.filter(
                payment__status=Payment.STATUS_SUCCEEDED,
                adjudicator__institution=self.institution, adjudicator__independent=False).count()
            nadjs = adjs
            discounts = Discount.objects.filter(
                (Q(payment__isnull=True) | ~Q(payment__status=Payment.STATUS_SUCCEEDED)) & Q(institution=self.institution))

        madjs = AdjudicatorsPerTeamRule.choice_functions[self.tournament.pref('adjudicator_rule')](nadjs)

        discount_amount = discounts.aggregate(amount=Coalesce(Sum('amount'), Value(0)))['amount']

        session, p = self.create_session(teams=teams, adjudicators=adjs,
            missing_adjs=madjs, discount=discount_amount, institution=self.institution, email=self.request.user.email)
        discounts.update(payment=p)

        return session

    def post(self, request, *args, **kwargs):
        return HttpResponseRedirect(self.create_payment_intent())


class IndividualPaymentView(TournamentMixin, PaymentSessionMixin, RegistrationFormTitlesMixin, TemplateView):
    form_title = gettext_lazy("Pay individual registration")
    template_name = 'individual_payment.html'
    acss_customer_type = 'personal'

    def get_context_data(self, **kwargs):
        obj, obj_type = self.get_object()
        kwargs['object'] = obj
        kwargs['fee'] = self.tournament.pref('adjudicator_fee' if obj_type == 'a' else 'team_fee')
        kwargs['role'] = _("adjudicator") if obj_type == 'a' else _("team")

        payment_filter = Q(teams_paid=obj) if obj_type == 't' else Q(adjudicators_paid=obj)

        kwargs['paid'] = Payment.objects.filter(payment_filter, status=Payment.STATUS_SUCCEEDED).exists()
        kwargs['form'] = None
        return super().get_context_data(**kwargs)

    def get_object(self):
        try:
            self.person = Person.objects.get(url_key=self.kwargs['url_key'])
        except Person.DoesNotExist:
            raise Http404
        if self.person.adjudicator is not None:
            if self.person.adjudicator.tournament != self.tournament:
                raise Http404
            return self.person.adjudicator, 'a'
        elif self.person.speaker.team.tournament != self.tournament:
            raise Http404
        return self.person.speaker.team, 't'

    def create_payment_session(self):
        obj, obj_type = self.get_object()
        payment_kwargs = {}
        if obj_type == 'a':
            payment_kwargs['adjudicators'] = [obj]
        else:
            payment_kwargs['teams'] = [obj]
        return self.create_session(**payment_kwargs, institution=obj.institution, email=self.person.email)[0]

    def post(self, request, *args, **kwargs):
        return HttpResponseRedirect(self.create_payment_session())


class CancelPaymentView(TournamentMixin, View):
    def get(self, request, *args, **kwargs):
        messages.info(request, _("Your payment has been canceled."))
        return HttpResponseRedirect(reverse_tournament("tournament-home", self.tournament))


class SuccessPaymentView(TournamentMixin, View):
    def get(self, request, *args, **kwargs):
        messages.success(request, _("Your payment has been received."))
        return HttpResponseRedirect(reverse_tournament("tournament-home", self.tournament))
