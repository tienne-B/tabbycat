"""Tenant middleware

These classes redefine middleware used for websocket authentication so that
users are found in the correct schema. This is necessary for database
operations they are handled asynchronously with connections purged before and
after the query, so the search_path gets reset.
"""

import pytz
from channels.auth import _get_user_session_key, AuthMiddleware
from channels.db import database_sync_to_async
from channels.sessions import CookieMiddleware, SessionMiddleware, SessionMiddlewareInstance
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, load_backend
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django_tenants.utils import schema_context

from .models import Instance


@database_sync_to_async
def get_schema(host):
    with schema_context('public'):
        return Instance.objects.select_related('tenant').get(domain=host).tenant.schema_name


class TenantSchemaMiddleware:
    """Add schema to the scope of the websocket."""

    def __init__(self, inner):
        self.inner = inner

    def __call__(self, scope):
        return TenantSchemaMiddlewareInstance(scope, self)


class TenantSchemaMiddlewareInstance:

    def __init__(self, scope, middleware):
        self.middleware = middleware
        self.scope = dict(scope)
        self.inner = self.middleware.inner

    async def __call__(self, receive, send):
        headers = dict(self.scope.get('headers', []))
        if b"host" in headers:
            self.scope['schema'] = await get_schema(headers[b'host'].decode('ascii').split(":")[0])
        return await self.inner(self.scope)(receive, send)


@database_sync_to_async
def get_user(scope):
    """
    Return the user model instance associated with the given scope.
    If no user is retrieved, return an instance of `AnonymousUser`.
    """

    if "session" not in scope:
        raise ValueError("Cannot find session in scope. You should wrap your consumer in SessionMiddleware.")
    session = scope["session"]
    user = None

    with schema_context(scope['schema']):
        try:
            user_id = _get_user_session_key(session)
            backend_path = session[BACKEND_SESSION_KEY]
        except KeyError:
            pass
        else:
            if backend_path in settings.AUTHENTICATION_BACKENDS:
                backend = load_backend(backend_path)
                user = backend.get_user(user_id)
                # Verify the session
                if hasattr(user, "get_session_auth_hash"):
                    session_hash = session.get(HASH_SESSION_KEY)
                    session_hash_verified = session_hash and constant_time_compare(
                        session_hash, user.get_session_auth_hash(),
                    )
                    if not session_hash_verified:
                        session.flush()
                        user = None
        return user or AnonymousUser()


class TenantSessionMiddleware(SessionMiddleware):

    def __call__(self, scope):
        return TenantSessionMiddlewareInstance(scope, self)


class TenantSessionMiddlewareInstance(SessionMiddlewareInstance):

    async def __call__(self, receive, send):
        """
        We intercept the send() callable so we can do session saves and
        add session cookie overrides to send back.
        """
        # Resolve the session now we can do it in a blocking way
        session_key = self.scope["cookies"].get(self.middleware.cookie_name)
        self.scope["session"]._wrapped = await database_sync_to_async(self.get_session_store())(session_key)
        # Override send
        self.real_send = send
        return await self.inner(receive, self.send)

    def get_session_store(self):
        def _session_store(*args, **kwargs):
            with schema_context(self.scope['schema']):
                return self.middleware.session_store(*args, **kwargs)
        return _session_store


class TenantAuthMiddleware(AuthMiddleware):

    async def resolve_scope(self, scope):
        scope["user"]._wrapped = await get_user(scope)


# Handy shortcut for applying all three at once
AuthMiddlewareStack = lambda inner: TenantSchemaMiddleware(CookieMiddleware(  # noqa: E731
    TenantSessionMiddleware(TenantAuthMiddleware(inner)),
))


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timezone.activate(pytz.timezone(request.tenant.timezone))
        return self.get_response(request)
