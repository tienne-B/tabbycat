from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from dynamic_preferences.models import PerInstancePreferenceModel

from participants.emoji import EMOJI_FIELD_CHOICES

from .preferences import PaymentCurrency
from .registries import tournament_preferences_registry


class Tournament(models.Model):
    name = models.CharField(max_length=100,
        verbose_name=_("name"),
        help_text=_("The full name, e.g. \"Australasian Intervarsity Debating Championships 2016\""))
    short_name = models.CharField(max_length=25, blank=True, default="",
        verbose_name=_("short name"),
        help_text=_("The name used in the menu, e.g. \"Australs 2016\""))
    slug = models.SlugField(unique=True,
        verbose_name=_("slug"),
        help_text=_("The sub-URL of the tournament, cannot have spaces, e.g. \"australs2016\""))
    active = models.BooleanField(verbose_name=_("active"), default=True)
    date = models.DateField(auto_now=False, verbose_name=_("start date"),
        help_text=_("When will the tournament start"))

    external_url = models.URLField(null=True, verbose_name=_("external URL"))
    api_token = models.CharField(null=True, max_length=50, verbose_name=_("API token"))

    connected_account = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("connected account"))
    fee_rate = models.FloatField(default=0.03, verbose_name=_("fee percentage"))

    managers = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("managers"))

    class Meta:
        verbose_name = _('tournament')
        verbose_name_plural = _('tournaments')

    def __init__(self, *args, **kwargs):
        self._prefs = {}
        return super().__init__(*args, **kwargs)

    def __str__(self):
        return self.name

    def pref(self, name):
        """Keep a record in this instance, to avoid hitting the cache
        unnecessarily. Note that this means that, if a tournament preference is
        changed, an instance of the Tournament (Python) object that has already
        queries that preference value won't pick up on the change."""
        try:
            return self._prefs[name]
        except KeyError:
            self._prefs[name] = self.preferences.get_by_name(name)
            return self._prefs[name]


class TournamentPreferenceModel(PerInstancePreferenceModel):

    instance = models.ForeignKey(Tournament, models.CASCADE, related_name="preferences",
        verbose_name=_("instance"))
    registry = tournament_preferences_registry

    class Meta(PerInstancePreferenceModel.Meta):
        app_label = "registration"
        verbose_name = _("tournament preference")
        verbose_name_plural = _("tournament preferences")


class Institution(models.Model):
    name = models.CharField(max_length=100,
        verbose_name=_("name"),
        # Translators: Change the examples to institutions native to your language; keep consistent between strings
        help_text=_("The institution's full name, e.g., \"University of Cambridge\", \"Victoria University of Wellington\""))
    code = models.CharField(max_length=20,
        verbose_name=_("code"),
        # Translators: Change the examples to institutions native to your language; keep consistent between strings
        help_text=_("What the institution is typically called for short, e.g., \"Cambridge\", \"Vic Wellington\""))

    tournament = models.ForeignKey(Tournament, models.CASCADE,
        verbose_name=_("tournament"))
    external_url = models.URLField(null=True, verbose_name=_("external URL"))

    requested_teams = models.PositiveIntegerField(null=True, verbose_name=_("teams requested"))
    accepted_teams = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("teams accepted"))

    requested_adjudicators = models.PositiveIntegerField(null=True, verbose_name=_("adjudicators requested"))
    accepted_adjudicators = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("adjudicators accepted"))

    manager = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("manager"))

    class Meta:
        unique_together = [('name', 'tournament'), ('code', 'tournament')]
        ordering = ['name']
        verbose_name = _("institution")
        verbose_name_plural = _("institutions")

    def __str__(self):
        return self.name


class SpeakerCategory(models.Model):
    tournament = models.ForeignKey(Tournament, models.CASCADE,
        verbose_name=_("tournament"))
    external_url = models.URLField(null=True, verbose_name=_("external URL"))

    name = models.CharField(max_length=50,
        verbose_name=_("name"),
        # Translators: Translate ESL to the acronym for "<target language> as a second/foreign language", not "English"
        help_text=_("Name to be displayed, e.g., \"Novice\", \"ESL\""))
    slug = models.SlugField(
        verbose_name=_("slug"),
        # Translators: Translate esl to the acronym for "<target language> as a second/foreign language", not "English"
        help_text=_("Slug for URLs, e.g., \"novice\", \"esl\""))
    seq = models.IntegerField(
        verbose_name=_("sequence number"),
        help_text=_("The order in which the categories are displayed"))

    class Meta:
        unique_together = [('tournament', 'seq'), ('tournament', 'slug')]
        ordering = ['tournament', 'seq']
        index_together = ['tournament', 'seq']
        verbose_name = _("speaker category")
        verbose_name_plural = _("speaker categories")

    def __str__(self):
        return "[{}] {}".format(self.tournament.slug, self.name)


