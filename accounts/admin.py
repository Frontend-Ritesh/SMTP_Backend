from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import Alias, AppPassword, Domain, Mailbox, MailboxStatusLog, Organization


# ──────────────────────────────────────────────────────────────────────────────
#  Organization
# ──────────────────────────────────────────────────────────────────────────────
class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0
    fields = ("name", "dkim_selector", "active", "is_verified")
    show_change_link = True


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "domain_count", "mailbox_count", "created_at")
    search_fields = ("name", "owner__username", "owner__email")
    readonly_fields = ("created_at", "domain_count", "mailbox_count")
    inlines = [DomainInline]
    ordering = ("-created_at",)

    fieldsets = (
        ("Organization Details", {
            "fields": ("name", "owner", "members", "description", "created_at"),
        }),
    )
    filter_horizontal = ("members",)

    @admin.display(description="Domains")
    def domain_count(self, obj):
        count = obj.domains.count()
        url = reverse("admin:accounts_domain_changelist") + f"?organization__id__exact={obj.pk}"
        return format_html('<a href="{}">{} domain{}</a>', url, count, "s" if count != 1 else "")

    @admin.display(description="Mailboxes")
    def mailbox_count(self, obj):
        return sum(d.mailbox_set.count() for d in obj.domains.all())


# ──────────────────────────────────────────────────────────────────────────────
#  Domain
# ──────────────────────────────────────────────────────────────────────────────
@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("name", "organization_link", "dkim_selector", "active", "is_verified", "mailbox_count", "created_at")
    list_filter = ("active", "is_verified", "organization")
    search_fields = ("name",)
    readonly_fields = ("verification_token", "created_at")
    ordering = ("-created_at",)

    @admin.display(description="Organization")
    def organization_link(self, obj):
        if obj.organization:
            url = reverse("admin:accounts_organization_change", args=[obj.organization.pk])
            return format_html('<a href="{}">{}</a>', url, obj.organization.name)
        return "—"

    @admin.display(description="Mailboxes")
    def mailbox_count(self, obj):
        count = obj.mailbox_set.count()
        url = reverse("admin:accounts_mailbox_changelist") + f"?domain__id__exact={obj.pk}"
        return format_html('<a href="{}">{}</a>', url, count)


# ──────────────────────────────────────────────────────────────────────────────
#  Mailbox
# ──────────────────────────────────────────────────────────────────────────────
@admin.register(Mailbox)
class MailboxAdmin(admin.ModelAdmin):
    list_display = ("address", "organization_name", "user", "quota_mb", "active", "created_at")
    list_filter = ("domain", "active")
    search_fields = ("local_part", "user__username", "domain__name")
    exclude = ("password_hash",)
    readonly_fields = ("maildir_path", "created_at")
    ordering = ("-created_at",)

    @admin.display(description="Organization")
    def organization_name(self, obj):
        org = obj.domain.organization
        if org:
            url = reverse("admin:accounts_organization_change", args=[org.pk])
            return format_html('<a href="{}">{}</a>', url, org.name)
        return "—"


# ──────────────────────────────────────────────────────────────────────────────
#  Alias
# ──────────────────────────────────────────────────────────────────────────────
@admin.register(Alias)
class AliasAdmin(admin.ModelAdmin):
    list_display = ("__str__", "domain", "active")
    list_filter = ("domain", "active")
    search_fields = ("source", "destination", "domain__name")


# ──────────────────────────────────────────────────────────────────────────────
#  AppPassword
# ──────────────────────────────────────────────────────────────────────────────
@admin.register(AppPassword)
class AppPasswordAdmin(admin.ModelAdmin):
    list_display = ("mailbox", "label", "created_at", "last_used_at")
    exclude = ("password_hash",)
    search_fields = ("mailbox__local_part", "label")


# ──────────────────────────────────────────────────────────────────────────────
#  MailboxStatusLog
# ──────────────────────────────────────────────────────────────────────────────
@admin.register(MailboxStatusLog)
class MailboxStatusLogAdmin(admin.ModelAdmin):
    list_display = ("mailbox_address", "organization", "active", "changed_at")
    list_filter = ("active", "organization")
    search_fields = ("mailbox_address",)
    readonly_fields = ("mailbox_id", "mailbox_address", "organization", "active", "changed_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ──────────────────────────────────────────────────────────────────────────────
#  Admin site customization
# ──────────────────────────────────────────────────────────────────────────────
admin.site.site_header = "MicroMX Administration"
admin.site.site_title = "MicroMX Admin"
admin.site.index_title = "Micronet Solutions — Mail Infrastructure"
