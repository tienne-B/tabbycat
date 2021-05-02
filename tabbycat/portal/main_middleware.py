from ipaddress import ip_address

from django.conf import settings
from django_tenants.middleware.main import TenantMainMiddleware as BaseTenantMainMiddleware


class TenantMainMiddleware(BaseTenantMainMiddleware):

    @staticmethod
    def hostname_from_request(request):
        host = super().hostname_from_request(request)
        try:
            # Use all private IPs as a domain, to avoid AWS reporting severe
            if ip_address(host).is_private:
                return settings.BASE_DOMAIN
            return host
        except ValueError:
            return host
