from django.conf import settings
from django_tenants.utils import schema_context


def using_tenant_schema(func):
    def switch_schema(*args, **kwargs):
        if 'event' in kwargs:
            tenant = kwargs['event']['tenant']
        else:
            tenant = args[1].get('tenant')
        with schema_context(tenant):
            return func(*args, **kwargs)
    return switch_schema


def ws_using_tenant_schema(func):
    def switch_schema(*args, **kwargs):
        with schema_context(args[0].scope['schema']):
            return func(*args, **kwargs)
    return switch_schema


def get_postgres_url():
    db = settings.DATABASES['default']
    return 'postgres://%s:%s@%s:%s/%s' % (db['USER'], db['PASSWORD'], db['HOST'], db['PORT'], db['NAME'])
