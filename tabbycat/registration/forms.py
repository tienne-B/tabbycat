from hashlib import sha1
from time import time
from urllib.parse import urlparse

import requests
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from dynamic_preferences.forms import preference_form_builder, PreferenceForm

from portal.forms import CalendarDateInputWidget

from .models import Adjudicator, IAApplicant, IATournament, Institution, Speaker, Team, Tournament
from .registries import tournament_preferences_registry


class TournamentPreferenceForm(PreferenceForm):
    registry = tournament_preferences_registry


def tournament_preference_form_builder(instance, preferences=[], **kwargs):
    return preference_form_builder(TournamentPreferenceForm, preferences, model={'instance': instance}, **kwargs)


def create_url_key(tournament, name):
    s = "%s/%s/%d" % (tournament.slug, name, int(time()))
    return sha1(s.encode('utf-8')).hexdigest()[:24]


class CreateTournamentFromURL(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ('external_url', 'api_token', 'date')
        labels = {
            "external_url": _("Tabbycat tournament URL"),
        }
        widgets = {
            'date': CalendarDateInputWidget,
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def clean_external_url(self):
        parsed = urlparse(self.cleaned_data['external_url'])
        path = parsed.path.split('/')
        if not parsed.netloc:
            raise ValidationError(_("Full URL to the tournament's page is required."))
        if len(path) < 3:
            raise ValidationError(_("Tournament must be in URL."))
        elif len(path) == 3:
            parsed = parsed._replace(path="/api/v1/tournaments/" + path[1])
        elif path[1:3] != ['api', 'v1', 'tournaments'] or len(path) > 5:
            raise ValidationError(_("URL must either be the tournament public home page or API detail endpoint."))

        t = requests.get(parsed.geturl())
        if t.status_code == '401':
            raise ValidationError(_("API is disabled on the site."))
        if t.status_code == '404':
            raise ValidationError(_("Tournament not found."))
        return t.json()['url']

    def save(self, commit=True):
        tournament = super().save(commit=False)

        api_result = requests.get(self.cleaned_data['external_url']).json()
        tournament.name = api_result['name']
        tournament.short_name = api_result['short_name']
        tournament.slug = api_result['slug']
        if Tournament.objects.filter(slug=api_result['slug']).exists():
            tournament.slug += tournament.date.strftime("%Y-%m-%d")

        if commit:
            tournament.save()
            tournament.managers.add(self.request.user)
        return tournament


class CreateInstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ('name', 'code', 'requested_teams', 'requested_adjudicators')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        self.tournament = kwargs.pop('tournament')
        super().__init__(*args, **kwargs)

        if not self.tournament.pref('require_slots'):
            self.fields.pop('requested_teams')
            self.fields.pop('requested_adjudicators')

    def save(self, commit=True):
        institution = super().save(commit=False)
        institution.tournament = self.tournament
        institution.manager = self.request.user

        if commit:
            institution.save()
        return institution


class TeamDetailsForm(forms.ModelForm):

    class Meta:
        model = Team
        fields = ('reference', 'institution', 'emoji')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.tournament = kwargs.pop('tournament')
        self.institution = kwargs.pop('institution', None)
        super().__init__(*args, **kwargs)

        self.fields['institution'].queryset = Institution.objects.filter(tournament=self.tournament)
        self.remove_team_fields()
        if 'emoji' in self.fields:
            self.populate_emojis()
        self.create_speaker_fields()

    @staticmethod
    def _get_speaker_name_field(seq):
        return 'speaker_%d_name' % seq

    @staticmethod
    def _get_speaker_email_field(seq):
        return 'speaker_%d_email' % seq

    @staticmethod
    def _get_speaker_categories_field(seq):
        return 'speaker_%d_categories' % seq

    @staticmethod
    def _get_speaker_gender_field(seq):
        return 'speaker_%d_gender' % seq

    def remove_team_fields(self):
        if not self.tournament.pref('choose_names'):
            self.fields.pop('reference')
        if not self.tournament.pref('choose_emoji'):
            self.fields.pop('emoji')
        if self.institution is not None:
            self.fields.pop('institution')

    def populate_emojis(self):
        emoji_request = requests.options(self.tournament.api_url + "/teams")
        if emoji_request.status_code == 200:
            team_options = emoji_request.json()
            if 'actions' not in team_options:
                self.fields.pop('emoji')
                return
            emoji_list = team_options['actions']['POST']['emoji']['choices']
            self.fields['emoji'].choices = [(c['value'], c['display_name']) for c in emoji_list]
        else:
            self.fields.pop('emoji')

    def create_speaker_fields(self):
        categories = self.tournament.speakercategory_set.all()
        select_categories = self.tournament.pref('select_categories') and categories.exists()
        for i in range(self.tournament.pref('max_speakers')):
            required = i < self.tournament.pref('min_speakers')
            self.fields[self._get_speaker_name_field(i)] = forms.CharField(
                max_length=70, required=required,
                label=_("Speaker %d name") % (i+1,))
            self.fields[self._get_speaker_email_field(i)] = forms.EmailField(required=required, label=_("Speaker %d email") % (i+1,))
            if select_categories:
                self.fields[self._get_speaker_categories_field(i)] = forms.ModelMultipleChoiceField(
                    queryset=categories, required=False, label=_("Speaker %d categories") % (i+1,))
            if self.tournament.pref('select_gender'):
                self.fields[self._get_speaker_gender_field(i)] = forms.ChoiceField(
                    choices=Speaker.GENDER_CHOICES, required=False, label=_("Speaker %d gender") % (i+1,))

    def save(self, commit=True):
        # First save the team, then create the speakers
        institution = self.cleaned_data.get('institution', self.institution)
        team = super().save(commit=False)

        override_name = not (self.tournament.pref('choose_names') and self.cleaned_data.get('reference'))
        if override_name:
            team.reference = "".join(
                self.cleaned_data[self._get_speaker_name_field(i)][-1][0] for i in range(self.tournament.pref('max_speakers')))
        team.short_reference = team.reference[:35]
        use_prefix = override_name or (self.tournament.pref('include_institution') and institution is not None)
        team.use_institution_prefix = use_prefix
        team.tournament = self.tournament
        team.institution = institution
        team.manager = self.request.user

        if commit:
            team.save()

        speakers = {}
        for i in range(self.tournament.pref('max_speakers')):
            if self.cleaned_data[self._get_speaker_name_field(i)] == '':
                break
            speaker = Speaker(team=team,
                name=self.cleaned_data[self._get_speaker_name_field(i)],
                email=self.cleaned_data[self._get_speaker_email_field(i)],
                gender=self.cleaned_data.get(self._get_speaker_gender_field(i), ''))
            speaker.url_key = create_url_key(team.tournament, speaker.name)
            if commit:
                speaker.save()
            speakers[speaker] = self.cleaned_data.get(self._get_speaker_categories_field(i), [])

        if commit:
            for speaker, categories in speakers.items():
                if len(categories) > 0:
                    speaker.categories.set(categories)

        return team


class AdjudicatorDetailsForm(forms.ModelForm):

    class Meta:
        model = Adjudicator
        fields = ('name', 'email', 'gender', 'institution')

    def __init__(self, *args, **kwargs):
        self.tournament = kwargs.pop('tournament')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        self.fields['institution'].queryset = Institution.objects.filter(tournament=self.tournament)
        if not self.tournament.pref('select_gender'):
            self.fields.pop('gender')

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.url_key = create_url_key(self.tournament, obj.name)
        obj.tournament = self.tournament
        obj.manager = self.user

        if commit:
            obj.save()
        return obj


class InstitutionApproveForm(forms.Form):

    def __init__(self, tournament, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tournament = tournament
        self.create_fields()

    def get_table_field(self, institution, participant):
        return self[getattr(self, "_fieldname_accepted_" + participant)(institution)].as_widget(attrs={'class': 'form-control'})

    @staticmethod
    def _fieldname_accepted_teams(institution):
        return 'accepted_teams_%d' % (institution.pk,)

    @staticmethod
    def _fieldname_accepted_adjs(institution):
        return 'accepted_adjs_%d' % (institution.pk,)

    def create_fields(self):
        for institution in self.tournament.institution_set.all():
            self.fields[self._fieldname_accepted_teams(institution)] = forms.IntegerField(min_value=0, required=False)
            self.initial[self._fieldname_accepted_teams(institution)] = institution.accepted_teams or 0

            self.fields[self._fieldname_accepted_adjs(institution)] = forms.IntegerField(min_value=0, required=False)
            self.initial[self._fieldname_accepted_adjs(institution)] = institution.accepted_adjudicators or 0

    def save(self):
        institutions = self.tournament.institution_set.all()
        for institution in institutions:
            institution.accepted_teams = self.cleaned_data[self._fieldname_accepted_teams(institution)]
            institution.accepted_adjudicators = self.cleaned_data[self._fieldname_accepted_adjs(institution)]
        Institution.objects.bulk_update(institutions, ['accepted_teams', 'accepted_adjudicators'])


class IADetailsForm(forms.ModelForm):

    class Meta:
        model = IAApplicant
        fields = ('name', 'email')

    def __init__(self, *args, **kwargs):
        self.tournament = kwargs.pop('tournament')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tournament = self.tournament

        if commit:
            obj.save()
        return obj


class CategoryModelChoiceField(forms.ModelChoiceField):

    def __init__(self, *args, **kwargs):
        kwargs['empty_label'] = _("Other")
        super().__init__(*args, **kwargs)


class LastRoundChoiceField(forms.ChoiceField):

    def __init__(self, *args, **kwargs):
        kwargs['empty_label'] = "No Breakeaste"
        super().__init__(*args, **kwargs)


class IATournamentForm(forms.ModelForm):

    all_rounds = (
        "Open PDOs",
        "Open Octos",
        "Open Quarters",
        "Open Semis",
        "Open Final",
        "ESL Quarters",
        "ESL Semis",
        "ESL Final",
        "EFL Semis",
        "EFL Final",
        "Pre-octavos",
        "Octavos",
        "Cuartos",
        "Semis",
        "Final Open",
        "Final ELE",
        "Semis Novates",
        "Final Novates",
    )

    rooms = forms.ChoiceField(choices=(
        (1, _("Less than 10 rooms")),
        (10, _("10-20 rooms")),
        (20, _("20-30 rooms")),
        (30, _("30-40 rooms")),
        (40, _("More than 40 rooms")),
    ), label="Número de salas", required=True)

    last_round = forms.ChoiceField(choices=((r, r) for r in all_rounds), required=False)
    last_round_chair = forms.ChoiceField(choices=((r, r) for r in all_rounds), required=False)

    class Meta:
        model = IATournament
        exclude = ('application',)
        field_classes = {
            'category': CategoryModelChoiceField,
        }
        labels = {
            'category': "Torneo",
            'year': "Año",
            'role': "Como persona",
            'not_bp': "¿Este torneo era temático, interno y/o de un formato diferente al Parlamentario Británico?",
        }

    def __init__(self, *args, **kwargs):
        self.application = kwargs.pop('application', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.application = self.application

        if commit:
            obj.save()
        return obj
