from channels.consumer import SyncConsumer
from django.db import connection
from django_tenants.utils import schema_context

from .models import Client


class PortalQueueConsumer(SyncConsumer):

    def create_schema(self, event):
        client = Client.objects.get(id=event.get('client'))

        client.create_schema()

        # Copy user to new site
        if client.user is not None:
            user_model = client.user.__class__
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO " + client.schema_name + ".auth_user SELECT * FROM public.auth_user WHERE id=%d" %
                    client.user.pk)
                cursor.execute(
                    "INSERT INTO " + client.schema_name + ".authtoken_token SELECT * FROM public.authtoken_token WHERE user_id=%d" %
                    client.user.pk)
            with schema_context(client.schema_name):
                user_model.objects.filter(pk=client.user.pk).update(is_staff=True, is_superuser=True)
