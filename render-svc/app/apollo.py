"""Apollo People-Match enrichment.

Adapted from Automated_Email_Signatures/apollo.py. The email signatures
pipeline keys lookups by email (which it always has from the CSV input);
this service typically only has name + domain, so we look up by
(first_name, last_name, domain) and fall back to a synthetic
`first_last@domain` key for caching.

Returns an empty `ApolloEnrichment` on any failure — APOLLO_API_KEY unset,
HTTP error, no Apollo match, malformed JSON. Callers are expected to fall
through to homepage scraping when the enrichment yields no usable org data.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import requests

API_URL = "https://api.apollo.io/v1/people/match"
HTTP_TIMEOUT = 20
DEFAULT_CACHE_PATH = Path(__file__).parent / ".apollo_cache.json"

log = logging.getLogger(__name__)


@dataclass
class ApolloEnrichment:
    """One Apollo /people/match call's payload, flattened.

    Apollo returns the matched person AND their organization in a single
    response — capturing the org block lets us bypass homepage scraping for
    company name, logo, and socials in the ~70% of cases where Apollo has
    a clean org record."""
    # Person fields
    contact_id: str = ""
    email: str = ""
    photo_url: str = ""
    linkedin_url: str = ""
    title: str = ""
    headline: str = ""
    # Organization fields (canonical sources for brand metadata)
    company_name: str = ""
    org_logo_url: str = ""
    org_website_url: str = ""
    org_linkedin_url: str = ""
    org_twitter_url: str = ""
    org_facebook_url: str = ""

    def found_person(self) -> bool:
        """True if Apollo matched a real person (has at least one identifier)."""
        return bool(self.contact_id or self.email or self.photo_url or self.linkedin_url)

    def found_org(self) -> bool:
        """True if Apollo's org block has anything we can use for brand assets."""
        return bool(self.company_name or self.org_logo_url or self.org_website_url)

    @classmethod
    def from_cache_dict(cls, d: dict) -> "ApolloEnrichment":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})


# LinkedIn serves real user photos from `media.licdn.com/dms/image/...` and
# its generic default-avatar placeholders from `static.licdn.com/aero-v1/...`.
# Apollo returns whichever LinkedIn shows on the profile page, so we reject
# the placeholders — a gray silhouette in a Zoom background is worse than
# the photo field simply being empty (we'd then either show no photo or
# fall through to Gravatar).
_PLACEHOLDER_PHOTO_HOSTS = ("static.licdn.com",)


def _is_placeholder_photo(url: str) -> bool:
    return any(host in url for host in _PLACEHOLDER_PHOTO_HOSTS)


def _normalise(data: dict) -> ApolloEnrichment:
    person = data.get("person") or {}
    org = person.get("organization") or {}
    photo_url = (person.get("photo_url") or "").strip()
    if photo_url and _is_placeholder_photo(photo_url):
        photo_url = ""
    return ApolloEnrichment(
        contact_id=(person.get("id") or "").strip(),
        email=(person.get("email") or "").strip(),
        photo_url=photo_url,
        linkedin_url=(person.get("linkedin_url") or "").strip(),
        title=(person.get("title") or "").strip(),
        headline=(person.get("headline") or "").strip(),
        company_name=(org.get("name") or "").strip(),
        org_logo_url=(org.get("logo_url") or "").strip(),
        org_website_url=(org.get("website_url") or "").strip(),
        org_linkedin_url=(org.get("linkedin_url") or "").strip(),
        org_twitter_url=(org.get("twitter_url") or "").strip(),
        org_facebook_url=(org.get("facebook_url") or "").strip(),
    )


def _read_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def enrich(
    first_name: str,
    last_name: str,
    domain: str,
    *,
    email: str = "",
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> ApolloEnrichment:
    """Look up a person via Apollo /people/match.

    Cache key: `email` when present, otherwise the synthetic
    `first_last@domain`. Both hits and misses are cached so re-runs don't
    burn credits on prospects Apollo has no record of. Delete the cache
    file (`.apollo_cache.json`) to force re-fetch."""
    api_key = os.environ.get("APOLLO_API_KEY", "").strip()
    if not api_key:
        log.info("APOLLO_API_KEY not set — skipping Apollo enrichment")
        return ApolloEnrichment()
    if not (first_name or last_name or email):
        return ApolloEnrichment()

    cache_key = (
        email.strip().lower()
        or f"{first_name}_{last_name}@{domain}".lower()
    )
    cache = _read_cache(cache_path)
    if cache_key in cache:
        log.debug("apollo cache hit: %s", cache_key)
        return ApolloEnrichment.from_cache_dict(cache[cache_key])

    payload = {k: v for k, v in {
        "first_name": first_name or None,
        "last_name": last_name or None,
        "domain": domain or None,
        "email": email or None,
    }.items() if v}
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    }

    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        log.warning("apollo: lookup failed for %s %s @ %s: %s",
                    first_name, last_name, domain, e)
        cache[cache_key] = asdict(ApolloEnrichment())  # cache the miss
        _write_cache(cache_path, cache)
        return ApolloEnrichment()
    except ValueError as e:
        log.warning("apollo: malformed JSON for %s %s @ %s: %s",
                    first_name, last_name, domain, e)
        return ApolloEnrichment()

    result = _normalise(data)
    cache[cache_key] = asdict(result)
    _write_cache(cache_path, cache)
    return result
