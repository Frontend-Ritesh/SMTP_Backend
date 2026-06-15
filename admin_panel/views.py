"""Admin panel views — infrastructure management only.

Privacy policy: platform admins can manage mailboxes, domains, aliases and
organisations but CANNOT access, read or browse any client email content.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages as flash
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect

from accounts.models import Alias, Domain, Mailbox, Organization
from accounts.services import dovecot_hash


# ──────────────────────────────────────────────────────────────────────────────
#  Dashboard
# ──────────────────────────────────────────────────────────────────────────────
@staff_member_required
def dashboard(request):
    """Admin panel landing page — infrastructure stats only, no email content."""
    User = get_user_model()
    ctx = {
        'org_count':        Organization.objects.count(),
        'domain_count':     Domain.objects.count(),
        'mailbox_count':    Mailbox.objects.count(),
        'user_count':       User.objects.count(),
        'recent_orgs':      Organization.objects.select_related('owner').order_by('-created_at')[:5],
        'recent_mailboxes': Mailbox.objects.select_related('domain', 'user').order_by('-created_at')[:5],
    }
    return render(request, 'admin_panel/dashboard.html', ctx)


# ──────────────────────────────────────────────────────────────────────────────
#  Mailbox Management
# ──────────────────────────────────────────────────────────────────────────────
@staff_member_required
def mailbox_list(request):
    qs = Mailbox.objects.select_related('domain', 'user').order_by('-created_at')
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'admin_panel/mailbox_list.html', {'page': page})


@staff_member_required
def mailbox_create(request):
    if request.method == 'POST':
        address  = request.POST.get('address', '').strip()
        password = request.POST.get('password', '').strip()
        quota_mb = int(request.POST.get('quota_mb', 2048))

        if '@' not in address:
            flash.error(request, "Invalid address. It must be in local_part@domain format.")
            return redirect('admin_panel:mailbox_list')

        local, domain_name = address.rsplit('@', 1)
        local       = local.lower().strip()
        domain_name = domain_name.lower().strip()

        if not local or not domain_name:
            flash.error(request, "Username and Domain name cannot be empty.")
            return redirect('admin_panel:mailbox_list')

        try:
            domain, _ = Domain.objects.get_or_create(name=domain_name)
            User = get_user_model()
            user, created = User.objects.get_or_create(
                username=address, defaults={'email': address}
            )
            if created or password:
                user.set_password(password)
                user.save()

            if Mailbox.objects.filter(domain=domain, local_part=local).exists():
                flash.error(request, f"Mailbox {address} already exists.")
                return redirect('admin_panel:mailbox_list')

            Mailbox.objects.create(
                user=user,
                domain=domain,
                local_part=local,
                password_hash=dovecot_hash(password),
                quota_mb=quota_mb,
            )
            flash.success(request, f"Mailbox {address} created successfully and is now live.")
        except Exception as e:
            flash.error(request, f"Error creating mailbox: {str(e)}")

    return redirect('admin_panel:mailbox_list')


@staff_member_required
def mailbox_delete(request, pk):
    mailbox = get_object_or_404(Mailbox, pk=pk)
    address = mailbox.address
    mailbox.delete()
    flash.success(request, f"Mailbox {address} deleted successfully.")
    return redirect('admin_panel:mailbox_list')


# ──────────────────────────────────────────────────────────────────────────────
#  Domain Management
# ──────────────────────────────────────────────────────────────────────────────
@staff_member_required
def domain_list(request):
    if request.method == 'POST':
        name          = request.POST.get('name', '').strip().lower()
        dkim_selector = request.POST.get('dkim_selector', 'mail').strip()
        if name:
            if Domain.objects.filter(name=name).exists():
                flash.error(request, f"Domain {name} already exists.")
            else:
                Domain.objects.create(name=name, dkim_selector=dkim_selector)
                flash.success(request, f"Domain {name} added successfully.")
        return redirect('admin_panel:domain_list')

    qs = Domain.objects.order_by('-created_at')
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'admin_panel/domain_list.html', {'page': page})


@staff_member_required
def domain_delete(request, pk):
    domain = get_object_or_404(Domain, pk=pk)
    name = domain.name
    try:
        domain.delete()
        flash.success(request, f"Domain {name} deleted successfully.")
    except Exception as e:
        flash.error(request, f"Failed to delete domain (might have active mailboxes): {str(e)}")
    return redirect('admin_panel:domain_list')


# ──────────────────────────────────────────────────────────────────────────────
#  Alias Management
# ──────────────────────────────────────────────────────────────────────────────
@staff_member_required
def alias_list(request):
    qs      = Alias.objects.select_related('domain').order_by('domain__name', 'source')
    paginator = Paginator(qs, 50)
    page    = paginator.get_page(request.GET.get('page'))
    domains = Domain.objects.filter(active=True)
    return render(request, 'admin_panel/alias_list.html', {'page': page, 'domains': domains})


@staff_member_required
def alias_create(request):
    if request.method == 'POST':
        domain_id   = request.POST.get('domain')
        source      = request.POST.get('source', '').strip().lower()
        destination = request.POST.get('destination', '').strip()

        domain = get_object_or_404(Domain, pk=domain_id)
        if not destination:
            flash.error(request, "Destination email is required.")
            return redirect('admin_panel:alias_list')

        try:
            Alias.objects.create(domain=domain, source=source, destination=destination)
            flash.success(request, "Alias created successfully.")
        except Exception as e:
            flash.error(request, f"Failed to create alias: {str(e)}")

    return redirect('admin_panel:alias_list')


@staff_member_required
def alias_delete(request, pk):
    alias = get_object_or_404(Alias, pk=pk)
    alias.delete()
    flash.success(request, "Alias deleted successfully.")
    return redirect('admin_panel:alias_list')
