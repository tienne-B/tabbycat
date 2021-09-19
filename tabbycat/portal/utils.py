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


# Payment webhook methods

def on_payment_success(client, payment):
    from .models import Instance
    client.paid = payment.get('amount', 0)
    client.save()

    # Add domain
    main_instance = Instance.objects.get(tenant__schema_name='public', is_primary=True).domain
    domains = [Instance(tenant=client, domain=client.schema_name + "." + main_instance, is_primary=True)]
    if not client.schema_name.islower():
        domains.append(Instance(tenant=client, domain=client.schema_name.lower() + "." + main_instance, is_primary=False))
    Instance.objects.bulk_create(domains, ignore_conflicts=True)


def on_payment_deny(client, payment):
    client.delete(force_drop=not client.domains.exists())


def get_postgres_url():
    db = settings.DATABASES['default']
    return 'postgres://%s:%s@%s:%s/%s' % (db['USER'], db['PASSWORD'], db['HOST'], db['PORT'], db['NAME'])
