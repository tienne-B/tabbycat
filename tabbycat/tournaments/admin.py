from django.contrib import admin
from django.db import connection

from .models import Round, Tournament


# ==============================================================================
# Tournament
# ==============================================================================

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'seq', 'short_name', 'current_round', 'active')
    ordering = ('seq', )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not connection.tenant.is_archived

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not connection.tenant.is_archived

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not connection.tenant.is_archived


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
