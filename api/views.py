from django.conf import settings
from django.contrib.auth import login as django_login, logout as django_logout, authenticate, get_user_model
from django.contrib.postgres.search import SearchQuery
from django.db import transaction
from django.http import Http404
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, views, viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny

from mail.imap import list_folders, open_mailbox, ImapUnavailable
from mail.models import MessageMeta
from mail.smtp import build_message, send
from accounts.models import Domain, Mailbox, Alias, Organization, SubscriptionTier
from accounts.dns_verify import check_txt_verification, check_mail_configurations
from .serializers import (
    MessageMetaSerializer,
    SendSerializer,
    DomainSerializer,
    MailboxSerializer,
    AliasSerializer,
    RegisterSerializer,
    OrganizationSerializer
)

User = get_user_model()

# Plan limits configuration
TIER_LIMITS = {
    "free": {"domains": 1, "mailboxes": 5, "quota_mb": 1024},
    "starter": {"domains": 5, "mailboxes": 20, "quota_mb": 5120},
    "pro": {"domains": 9999, "mailboxes": 9999, "quota_mb": 20480},
}


def _get_user_organization(user):
    """Retrieves the primary organization the user belongs to."""
    org = user.organizations.first()
    if not org:
        org = user.owned_organizations.first()
    return org


def _mailbox(request):
    mb = request.user.mailboxes.filter(active=True).first()
    if mb is None:
        # Fallback 1: If username contains '@', look up mailbox by exact address
        if "@" in request.user.username:
            local, dom = request.user.username.rsplit("@", 1)
            mb = Mailbox.objects.filter(local_part=local.lower().strip(), domain__name=dom.lower().strip(), active=True).first()
        
        # Fallback 1.5: If user's email field contains '@', look up mailbox by exact address
        if mb is None and getattr(request.user, "email", None) and "@" in request.user.email:
            local, dom = request.user.email.rsplit("@", 1)
            mb = Mailbox.objects.filter(local_part=local.lower().strip(), domain__name=dom.lower().strip(), active=True).first()
        
        # Fallback 2: Look up mailbox where local_part matches the username (e.g. 'admin' matches 'admin@polynexus.in')
        if mb is None:
            mb = Mailbox.objects.filter(local_part=request.user.username.lower().strip(), active=True).first()
            
    if mb is None:
        raise Http404("No mailbox for this account")
    return mb


class CSRFTokenView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data["username"]
            password = serializer.validated_data["password"]
            org_name = serializer.validated_data["org_name"]

            with transaction.atomic():
                user = User.objects.create_user(username=username, email=username)
                user.set_password(password)
                user.save()

                # Create Tenant Organization
                org = Organization.objects.create(name=org_name, owner=user)
                org.members.add(user)

            django_login(request, user)

            return Response({
                "status": "success",
                "user": {
                    "username": user.username,
                    "is_staff": user.is_staff,
                    "mailbox": None
                },
                "organization": {
                    "id": org.id,
                    "name": org.name,
                    "tier": org.tier
                }
            }, status=status.HTTP_211_CREATED if hasattr(status, 'HTTP_211_CREATED') else 201)
        return Response(serializer.errors, status=400)


class LoginView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "").strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            django_login(request, user)
            mb = user.mailboxes.filter(active=True).first()
            if mb is None:
                try:
                    mb = _mailbox(request)
                except Http404:
                    mb = None
            org = _get_user_organization(user)
            return Response({
                "status": "success",
                "user": {
                    "username": user.username,
                    "is_staff": user.is_staff,
                    "mailbox": mb.address if mb else None
                },
                "organization": {
                    "id": org.id if org else None,
                    "name": org.name if org else None,
                    "tier": org.tier if org else "free"
                }
            })
        return Response({"status": "error", "message": "Invalid credentials"}, status=400)


class LogoutView(views.APIView):
    def post(self, request):
        django_logout(request)
        return Response({"status": "success"})


