from django.utils.translation import gettext_lazy as _
from dynamic_preferences.types import BooleanPreference, ChoicePreference, IntegerPreference

from .registries import tournament_preferences_registry


@tournament_preferences_registry.register
class EnableGenderSelection(BooleanPreference):
    verbose_name = _("Enable participant gender selection")
    help_text = _("Add field for participants' gender in the registration form")
    name = 'select_gender'
    default = False


@tournament_preferences_registry.register
class MaximumAdjudicators(IntegerPreference):
    verbose_name = _("Maximum number of adjudicators per institution")
    help_text = _("Maximum number of adjudicators per institution in pre-registration. Use -1 for no limit.")
    name = 'maximum_adjudicators'
    default = -1


@tournament_preferences_registry.register
class MaximumTeams(IntegerPreference):
    verbose_name = _("Maximum number of teams per institution")
    help_text = _("Maximum number of teams per institution in pre-registration. Use -1 for no limit.")
    name = 'maximum_teams'
    default = -1


@tournament_preferences_registry.register
class ChooseNames(BooleanPreference):
    verbose_name = _("Allow teams to create their team name")
    help_text = _("Adds a field in team registration for a custom team name")
    name = 'choose_names'
    default = True


@tournament_preferences_registry.register
class ChooseEmoji(BooleanPreference):
    verbose_name = _("Allow teams to choose their emoji")
    help_text = _("Adds a field in team registration for a custom unused emoji/code name")
    name = 'choose_emoji'
    default = False


@tournament_preferences_registry.register
class SelectCategories(BooleanPreference):
    verbose_name = _("Allow team speakers to categorise themselves")
    help_text = _("Adds a field in team registration for speakers to select their speaker categories")
    name = 'select_categories'
    default = True


@tournament_preferences_registry.register
class NumberOfSpeakers(IntegerPreference):
    verbose_name = _("Number of speakers per team")
    help_text = _("How many speakers does each team contain (as a maximum)")
    name = 'max_speakers'
    default = 2


@tournament_preferences_registry.register
class MinimalSpeakers(IntegerPreference):
    verbose_name = _("Minimum number of speakers")
    help_text = _("The minimal number of speakers in a team")
    name = 'min_speakers'
    default = 2


@tournament_preferences_registry.register
class IncludeInstitution(BooleanPreference):
    verbose_name = _("Include institution in team names")
    help_text = _("To append the institution's name onto team names, even if custom.")
    name = 'include_institution'
    default = False


@tournament_preferences_registry.register
class PaymentCurrency(ChoicePreference):
    verbose_name = _("Currency to charge fees")
    help_text = _("The currency in which the payments will be made")
    name = 'currency'
    choices = (
        ('AUD', _("Australian Dollar")),
        ('CAD', _("Canadian Dollar")),
        ('EUR', _("Euro")),
        ('USD', _("United States Dollar")),
    )
    default = 'CAD'


@tournament_preferences_registry.register
class TeamFee(IntegerPreference):
    verbose_name = _("Team registration fee")
    help_text = _("The team registration fee in the smallest denomination (20$ becomes 2000)")
    name = 'team_fee'
    default = 2000


@tournament_preferences_registry.register
class AdjudicatorFee(IntegerPreference):
    verbose_name = _("Adjudicator registration fee")
    help_text = _("The adjudicator registration fee in the smallest denomination (20$ becomes 2000)")
    name = 'adjudicator_fee'
    default = 2000


@tournament_preferences_registry.register
class EnableInstitutionRegistration(BooleanPreference):
    verbose_name = _("Enable institution registration with participants")
    help_text = _("Institutions may register and may add participants to their approved limit")
    name = 'enable_institutions'
    default = True


@tournament_preferences_registry.register
class EnableIndependentTeamRegistration(BooleanPreference):
    verbose_name = _("Enable team registration without institution")
    help_text = _("Teams may register without an institution as intermediary")
    name = 'enable_teams'
    default = False


@tournament_preferences_registry.register
class EnableIndependentAdjudicatorRegistration(BooleanPreference):
    verbose_name = _("Enable adjudicator registration without institution")
    help_text = _("Adjudicators may register without an institution as intermediary")
    name = 'enable_adjs'
    default = True


@tournament_preferences_registry.register
class PayByRegisteredTeams(BooleanPreference):
    verbose_name = _("Have institutions pay per registered participant")
    help_text = _("The alternative is that institutions pay by the number of approved participants, before their details")
    name = 'pay_per_registration'
    default = False


@tournament_preferences_registry.register
class AdjudicatorsPerTeamRule(ChoicePreference):
    verbose_name = _("Institutional adjudicator rule")
    help_text = _("How many adjudicators must an institution provide from the number of teams")
    name = 'adjudicator_rule'
    choices = (
        ('0', _("No adjudicators (0)")),
        ('N', _("One adjudicator per team (n)")),
        ('N-1', _("One adjudicator per team starting with the second team (n-1)")),
    )
    default = '0'

    choice_functions = {
        '0': lambda n: 0,
        'N': lambda n: n,
        'N-1': lambda n: max(0, n-1),
    }


@tournament_preferences_registry.register
class MissingAdjudicatorFee(IntegerPreference):
    verbose_name = _("Missing adjudicator fee")
    help_text = _("The fee for not registering the required number of adjudicators, in the smallest denomination.")
    name = 'missing_adjudicator_fee'
    default = 0


@tournament_preferences_registry.register
class RequireInstitutionRegistration(BooleanPreference):
    verbose_name = _("Require institution registration")
    help_text = _("Require institutions to request slots before registration")
    name = 'require_slots'
    default = False
