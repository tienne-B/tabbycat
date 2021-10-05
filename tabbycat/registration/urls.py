from django.urls import include, path

from . import views


urlpatterns = [
    path('', views.ListManagedObjectsView.as_view(), name='my-reg'),
    path('create/', views.CreateTournamentView.as_view(), name='create-tournament'),
    path('<slug:tournament_slug>/', include([
        path('', views.PublicTournamentIndexView.as_view(), name='tournament-home'),
        path('institutions/<int:pk>/', include([
            path('teams/', views.EditTeamsView.as_view(), name='institution-edit-teams'),
            path('adjudicators/', views.EditAdjudicatorsView.as_view(), name='institution-edit-adjudicators'),
            path('payment/', views.InstitutionPaymentView.as_view(), name='institution-payment'),
        ])),
        path('register/', include([
            path('institution/', views.CreateInstitutionView.as_view(), name='register-institution'),
            path('team/', views.CreateTeamView.as_view(), name='register-team'),
            path('adjudicator/', views.CreateAdjudicatorView.as_view(), name='register-adjudicator'),
        ])),
        path('admin/', include([
            path('preferences/', views.AdminPreferencesView.as_view(), name='admin-preferences'),
            path('registration/', views.AdminRegistrationListView.as_view(), name='admin-registration-list'),
            path('institutions/', include([
                path('', views.AdminInstitutionsListView.as_view(), name='admin-institutions-list'),
                path('<int:pk>/', views.AdminInstitutionDetailView.as_view(), name='admin-institution-detail'),
            ])),
            path('stripe-connect/', views.ConnectStripeAccountView.as_view(), name='stripe-connect-account'),
        ])),
        path('payment/', include([
            path('cancel/', views.CancelPaymentView.as_view(), name='cancel-payment'),
            path('success/', views.SuccessPaymentView.as_view(), name='success-payment'),
            path('t<int:pk>/', views.IndividualPaymentView.as_view(object_type='t'), name='individual-team-payment'),
            path('a<int:pk>/', views.IndividualPaymentView.as_view(object_type='a'), name='individual-adj-payment'),
        ])),
    ])),
]
