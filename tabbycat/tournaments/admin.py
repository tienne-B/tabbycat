from django.contrib import admin

from .models import Round, Tournament


# ==============================================================================
# Tournament
# ==============================================================================

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'seq', 'short_name', 'current_round', 'active')
    ordering = ('seq', )

    def has_add_permission(self, request):
        full = request.tenant.schema_name != 'public' and request.tenant.number_tournaments <= Tournament.objects.all().count()
        return super().has_add_permission(request) and not (request.tenant.is_archived or full)

    def has_change_permission(self, request, obj=None):
        full = request.tenant.schema_name != 'public' and request.tenant.number_tournaments < Tournament.objects.all().count()
        return super().has_change_permission(request, obj) and not (request.tenant.is_archived or full)

    def has_delete_permission(self, request, obj=None):
        return request.tenant.schema_name == 'public'


# ==============================================================================
# Round
# ==============================================================================

@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ('name', 'tournament', 'seq', 'abbreviation', 'stage',
                    'draw_type', 'draw_status', 'feedback_weight', 'silent',
                    'motions_released', 'starts_at', 'completed')
    list_editable = ('seq', 'draw_status', 'feedback_weight', 'silent',
                     'motions_released', 'completed')
    list_filter = ('tournament', )
    search_fields = ('name', 'seq', 'abbreviation', 'stage', 'draw_type', 'draw_status')
    ordering = ('tournament__slug', 'seq')
