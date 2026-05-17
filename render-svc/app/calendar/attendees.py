"""Resolve a meeting's attendees → the primary external company we're
personalising the background for. Used by `scheduler.py` to translate a
raw CalendarEvent into a /generate request.

This piece is NOT a stub — it's pure heuristics over already-resolved
data, no external integrations required. The calendar modules supply
attendee email lists; this module decides which company "owns" the
meeting from the AE's perspective.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Personal-email domains we treat as "couldn't determine company" — never
# the right answer for "which company is this meeting with."
GENERIC_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com", "aol.com",
    "proton.me", "protonmail.com", "tutanota.com",
})


@dataclass
class AttendeeResolution:
    primary_domain: str          # "" when no usable external attendee found
    primary_email: str           # the actual email at primary_domain
    external_emails: list[str]
    rationale: str               # human-readable reason — surfaced in logs


@dataclass
class CompanyOnMeeting:
    """One external company present in a meeting. The meeting-render
    orchestrator builds a list of these and creates one welcome layer per
    entry (each in that company's brand color)."""
    domain: str
    representative_email: str    # first attendee at this domain — for any lookup that needs an actual email
    attendee_count: int          # how many attendees from this domain


def _domain_of(email: str) -> str:
    """Lower-case domain part of an email, or "" if not parseable."""
    m = re.match(r"^[^@]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})$", email.strip())
    return m.group(1).lower() if m else ""


def resolve(
    attendees: list[str],
    *,
    organiser_email: str,
    organiser_company_domain: str,
    event_title: str = "",
) -> AttendeeResolution:
    """Pick the primary external company for a meeting.

    Rules, in order:
      1. Exactly one external attendee → use their domain.
      2. Multiple external attendees → use the most-common external domain
         (handles "AE + customer team" meetings).
      3. Zero external attendees → try parsing the event title
         ("Meeting with Acme Corp" → acme.com via a TLD guess). If that
         fails, return empty domain — caller skips personalisation.

    External = not the organiser's company domain, and not a generic
    personal-email domain.
    """
    org_domain = (organiser_company_domain or "").lower()
    externals: list[str] = []
    for email in attendees:
        d = _domain_of(email)
        if not d:
            continue
        if d == org_domain:
            continue
        if d in GENERIC_EMAIL_DOMAINS:
            continue
        externals.append(email)

    external_domains = [_domain_of(e) for e in externals]
    counts = Counter(external_domains)

    if len(set(external_domains)) == 1 and external_domains:
        d = external_domains[0]
        return AttendeeResolution(
            primary_domain=d,
            primary_email=externals[0],
            external_emails=externals,
            rationale=f"single external domain ({d})",
        )

    if counts:
        d, n = counts.most_common(1)[0]
        primary_email = next(e for e in externals if _domain_of(e) == d)
        return AttendeeResolution(
            primary_domain=d,
            primary_email=primary_email,
            external_emails=externals,
            rationale=f"most-common external domain ({d}, {n} attendees)",
        )

    # No external attendees — try the event title.
    title_domain = _guess_domain_from_title(event_title)
    return AttendeeResolution(
        primary_domain=title_domain,
        primary_email="",
        external_emails=[],
        rationale=(
            f"no external attendees; parsed title → {title_domain}"
            if title_domain
            else "no external attendees and title didn't yield a domain"
        ),
    )


def resolve_all(
    attendees: list[str],
    *,
    organiser_email: str,
    organiser_company_domain: str,
) -> list[CompanyOnMeeting]:
    """Return every external company represented in the attendee list,
    sorted by attendee count (most-represented first). Used by the
    meeting-render orchestrator to produce one welcome banner per company
    when there are multiple external companies in the same meeting
    (e.g., a joint customer + partner call).

    Same filtering as `resolve()`: drop the organiser's domain, drop
    generic personal-email providers. Returns [] when no external
    company is found — caller falls back to no welcome layer."""
    org_domain = (organiser_company_domain or "").lower()
    by_domain: dict[str, list[str]] = {}
    for email in attendees:
        d = _domain_of(email)
        if not d or d == org_domain or d in GENERIC_EMAIL_DOMAINS:
            continue
        by_domain.setdefault(d, []).append(email)

    result = [
        CompanyOnMeeting(
            domain=d,
            representative_email=emails[0],
            attendee_count=len(emails),
        )
        for d, emails in by_domain.items()
    ]
    # Highest attendee count first; ties broken alphabetically for
    # reproducibility (matters in tests + when re-rendering the same
    # meeting from two replicas).
    result.sort(key=lambda c: (-c.attendee_count, c.domain))
    return result


# Patterns that show up in salespeople's calendar event titles:
#   "Acme Corp / WiseStamp <> intro"
#   "Meeting with Acme"
#   "Acme x WiseStamp"
_TITLE_PATTERNS = (
    re.compile(r"(?:meeting|sync|intro|chat)\s+(?:with|w/)\s+([A-Z][A-Za-z0-9& -]+)", re.I),
    re.compile(r"^([A-Z][A-Za-z0-9& -]+?)\s*(?:/|<>|x)\s*", re.I),
)


def _guess_domain_from_title(title: str) -> str:
    """Last-resort: extract a company name from the event title and turn
    it into a plausible domain. Lossy — works for clean titles, falls
    over on cryptic ones. Returns "" on failure."""
    if not title:
        return ""
    for pat in _TITLE_PATTERNS:
        m = pat.search(title)
        if not m:
            continue
        name = m.group(1).strip()
        # Normalise: drop spaces, ampersands, lowercase, append .com as a
        # best guess. brand_scraper falls back to logo.dev/favicon, so a
        # wrong TLD often still produces something usable.
        slug = re.sub(r"[^a-z0-9]+", "", name.lower())
        if 2 <= len(slug) <= 30:
            return f"{slug}.com"
    return ""
