from django.contrib import admin
from dynamic_preferences.admin import PerInstancePreferenceAdmin

from portal.admin import HideFromTenantsMixin

from .models import Adjudicator, Institution, Payment, Speaker, SpeakerCategory, Team, Tournament, TournamentPreferenceModel


@admin.register(Tournament)
class TournamentAdmin(HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('name', 'slug', 'active', 'date')
    ordering = ('date',)


@admin.register(TournamentPreferenceModel)
class TournamentPreferenceAdmin(HideFromTenantsMixin, PerInstancePreferenceAdmin):
    pass


@admin.register(Institution)
class InstitutionAdmin(HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('name', 'code', 'tournament', 'manager')
    list_select_related = ('tournament', 'manager')
    ordering = ('name',)
    search_fields = ('tournament', 'name')


@admin.register(SpeakerCategory)
class SpeakerCategoryAdmin(HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('name', 'slug', 'seq', 'tournament')
    list_filter = ('tournament',)
    ordering = ('tournament', 'seq')


class SpeakerInline(admin.TabularInline):
    model = Speaker
    fields = ('name', 'email', 'gender')


@admin.register(Team)
class TeamAdmin(HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('long_name', 'short_name', 'emoji', 'institution', 'tournament')
    list_select_related = ('tournament', 'institution')
    search_fields = ('reference', 'short_name', 'institution__name',
                     'institution__code', 'tournament__name')
    list_filter = ('tournament', 'institution')
    inlines = (SpeakerInline,)


@admin.register(Adjudicator)
class AdjudicatorAdmin(HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('name', 'institution', 'tournament', 'independent')
    search_fields = ('name', 'tournament__name', 'institution__name', 'institution__code')
    list_filter = ('tournament', 'institution')
    list_editable = ('independent',)


@admin.register(Payment)
class PaymentAdmin(HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('payment_intent', 'tournament', 'institution', 'status', 'amount_paid', 'paid_on')
    list_select_related = ('tournament', 'institution')
    search_fields = ('payment_intent',)
    list_filter = ('tournament',)