class MeView(views.APIView):
    def get(self, request):
        user = request.user
        mb = None
        try:
            mb = _mailbox(request)
        except Http404:
            pass
        org = _get_user_organization(user)
        return Response({
            "username": user.username,
            "is_staff": user.is_staff,
            "mailbox": mb.address if mb else None,
            "organization": {
                "id": org.id if org else None,
                "name": org.name if org else None,
                "tier": org.tier if org else "free",
                "limits": TIER_LIMITS[org.tier] if org else TIER_LIMITS["free"]
            }
        })


class OrganizationView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org = _get_user_organization(request.user)
        if not org:
            return Response({"error": "No workspace organization associated with this account"}, status=404)
        serializer = OrganizationSerializer(org)
        limits = TIER_LIMITS[org.tier]
        return Response({
            "organization": serializer.data,
            "limits": limits
        })


class FolderListView(views.APIView):
    def get(self, request):
        try:
            mb = _mailbox(request)
            return Response({"folders": list_folders(mb.address)})
        except ImapUnavailable:
            return Response({"error": "Mail server unreachable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Http404:
            return Response({"folders": []})


class MessageListView(generics.ListAPIView):
    serializer_class = MessageMetaSerializer

    def get_queryset(self):
        try:
            mb = _mailbox(self.request)
        except Http404:
            return MessageMeta.objects.none()
        folder = self.request.query_params.get("folder", "INBOX")
        
        # Sync new mail from Dovecot on inbox load / refresh
        from mail.tasks import index_mailbox
        try:
            index_mailbox.run(None, mb.id, folder)
        except Exception:
            pass
            
        return MessageMeta.objects.filter(mailbox=mb, folder=folder)


class MessageDetailView(views.APIView):
    def get(self, request, folder: str, uid: int):
        mb = _mailbox(request)
        try:
            with open_mailbox(mb.address, folder) as imap:
                msg = next(iter(imap.fetch(f"UID {uid}", mark_seen=True)), None)
        except ImapUnavailable:
            return Response({"error": "Mail server unreachable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if msg is None or int(msg.uid) != uid:
            raise Http404
        
        MessageMeta.objects.filter(mailbox=mb, folder=folder, uid=uid).update(seen=True)
        
        return Response({
            "uid": uid,
            "subject": msg.subject,
            "from": msg.from_,
            "to": msg.to,
            "date": msg.date.isoformat() if msg.date else None,
            "text": msg.text or "(no plain-text part; HTML rendering not enabled)",
            "html": msg.html or "",
            "attachments": [{"filename": a.filename, "size": a.size,
                             "content_type": a.content_type} for a in msg.attachments],
        })

    def delete(self, request, folder: str, uid: int):
        mb = _mailbox(request)
        try:
            with open_mailbox(mb.address, folder) as imap:
                imap.delete([str(uid)])
        except ImapUnavailable:
            return Response({"error": "Mail server unreachable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        MessageMeta.objects.filter(mailbox=mb, folder=folder, uid=uid).delete()
        return Response({"status": "deleted"})


class SendView(views.APIView):
    def post(self, request):
        mb = _mailbox(request)
        
        to_data = request.data.get("to")
        if isinstance(to_data, str):
            to = [a.strip() for a in to_data.split(",") if a.strip()]
        elif isinstance(to_data, list):
            to = to_data
        else:
            to = []
            
        cc_data = request.data.get("cc", "")
        if isinstance(cc_data, str):
            cc = [a.strip() for a in cc_data.split(",") if a.strip()]
        elif isinstance(cc_data, list):
            cc = cc_data
        else:
            cc = []

        subject = request.data.get("subject", "")
        body = request.data.get("body", "")

        if not to:
            return Response({"error": "Recipient required"}, status=400)

        attachments = []
        for f in request.FILES.getlist("attachments"):
            if f.size > settings.MAX_ATTACHMENT_BYTES:
                return Response({"error": f"{f.name} exceeds the attachment size limit."}, status=400)
            attachments.append((f.name, f.read(), f.content_type or "application/octet-stream"))

        msg = build_message(
            from_addr=mb.address,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            attachments=attachments
        )
        send(msg)

        try:
            with open_mailbox(mb.address, "INBOX") as imap:
                if not imap.folder.exists("Sent"):
                    imap.folder.create("Sent")
            with open_mailbox(mb.address, "Sent") as imap:
                imap.append(msg.as_bytes(), "Sent")
            
            from mail.tasks import index_mailbox
            index_mailbox.run(None, mb.id, "Sent")
        except Exception:
            pass

        return Response({"status": "queued", "message_id": msg["Message-ID"]}, status=202)


class SearchView(views.APIView):
    def get(self, request):
        try:
            mb = _mailbox(request)
        except Http404:
            return Response({"results": []})
        q = request.query_params.get("q", "").strip()
        results = MessageMeta.objects.none()
        if q:
            results = MessageMeta.objects.filter(
                mailbox=mb, search_vector=SearchQuery(q)
            )[:100]
        serializer = MessageMetaSerializer(results, many=True)
        return Response({"results": serializer.data})


# --- Tenant Multi-Tenant ViewSets ---
class TenantDomainViewSet(viewsets.ModelViewSet):
    serializer_class = DomainSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org = _get_user_organization(self.request.user)
        if not org:
            return Domain.objects.none()
        return Domain.objects.filter(organization=org).order_by("-created_at")

    def perform_create(self, serializer):
        org = _get_user_organization(self.request.user)
        if not org:
            raise Response({"error": "No workspace workspace associated"}, status=400)

        # Enforce tier limits
        limits = TIER_LIMITS[org.tier]
        if Domain.objects.filter(organization=org).count() >= limits["domains"]:
            raise serializers.ValidationError(f"Domain limit reached ({limits['domains']}) for your current tier.")

        serializer.save(organization=org, active=False)


class TenantMailboxViewSet(viewsets.ModelViewSet):
    serializer_class = MailboxSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org = _get_user_organization(self.request.user)
        if not org:
            return Mailbox.objects.none()
        return Mailbox.objects.filter(domain__organization=org).order_by("-created_at")

    def perform_create(self, serializer):
        org = _get_user_organization(self.request.user)
        domain = serializer.validated_data["domain"]

        # Validate domain belongs to user organization
        if domain.organization != org:
            raise Response({"error": "Domain does not belong to your workspace"}, status=403)

        # Validate domain is verified
        if not domain.is_verified:
            raise Response({"error": "Domain must be verified before creating mailboxes under it"}, status=400)

        # Enforce tier limits
        limits = TIER_LIMITS[org.tier]
        current_mailboxes = Mailbox.objects.filter(domain__organization=org).count()
        if current_mailboxes >= limits["mailboxes"]:
            raise Response({"error": f"Mailbox limit reached ({limits['mailboxes']}) for your current tier."}, status=400)

        # Validate quota
        quota_mb = serializer.validated_data.get("quota_mb", 1024)
        if quota_mb > limits["quota_mb"]:
            raise Response({"error": f"Quota exceeds maximum allowed ({limits['quota_mb']}MB) for your current tier."}, status=400)

        serializer.save()


class TenantAliasViewSet(viewsets.ModelViewSet):
    serializer_class = AliasSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org = _get_user_organization(self.request.user)
        if not org:
            return Alias.objects.none()
        return Alias.objects.filter(domain__organization=org).order_by("domain__name", "source")

    def perform_create(self, serializer):
        org = _get_user_organization(self.request.user)
        domain = serializer.validated_data["domain"]

        # Validate domain belongs to user organization
        if domain.organization != org:
            raise Response({"error": "Domain does not belong to your workspace"}, status=403)

        serializer.save()


class DomainVerificationAPIView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        org = _get_user_organization(request.user)
        try:
            domain = Domain.objects.get(pk=pk, organization=org)
        except Domain.DoesNotExist:
            return Response({"error": "Domain not found"}, status=404)

        # 1. Run ownership TXT record verification
        is_txt_ok = check_txt_verification(domain.name, domain.verification_token)
        if is_txt_ok:
            domain.is_verified = True
            domain.active = True
            domain.save()

        # 2. Run diagnostics check for MX, SPF, DKIM, DMARC
        dns_status = check_mail_configurations(domain.name, domain.dkim_selector)

        return Response({
            "is_verified": domain.is_verified,
            "active": domain.active,
            "dns_diagnostics": dns_status
        })

    def get(self, request, pk):
        org = _get_user_organization(request.user)
        try:
            domain = Domain.objects.get(pk=pk, organization=org)
        except Domain.DoesNotExist:
            return Response({"error": "Domain not found"}, status=404)

        dns_status = check_mail_configurations(domain.name, domain.dkim_selector)
        return Response({
            "is_verified": domain.is_verified,
            "active": domain.active,
            "dns_diagnostics": dns_status
        })


class StripeCheckoutSessionAPIView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tier = request.data.get("tier", "starter")
        if tier not in [SubscriptionTier.STARTER, SubscriptionTier.PRO]:
            return Response({"error": "Invalid tier specified"}, status=400)

        org = _get_user_organization(request.user)
        if not org:
            return Response({"error": "No workspace organization associated"}, status=404)

        # Fallback to Mock Payment if Stripe secrets are not loaded in .env
        stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
        if not stripe_key:
            org.tier = tier
            org.subscription_status = "active"
            org.save()
            return Response({
                "status": "success",
                "mock": True,
                "message": f"Successfully upgraded workspace to {tier.upper()} (Mock billing gateway)",
                "url": "/dashboard"
            })

        # pyrefly: ignore [missing-import]
        import stripe
        stripe.api_key = stripe_key
        try:
            # Simple checkout session skeleton configuration
            checkout_session = stripe.checkout.Session.create(
                line_items=[{
                    # (In production, replace with real product API price IDs)
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': f'MailStack {tier.capitalize()} Plan'},
                        'unit_amount': 900 if tier == 'starter' else 2900,
                        'recurring': {'interval': 'month'},
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=request.build_absolute_uri('/dashboard?payment=success'),
                cancel_url=request.build_absolute_uri('/dashboard?payment=cancel'),
                client_reference_id=str(org.id),
                customer_email=request.user.email
            )
            return Response({"url": checkout_session.url})
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class StripeWebhookAPIView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

        if not endpoint_secret or not sig_header:
            return Response({"error": "Stripe webhook not configured"}, status=400)

        # pyrefly: ignore [missing-import]
        import stripe
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError:
            return Response(status=400)
        except stripe.error.SignatureVerificationError:
            return Response(status=400)

        # Handle successful subscriptions
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            org_id = session.get('client_reference_id')
            customer_id = session.get('customer')
            subscription_id = session.get('subscription')

            if org_id:
                try:
                    org = Organization.objects.get(id=org_id)
                    org.stripe_customer_id = customer_id
                    org.stripe_subscription_id = subscription_id
                    org.subscription_status = "active"
                    # Determine tier based on pricing or parameters (e.g. starter/pro)
                    # For demo purposes, we default to Starter.
                    org.tier = SubscriptionTier.STARTER
                    org.save()
                except Organization.DoesNotExist:
                    pass

        return Response({"status": "received"})


# --- Legacy Global Admin Panels (Restricted to Django Staff) ---
class DomainViewSet(viewsets.ModelViewSet):
    queryset = Domain.objects.all().order_by("-created_at")
    serializer_class = DomainSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]


class MailboxViewSet(viewsets.ModelViewSet):
    queryset = Mailbox.objects.select_related("domain", "user").all().order_by("-created_at")
    serializer_class = MailboxSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]


class AliasViewSet(viewsets.ModelViewSet):
    queryset = Alias.objects.select_related("domain").all().order_by("domain__name", "source")
    serializer_class = AliasSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]


class AdminEmailViewSet(viewsets.ModelViewSet):
    queryset = MessageMeta.objects.select_related("mailbox").all().order_by("-date")
    serializer_class = MessageMetaSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
 