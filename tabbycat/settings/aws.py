# Settings relating to the multi-tenant setup using Amazon Web Services

import os


ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '.calicotab.com').split(',')
SECRET_KEY = os.environ.get('DJ_SECRET_KEY')
STATIC_URL = os.getenv('STATIC_URL', '/static/')

BASE_DOMAIN = os.environ.get('BASE_DOMAIN', 'calicotab.com')

# ==============================================================================
# Database
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE'      : 'django_tenants.postgresql_backend',
        'NAME'        : os.environ.get('RDS_DB_NAME'),
        'USER'        : os.environ.get('RDS_USERNAME'),
        'PASSWORD'    : os.environ.get('RDS_PASSWORD'),
        'HOST'        : os.environ.get('RDS_HOSTNAME'),
        'PORT'        : os.environ.get('RDS_PORT'),
        'CONN_MAX_AGE': None,
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

TENANT_LIMIT_SET_CALLS = True

# ==============================================================================
# Django-specific Modules
# ==============================================================================

MIDDLEWARE = [
    'portal.main_middleware.TenantMainMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # User language preferences; must be after Session
    'django.middleware.locale.LocaleMiddleware',
    # Set Etags; i.e. cached requests not on network; must precede Common
    'django.middleware.http.ConditionalGetMiddleware',
    'django.middleware.common.CommonMiddleware',
    # Must be after SessionMiddleware
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'utils.middleware.DebateMiddleware',
    'portal.middleware.TimezoneMiddleware',
]

TABBYCAT_APPS = (
    'actionlog',
    'adjallocation',
    'adjfeedback',
    'api',
    'availability',
    'breakqual',
    'checkins',
    'divisions', # obsolete
    'draw',
    'motions',
    'options',
    'participants',
    'printing',
    'privateurls',
    'results',
    'tournaments',
    'venues',
    'utils',
    'users',
    'standings',
    'notifications',
    'importer',
    'portal',
)

INSTALLED_APPS = (
    'django_tenants',
    'jet',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'channels', # For Websockets / real-time connections (above whitenoise)
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django_summernote',  # Keep above our apps; as we unregister an admin model
    'django.contrib.messages') \
    + TABBYCAT_APPS + (
    'dynamic_preferences',
    'django_extensions',  # For Secret Generation Command
    'gfklookupwidget',
    'formtools',
    'statici18n', # Compile js translations as static file; saving requests
    'polymorphic',
    'rest_framework',
    'rest_framework.authtoken',
    'registration',
)

SHARED_APPS = (
    'django_tenants',  # mandatory
    'portal', # you must list the app where your tenant model resides in
    'jet',
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'channels', # For Websockets / real-time connections (above whitenoise)
    'django_summernote',  # Keep above our apps; as we unregister an admin model
    'django_extensions',  # For Secret Generation Command
    'gfklookupwidget',
    'formtools',
    'statici18n', # Compile js translations as static file; saving requests
    'polymorphic',
    'rest_framework',
    'rest_framework.authtoken',
    'registration',
)

TENANT_APPS = (
    'jet',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions') \
    + TABBYCAT_APPS + (
    'dynamic_preferences',
    'rest_framework.authtoken',
)

TENANT_MODEL = "portal.Client"
TENANT_DOMAIN_MODEL = "portal.Instance"
PUBLIC_SCHEMA_URLCONF = 'portal.urls'
AUTO_DROP_SCHEMA = True
TENANT_COLOR_ADMIN_APPS = False

# ==============================================================================
# Stripe Settings
# ==============================================================================

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISH_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
INSTANCE_PRICE_ID = os.environ.get("STRIPE_INSTANCE_PRICE_ID")
STRIPE_ENDPOINT_SEC = os.environ.get("STRIPE_ENDPOINT_KEY")

# ==============================================================================
# Email
# ==============================================================================

EMAIL_DOMAIN = os.environ.get('EMAIL_FROM_ADDRESS', '').split("@")[-1]
SERVER_EMAIL = os.environ.get('EMAIL_FROM_ADDRESS')
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_FROM_ADDRESS')
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_HOST_USER = os.environ.get('EMAIL_USERNAME')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_PORT = 587
EMAIL_USE_TLS = True

SES_WEBHOOK_KEY = os.environ.get('SES_WEBHOOK_KEY', '')

BACKUPS_S3_BUCKET = os.environ.get('BACKUPS_S3_BUCKET', '')

# ==============================================================================
# Dynamic preferences
# ==============================================================================

DYNAMIC_PREFERENCES = {
    'REGISTRY_MODULE': 'preferences',
    'ENABLE_CACHE': False,
}

# ==============================================================================
# Channels
# ==============================================================================

ASGI_APPLICATION = "routing.application"

if 'REDIS_HOST' in os.environ:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [os.environ.get("REDIS_HOST_URL")],
                "group_expiry": 10800,
            },
        },
    }
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": os.environ.get("REDIS_HOST_URL"),
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True, # Don't crash on say ConnectionError due to limits
                # "CONNECTION_POOL_KWARGS": {"max_connections": 5} # See above
                "SOCKET_CONNECT_TIMEOUT": 5,
                "SOCKET_TIMEOUT": 60,
                'KEY_FUNCTION': 'django_tenants.cache.make_key',
                'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key',
            }
        }
    }
else:
    CACHES = { # Use a dummy cache in development
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
       }
    }

    # Use the cache with database write through for local sessions
    SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
