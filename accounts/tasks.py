import logging
from celery import shared_task
from .models import Domain
from .dns_verify import check_txt_verification

logger = logging.getLogger(__name__)

@shared_task
def verify_domain_dns_task(domain_id):
    """
    Verifies a single domain immediately.
    Sets is_verified=True and active=True upon matching the verification token.
    """
    try:
        domain = Domain.objects.get(id=domain_id)
        if domain.is_verified:
            return True
            
        is_txt_ok = check_txt_verification(domain.name, domain.verification_token)
        if is_txt_ok:
            domain.is_verified = True
            domain.active = True
            domain.save()
            logger.info(f"Domain {domain.name} verified successfully.")
            return True
        else:
            logger.info(f"Domain {domain.name} verification failed (TXT token not found).")
    except Domain.DoesNotExist:
        logger.error(f"Domain with ID {domain_id} does not exist.")
    except Exception as e:
        logger.error(f"Error running domain verification task: {e}")
    return False

@shared_task
def verify_all_pending_domains():
    """
    Periodic task to check all unverified domains.
    """
    unverified_domains = Domain.objects.filter(is_verified=False)
    verified_count = 0
    for domain in unverified_domains:
        is_ok = check_txt_verification(domain.name, domain.verification_token)
        if is_ok:
            domain.is_verified = True
            domain.active = True
            domain.save()
            verified_count += 1
            logger.info(f"Domain {domain.name} verified by periodic scanner.")
    return f"Scanned {len(unverified_domains)} domains, verified {verified_count}."
