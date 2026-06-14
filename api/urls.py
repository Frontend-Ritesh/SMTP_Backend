from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
# Superadmin legacy routes
router.register("admin/domains", views.DomainViewSet, basename="admin-domain")
router.register("admin/mailboxes", views.MailboxViewSet, basename="admin-mailbox")
router.register("admin/aliases", views.AliasViewSet, basename="admin-alias")
router.register("admin/emails", views.AdminEmailViewSet, basename="admin-email")

# Tenant SaaS routes
router.register("tenant/domains", views.TenantDomainViewSet, basename="tenant-domain")
router.register("tenant/mailboxes", views.TenantMailboxViewSet, basename="tenant-mailbox")
router.register("tenant/aliases", views.TenantAliasViewSet, basename="tenant-alias")

urlpatterns = [
    # Auth & Session
    path("csrf/", views.CSRFTokenView.as_view(), name="api-csrf"),
    path("auth/login/", views.LoginView.as_view(), name="api-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="api-logout"),
    path("auth/signup/", views.RegisterView.as_view(), name="api-signup"),
    path("auth/me/", views.MeView.as_view(), name="api-me"),

    # Tenant Dashboard Extra Info
    path("tenant/organization/", views.OrganizationView.as_view(), name="api-tenant-org"),
    path("tenant/domains/<int:pk>/verify/", views.DomainVerificationAPIView.as_view(), name="api-tenant-domain-verify"),

    # Billing integrations
    path("billing/checkout/", views.StripeCheckoutSessionAPIView.as_view(), name="api-billing-checkout"),
    path("billing/webhook/", views.StripeWebhookAPIView.as_view(), name="api-billing-webhook"),

    # Webmail Operations
    path("folders/", views.FolderListView.as_view(), name="api-folders"),
    path("messages/", views.MessageListView.as_view(), name="api-messages"),
    path("messages/<str:folder>/<int:uid>/", views.MessageDetailView.as_view(), name="api-message-detail"),
    path("send/", views.SendView.as_view(), name="api-send"),
    path("search/", views.SearchView.as_view(), name="api-search"),

    # CRUD Router routes
    path("", include(router.urls)),
]
