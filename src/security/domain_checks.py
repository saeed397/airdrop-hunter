"""Domain age (WHOIS) and basic SSL / legitimacy checks."""
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import whois
import ssl
import socket
from src.utils.logger import log
from src.utils.helpers import extract_domain


class DomainChecker:
    """
    Checks:
    - Domain age (red flag if < 30 days)
    - Basic SSL certificate presence
    """

    def check_domain(self, url_or_domain: str) -> Dict[str, Any]:
        domain = extract_domain(url_or_domain)
        if not domain:
            return {"error": "invalid_domain", "domain_age_days": None}

        result = {
            "domain": domain,
            "domain_age_days": None,
            "creation_date": None,
            "has_ssl": None,
            "registrar": None,
        }

        # WHOIS
        try:
            w = whois.whois(domain)
            creation = w.creation_date
            if isinstance(creation, list):
                creation = creation[0]
            if creation:
                if creation.tzinfo is None:
                    creation = creation.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - creation).days
                result["domain_age_days"] = age_days
                result["creation_date"] = creation.isoformat()
            result["registrar"] = w.registrar
        except Exception as e:
            log.debug(f"[Domain] WHOIS failed for {domain}: {e}")
            result["whois_error"] = str(e)

        # SSL check (simple)
        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=8) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    result["has_ssl"] = True
                    cert = ssock.getpeercert()
                    result["ssl_issuer"] = dict(x[0] for x in cert.get("issuer", []))
        except Exception:
            result["has_ssl"] = False

        return result
