from ipaddress import ip_address

from django.conf import settings
from django_tenants.middleware.main import TenantMainMiddleware as BaseTenantMainMiddleware
from django_tenants.utils import remove_www


class TenantMainMiddleware(BaseTenantMainMiddleware):

    @staticmethod
    def hostname_from_request(request):
        host = remove_www(request.get_host().split(':')[0])
        try:
            # Use all private IPs as a domain, to avoid AWS reporting severe
            if ip_address(host).is_private:
                return settings.BASE_DOMAIN
        except ValueError:
            pass
        return host