class Person(models.Model):
    name = models.CharField(max_length=70, db_index=True,
        verbose_name=_("name"))
    email = models.EmailField(blank=True, null=True,
        verbose_name=_("email address"))
    url_key = models.SlugField(blank=True, null=True, unique=True, max_length=24,
        verbose_name=_("URL key"))

    GENDER_MALE = 'M'
    GENDER_FEMALE = 'F'
    GENDER_OTHER = 'O'
    GENDER_CHOICES = ((GENDER_MALE,   _("male")),
                      (GENDER_FEMALE, _("female")),
                      (GENDER_OTHER,  _("other")))
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True,
        verbose_name=_("gender"),
        help_text=_("Gender is displayed in the adjudicator allocation interface, and nowhere else"))

    class Meta:
        verbose_name = _("person")
        verbose_name_plural = _("persons")

    def __str__(self):
        return str(self.name)


class Team(models.Model):
    reference = models.CharField(blank=True, max_length=150,
        verbose_name=_("full name/suffix"),
        help_text=_("Do not include institution name (see \"uses institutional prefix\" below)"))
    short_reference = models.CharField(blank=True, max_length=35,
        verbose_name=_("short name/suffix"),
        help_text=_("The name shown in the draw. Do not include institution name (see \"uses institutional prefix\" below)"))
    code_name = models.CharField(blank=True, max_length=150,
        verbose_name=_("code name"),
        help_text=_("Name used to obscure institutional identity on public-facing pages"))

    short_name = models.CharField(editable=False, max_length=20+1+35,  # Max institution code + space + short_reference max
        verbose_name=_("short name"),
        help_text=_("The name shown in the draw, including institution name. (This is autogenerated.)"))
    long_name = models.CharField(editable=False, max_length=100+1+150,  # Max institution name + space + reference max
        verbose_name=_("long name"),
        help_text=_("The full name of the team, including institution name. (This is autogenerated.)"))

    institution = models.ForeignKey(Institution, models.SET_NULL, blank=True, null=True,
        verbose_name=_("institution"))
    tournament = models.ForeignKey(Tournament, models.CASCADE,
        verbose_name=_("tournament"))
    use_institution_prefix = models.BooleanField(default=False,
        verbose_name=_("Uses institutional prefix"),
        help_text=_("If ticked, a team called \"1\" from Victoria will be shown as \"Victoria 1\""))

    emoji = models.CharField(max_length=3, default=None, choices=EMOJI_FIELD_CHOICES,
        blank=True, null=True,   # uses null=True to allow multiple teams to have no emoji
        verbose_name=_("emoji"))

    external_url = models.URLField(null=True, verbose_name=_("external URL"))
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("manager"))

    class Meta:
        unique_together = [
            ('reference', 'institution', 'tournament'),
            ('emoji', 'tournament'),
        ]
        ordering = ['tournament', 'institution', 'short_reference']
        index_together = ['tournament', 'institution', 'short_reference']
        verbose_name = _("team")
        verbose_name_plural = _("teams")

    def __str__(self):
        return "[{}] {}".format(self.tournament.slug, self.short_name)

    def _construct_short_name(self):
        reference = self.short_reference or self.reference
        if self.use_institution_prefix and self.institution is not None:
            short_name = self.institution.code
            if reference:
                short_name += " " + str(reference)[:35]
            return short_name
        else:
            return str(reference)[:20+1+35]

    def _construct_long_name(self):
        if self.use_institution_prefix and self.institution is not None:
            long_name = self.institution.name
            if self.reference:
                long_name += " " + self.reference
            return long_name
        else:
            return self.reference

    @cached_property
    def speakers(self):
        return self.speaker_set.all()

    @property
    def name(self):
        return self.short_name

    def clean(self):
        # Require reference and short_reference if use_institution_prefix is False
        errors = {}
        if self.use_institution_prefix and self.institution is None:
            errors['institution'] = _("Teams must have an institution if they are using the institutional prefix.")
        if not self.use_institution_prefix and not self.reference:
            errors['reference'] = _("Teams must have a full name if they don't use the institutional prefix.")
        if not self.use_institution_prefix and not self.short_reference:
            errors['short_reference'] = _("Teams must have a short name if they don't use the institutional prefix.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Override the short and long names before saving
        self.short_name = self._construct_short_name()
        self.long_name = self._construct_long_name()
        super().save(*args, **kwargs)


class Speaker(Person):
    team = models.ForeignKey(Team, models.CASCADE,
        verbose_name=_("team"))
    categories = models.ManyToManyField(SpeakerCategory, blank=True,
        verbose_name=_("speaker categories"))

    class Meta:
        verbose_name = _("speaker")
        verbose_name_plural = _("speakers")

    def __str__(self):
        return str(self.name)

    @property
    def tournament(self):
        return self.team.tournament


class Adjudicator(Person):
    institution = models.ForeignKey(Institution, models.SET_NULL, blank=True, null=True,
        verbose_name=_("institution"))
    tournament = models.ForeignKey(Tournament, models.CASCADE,
        verbose_name=_("tournament"))
    external_url = models.URLField(null=True, verbose_name=_("external URL"))
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("manager"))

    independent = models.BooleanField(default=False, blank=True,
        verbose_name=_("independent"))

    class Meta:
        verbose_name = _("adjudicator")
        verbose_name_plural = _("adjudicators")

    def __str__(self):
        if self.institution is None:
            return self.name
        else:
            return "%s (%s)" % (self.name, self.institution.code)


