from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import admin
from django.core.management import call_command
from django.db import connection
from django.utils.translation import gettext_lazy as _, ngettext_lazy
from django_tenants.admin import TenantAdminMixin
from django_tenants.utils import get_public_schema_name

from .models import Client, Instance


class HideFromTenantsMixin:
    """
    Hides public models from tenants
    """

    def has_add_permission(self, request):
        return super().has_add_permission(request) and request.tenant.schema_name == get_public_schema_name()

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and request.tenant.schema_name == get_public_schema_name()

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and request.tenant.schema_name == get_public_schema_name()

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and request.tenant.schema_name == get_public_schema_name()


class DomainInline(admin.TabularInline):
    model = Instance


@admin.register(Client)
class ClientAdmin(TenantAdminMixin, HideFromTenantsMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'user', 'created_on', 'archive', 'paid')
    list_editable = ('archive',)
    search_fields = ('schema_name', 'name', 'user__username')
    inlines = (DomainInline,)
    actions = ['create_schema', 'delete_schema', 'migrate_schema', 'create_migrate_schema']

    def create_schema(self, request, queryset):
        for client in queryset:
            with connection.cursor() as cursor:
                cursor.execute('CREATE SCHEMA "%s"' % client.schema_name)

        num_schemas = queryset.count()
        self.message_user(request, ngettext_lazy(
            "%(count)d schema was created.",
            "%(count)d schemas were created.",
            num_schemas,
        ) % {'count': num_schemas})
    create_schema.short_description = _("Create Schema")

    def delete_schema(self, request, queryset):
        num_schemas = queryset.count()
        for client in queryset:
            client.delete(force_drop=True)
        self.message_user(request, ngettext_lazy(
            "%(count)d schema was dropped.",
            "%(count)d schemas were dropped.",
            num_schemas,
        ) % {'count': num_schemas})
    delete_schema.short_description = _("Drop Schema")

    def migrate_schema(self, request, queryset):
        for client in queryset:
            call_command('migrate_schemas',
                tenant=True,
                schema_name=client.schema_name,
                interactive=False,
                verbosity=1)

        num_schemas = queryset.count()
        self.message_user(request, ngettext_lazy(
            "%(count)d schema was migrated.",
            "%(count)d schemas were migrated.",
            num_schemas,
        ) % {'count': num_schemas})
    migrate_schema.short_description = _("Migrate Schema")

    def create_migrate_schema(self, request, queryset):
        for client in queryset:
            async_to_sync(get_channel_layer().send)("portal", {
                "type": "create_schema",
                "client": client.id,
            })

        num_schemas = queryset.count()
        self.message_user(request, ngettext_lazy(
            "%(count)d schema is being created and migrated.",
            "%(count)d schemas is being created and migrated.",
            num_schemas,
        ) % {'count': num_schemas})
    create_migrate_schema.short_description = _("Create and Migrate")
