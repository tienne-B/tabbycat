from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog

from . import views

urlpatterns = [
    # Accounts
    path('accounts/', include([
        path('logout/',
            auth_views.LogoutView.as_view(),
            {'next_page': '/'},  # override to specify next_page
            name='logout'),
        path('create/',
            views.CreateAccountView.as_view(),
            name='create-account'),
        path('',
            include('django.contrib.auth.urls')),
    ])),

    path('',
        views.MainPageView.as_view(),
        name='global-main-page'),

    path('tournaments/', include([
        path('',
            views.ListOwnTournamentsView.as_view(),
            name='own-tournaments-list'),
        path('new/',
            views.CreateInstanceFormView.as_view(),
            name='create-instance'),
        path('new/invoiced/',
            views.InvoicedCreateInstanceFormView.as_view(),
            name='create-instance-invoice'),
        path('<slug:schema>/', include([
            path('',
                views.TournamentDetailView.as_view(),
                name='tournament-detail'),
            path('delete/',
                views.DeleteInstanceView.as_view(),
                name='delete-instance'),
            path('backup/',
                views.BackupInstanceView.as_view(),
                name='backup-instance'),
        ])),
    ])),

    path('registration/', include('registration.urls')),

    path('stripe/', include([
        path('webhook/',
            views.StripeWebhookView.as_view(),
            name='stripe-webhook'),
    ])),

    path('sns/email/<slug:wh_key>/', views.SESWebhookView.as_view(), name='sns-ses-webhook'),

    # Set language override
    path('i18n/',
        include('django.conf.urls.i18n')),

    # JS Translations Catalogue; includes all djangojs files in locale folders
    path('jsi18n/',
         JavaScriptCatalog.as_view(domain="djangojs"),
         name='javascript-catalog'),

    # Summernote (WYSYWIG)
    path('summernote/',
        include('django_summernote.urls')),

    # Admin area
    path('jet/',
        include('jet.urls', 'jet')),
    path('database/',
        admin.site.urls),
]

if settings.DEBUG and settings.ENABLE_DEBUG_TOOLBAR:  # Only serve debug toolbar when on DEBUG
    import debug_toolbar
    urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))
