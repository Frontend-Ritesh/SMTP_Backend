from django.urls import path
from . import views

app_name = 'admin_panel'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Mailbox management
    path('mailboxes/', views.mailbox_list, name='mailbox_list'),
    path('mailboxes/create/', views.mailbox_create, name='mailbox_create'),
    path('mailboxes/<int:pk>/delete/', views.mailbox_delete, name='mailbox_delete'),

    # Domain management
    path('domains/', views.domain_list, name='domain_list'),
    path('domains/<int:pk>/delete/', views.domain_delete, name='domain_delete'),

    # Alias management
    path('aliases/', views.alias_list, name='alias_list'),
    path('aliases/create/', views.alias_create, name='alias_create'),
    path('aliases/<int:pk>/delete/', views.alias_delete, name='alias_delete'),

    # NOTE: Email content browsing is intentionally excluded.
    # Accessing client email content would breach user privacy.
]
