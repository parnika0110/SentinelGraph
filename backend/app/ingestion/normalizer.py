"""Alert/telemetry normalization.

Responsibilities:
* Validate and normalize identifiers, severity, timestamps (done by models).
* Derive STABLE node ids so repeated ingestion upserts instead of duplicating.
* Preserve provenance: source alert id + timestamp travel on every INVOLVES /
  OBSERVED_ON edge as properties.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re

from app.models import AlertIn, ProcessInfo

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(value: str, max_len: int = 80) -> str:
    return _SLUG_RE.sub("_", value.strip().lower()).strip("_")[:max_len]


def normalize_account(value: str) -> str:
    return f"acct:{value.strip().lower()}"


def normalize_device(value: str) -> str:
    return f"dev:{value.strip().lower()}"


def normalize_ip(value: str) -> str:
    """Validate + canonicalize an IP address; raises ValueError if invalid."""
    return f"ip:{ipaddress.ip_address(value.strip())}"


def normalize_service(value: str) -> str:
    return f"svc:{_slug(value)}"


def normalize_process(process: ProcessInfo) -> str:
    if process.sha256:
        return f"proc:{process.sha256.strip().lower()[:16]}"
    return f"proc:{_slug(process.name)}"


def ip_scope(addr: str) -> str:
    """Classify an IP as internal (RFC1918/loopback/link-local/ULA) or external.

    NOTE: `ipaddress` flags documentation ranges (TEST-NET-1/2/3 such as
    203.0.113.0/24) as ``is_private`` since Python 3.13+, but those are NOT
    internal networks in our model -- the demo's attacker IP lives there.
    We therefore classify explicitly by routable private ranges only.
    """
    ip = ipaddress.ip_address(addr)
    if ip.version == 4:
        internal = any(
            ip in ipaddress.ip_network(net)
            for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                        "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8")
        )
    else:
        internal = any(
            ip in ipaddress.ip_network(net)
            for net in ("fc00::/7", "fe80::/10", "::1/128")
        )
    return "internal" if internal else "external"


def alert_entity_ids(alert: AlertIn) -> dict[str, str | None]:
    """Stable entity ids referenced by an alert, keyed by role."""
    return {
        "actor_account": normalize_account(alert.account) if alert.account else None,
        "observed_device": normalize_device(alert.device) if alert.device else None,
        "source_ip": normalize_ip(alert.source_ip) if alert.source_ip else None,
        "process": normalize_process(alert.process) if alert.process else None,
        "service": normalize_service(alert.service) if alert.service else None,
    }


def deterministic_id(*parts: str, prefix: str) -> str:
    """Deterministic id for derived nodes (e.g. login evidence)."""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}"