class Payment(models.Model):
    STATUS_REQUIRES_PAYMENT_METHOD = 'requires_payment_method'
    STATUS_REQUIRES_CONFIRMATION = 'requires_confirmation'
    STATUS_REQUIRES_ACTION = 'requires_action'
    STATUS_PROCESSING = 'processing'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_CANCELLED = 'canceled'
    STATUS_CHOICES = (
        (STATUS_REQUIRES_PAYMENT_METHOD, _("requires payment method")),
        (STATUS_REQUIRES_CONFIRMATION, _("requires confirmation")),
        (STATUS_REQUIRES_ACTION, _("requires action")),
        (STATUS_PROCESSING, _("processing")),
        (STATUS_SUCCEEDED, _("succeeded")),
        (STATUS_CANCELLED, _("cancelled")),
    )

    PROCESSOR_STRIPE = 'stripe'
    PROCESSOR_CASH = 'cash'
    PROCESSOR_VOID = 'void'
    PROCESSOR_OPTIONS = (
        (PROCESSOR_STRIPE, _("by Stripe")),
        (PROCESSOR_CASH, _("by cash")),
        (PROCESSOR_VOID, _("Ignore payment")),
        ('', _("Other")),
    )

    tournament = models.ForeignKey(Tournament, models.PROTECT, verbose_name=_("tournament"))
    payment_intent = models.CharField(max_length=30, null=True, verbose_name=_("payment intent"))
    processor = models.CharField(max_length=6, choices=PROCESSOR_OPTIONS, blank=True, verbose_name=_("processor"))

    paid_on = models.DateTimeField(auto_now_add=False, null=True, verbose_name=_("paid on"))
    status = models.CharField(max_length=23, choices=STATUS_CHOICES, default=STATUS_REQUIRES_PAYMENT_METHOD, verbose_name=_("status"))

    amount_paid = models.IntegerField(default=0, verbose_name=_("amount paid"))
    currency = models.CharField(max_length=3, choices=PaymentCurrency.choices, verbose_name=_("currency"))

    institution = models.ForeignKey(Institution, models.PROTECT, blank=True, verbose_name=_("institution"))
    teams_paid = models.ManyToManyField(Team, verbose_name=_("teams paid"))
    adjudicators_paid = models.ManyToManyField(Adjudicator, verbose_name=_("adjudicators paid"))

    num_teams = models.PositiveIntegerField(default=0, verbose_name=_("number of teams"))
    num_adjudicators = models.PositiveIntegerField(default=0, verbose_name=_("number of adjudicators"))

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")

    def __str__(self):
        return self.payment_intent

    @property
    def amount_fees(self):
        return self.amount_paid - self.amount_received


class Discount(models.Model):
    team = models.ForeignKey(Team, models.CASCADE, null=True, blank=True, verbose_name=_("team"))
    adjudicator = models.ForeignKey(Adjudicator, models.CASCADE, null=True, blank=True, verbose_name=_("adjudicator"))
    institution = models.ForeignKey(Institution, models.CASCADE, null=True, blank=True, verbose_name=_("institution"))

    amount = models.IntegerField(verbose_name=_("amount"))
    currency = models.CharField(max_length=3, choices=PaymentCurrency.choices, verbose_name=_("currency"))
    payment = models.ForeignKey(Payment, models.CASCADE, null=True, blank=True, verbose_name=_("payment"))

    class Meta:
        verbose_name = _("discount")
        verbose_name_plural = _("discounts")

    def __str__(self):
        if self.team is not None:
            return "Team Discount: %s" % (self.team.short_name,)
        if self.adjudicator is not None:
            return "Adj Discount: %s" % (self.adjudicator.name,)
        return "Unknown Discount"
