from django.contrib import admin
from django.db.models import F
from django_tenants.utils import schema_context

from utils.admin import ModelAdmin

from .models import Round, Tournament


# ==============================================================================
# Tournament
# ==============================================================================

@admin.register(Tournament)
class TournamentAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'seq', 'short_name', 'current_round', 'active')
    ordering = ('seq', )

    def has_add_permission(self, request):
        full = request.tenant.schema_name != 'public' and request.tenant.number_tournaments <= Tournament.objects.all().count()
        return super().has_add_permission(request) and not (request.tenant.is_archived or full)

    def has_change_permission(self, request, obj=None):
        full = request.tenant.schema_name != 'public' and request.tenant.number_tournaments < Tournament.objects.all().count()
        return super().has_change_permission(request, obj) and not (request.tenant.is_archived or full)

    def delete_queryset(self, request, queryset):
        tenant = request.tenant
        if tenant.schema_name != 'public':
            count = queryset.count()
            with schema_context('public'):
                tenant.number_tournaments = F('number_tournaments') - count
                tenant.save()
        return super().delete_queryset(request, queryset)

    def delete_model(self, request, obj):
        tenant = request.tenant
        with schema_context('public'):
            tenant.number_tournaments = F('number_tournaments') - 1
            tenant.save()
        return super().delete_model(request, obj)


# ==============================================================================
# Round
# ==============================================================================

@admin.register(Round)
class RoundAdmin(ModelAdmin):
    list_display = ('name', 'tournament', 'seq', 'abbreviation', 'stage',
                    'draw_type', 'draw_status', 'feedback_weight', 'silent',
                    'motions_released', 'starts_at', 'completed')
    list_editable = ('feedback_weight', 'silent', 'motions_released', 'completed')
    list_filter = ('tournament', )
    search_fields = ('name', 'seq', 'abbreviation', 'stage', 'draw_type', 'draw_status')
    ordering = ('tournament__slug', 'seq')
