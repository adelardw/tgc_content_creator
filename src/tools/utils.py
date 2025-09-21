from urllib.parse import urlparse
import re
import tldextract
import os


def is_url_safe(url):
    parsed = urlparse(url)

    if parsed.scheme not in ['http', 'https']:
        return False

    domain_info = tldextract.extract(parsed.netloc)
    domain = f"{domain_info.domain}.{domain_info.suffix}"


    dangerous_domains = [
        'exe-download.com', 'free-cracks.org',
        'adult-site.com', 'bitcoin-miner.net'
    ]

    if domain in dangerous_domains:
        return False

    suspicious_patterns = [
        r'\.exe$', r'\.zip$', r'\.rar$', r'\.msi$',
        r'\/download\/', r'\/install\/', r'\/crack\/',
        r'\/keygen\/', r'\/torrent\/'
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, url, re.I):
            return False

    return True

