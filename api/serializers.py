from rest_framework import serializers
from mail.models import MessageMeta
from accounts.models import Domain, Mailbox, Alias, Organization
from django.contrib.auth import get_user_model

User = get_user_model()

class MessageMetaSerializer(serializers.ModelSerializer):
    mailbox_address = serializers.CharField(source="mailbox.address", read_only=True)

    class Meta:
        model = MessageMeta
        fields = [
            "id", "uid", "folder", "subject", "from_addr", "to_addrs",
            "date", "size", "seen", "flagged", "snippet", "mailbox_address",
            "conversation_id"
        ]


class SendSerializer(serializers.Serializer):
    to = serializers.ListField(child=serializers.EmailField(), min_length=1)
    cc = serializers.ListField(child=serializers.EmailField(), required=False, default=list)
    subject = serializers.CharField(allow_blank=True, default="")
    body = serializers.CharField(allow_blank=True, default="")


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    org_name = serializers.CharField(max_length=255, required=False, default="My Workspace")

    def validate_username(self, value):
        value = value.lower().strip()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value


class OrganizationSerializer(serializers.ModelSerializer):
    domains_count = serializers.IntegerField(source="domains.count", read_only=True)
    mailboxes_count = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id", "name", "owner_username", "stripe_customer_id", "stripe_subscription_id",
            "tier", "subscription_status", "created_at", "domains_count", "mailboxes_count"
        ]
        read_only_fields = ["id", "created_at", "stripe_customer_id", "stripe_subscription_id", "tier", "subscription_status"]

    def get_mailboxes_count(self, obj):
        return Mailbox.objects.filter(domain__organization=obj).count()


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ["id", "name", "dkim_selector", "active", "verification_token", "is_verified", "created_at"]
        read_only_fields = ["id", "verification_token", "is_verified", "created_at"]


class MailboxSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source="domain.name", read_only=True)
    address = serializers.CharField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Mailbox
        fields = ["id", "domain", "domain_name", "local_part", "address", "quota_mb", "active", "password", "created_at"]
        read_only_fields = ["id", "address", "created_at"]

    def create(self, validated_data):
        from accounts.services import dovecot_hash
        
        password = validated_data.pop("password", None)
        local_part = validated_data["local_part"].lower().strip()
        domain = validated_data["domain"]
        address = f"{local_part}@{domain.name}"

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=address, defaults={'email': address}
        )
        if created or password:
            user.set_password(password)
            user.save()

        mailbox = Mailbox.objects.create(
            user=user,
            domain=domain,
            local_part=local_part,
            password_hash=dovecot_hash(password) if password else "",
            quota_mb=validated_data.get("quota_mb", 1024),  # Default to 1GB (1024MB)
            active=validated_data.get("active", True)
        )
        return mailbox


class AliasSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source="domain.name", read_only=True)

    class Meta:
        model = Alias
        fields = ["id", "domain", "domain_name", "source", "destination", "active"]
        read_only_fields = ["id", "domain_name"]
