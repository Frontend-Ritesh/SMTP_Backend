import logging
import dns.resolver
from django.conf import settings

logger = logging.getLogger(__name__)

def check_txt_verification(domain_name, expected_token):
    """
    Checks if a TXT record exists on the domain containing the expected verification token.
    Format: mailstack-verification=<token>
    """
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 5
        
        answers = resolver.resolve(domain_name, 'TXT')
        expected_record = f"mailstack-verification={expected_token}"
        
        for rdata in answers:
            # Join strings (DNS handles long TXT values as split arrays of strings)
            txt_content = "".join([part.decode('utf-8') for part in rdata.strings])
            if txt_content.strip() == expected_record:
                return True
    except Exception as e:
        logger.warning(f"TXT verification lookup failed for {domain_name}: {e}")
    return False

def check_mail_configurations(domain_name, dkim_selector="mail"):
    """
    Checks for the existence and correctness of MX, SPF, DKIM, and DMARC records.
    Returns diagnostic details for the tenant.
    """
    status = {
        "mx_valid": False,
        "spf_valid": False,
        "dkim_valid": False,
        "dmarc_valid": False,
        "mx_records": [],
        "spf_record": None,
        "dmarc_record": None,
    }
    
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5
    
    # 1. Verify MX
    try:
        answers = resolver.resolve(domain_name, 'MX')
        # Retrieve system mail server hostname (e.g. mail.example.com)
        mail_host = getattr(settings, 'MAIL_HOSTNAME', '').lower().strip('.')
        for rdata in answers:
            mx_host = str(rdata.exchange).lower().strip('.')
            status["mx_records"].append(f"{rdata.preference} {mx_host}")
            if mail_host and (mx_host == mail_host or mx_host.endswith('.' + mail_host)):
                status["mx_valid"] = True
    except Exception:
        pass
        
    # 2. Verify SPF
    try:
        answers = resolver.resolve(domain_name, 'TXT')
        for rdata in answers:
            txt_content = "".join([part.decode('utf-8') for part in rdata.strings])
            if txt_content.startswith("v=spf1"):
                status["spf_record"] = txt_content
                status["spf_valid"] = True
                break
    except Exception:
        pass
        
    # 3. Verify DKIM
    try:
        dkim_domain = f"{dkim_selector}._domainkey.{domain_name}"
        answers = resolver.resolve(dkim_domain, 'TXT')
        for rdata in answers:
            txt_content = "".join([part.decode('utf-8') for part in rdata.strings])
            if "v=DKIM1" in txt_content:
                status["dkim_valid"] = True
                break
    except Exception:
        pass
        
    # 4. Verify DMARC
    try:
        dmarc_domain = f"_dmarc.{domain_name}"
        answers = resolver.resolve(dmarc_domain, 'TXT')
        for rdata in answers:
            txt_content = "".join([part.decode('utf-8') for part in rdata.strings])
            if txt_content.startswith("v=DMARC1"):
                status["dmarc_record"] = txt_content
                status["dmarc_valid"] = True
                break
    except Exception:
        pass
        
    return status
