from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import admin
from django.core.management import call_command
from django.db import connection
from django.utils.translation import gettext_lazy as _, ngettext_lazy
from django_tenants.admin import TenantAdminMixin

from .models import Client, Instance


class DomainInline(admin.TabularInline):
    model = Instance


@admin.register(Client)
class ClientAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'user', 'created_on', 'archive', 'paid')
    list_editable = ('archive', 'paid')
    search_fields = ('schema_name', 'name', 'user__username')
    inlines = (DomainInline,)
    actions = ['create_schema', 'migrate_schema', 'create_migrate_schema']

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
