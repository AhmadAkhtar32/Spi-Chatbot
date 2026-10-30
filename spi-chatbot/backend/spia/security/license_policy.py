"""Verify company licenses and build a user policy on the server.

Public keys and minimum revisions come from trusted server configuration.
UserAccess comes from the server's access store, never the request body.
Identity must already have been authenticated by the session adapter.
"""

import base64
import binascii
import json
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, ValidationError, model_validator

from spia.security.access_control import (
    AccessDenied, Channel, Identity, Key, LicenseTerm, Model,
    ModuleLicense, PackageLicense, Pair, Policy, Rule,
)

SIGNING_CONTEXT = b"SPIA-LICENSE-V1\x00"
MAX_LICENSE_BYTES = 1024 * 1024


class SignedLicense(Model):
    key_id: Key
    payload: str = Field(min_length=1, max_length=MAX_LICENSE_BYTES)
    signature: str = Field(min_length=1, max_length=128)


class CompanyLicense(LicenseTerm):
    company_id: Key
    installation_id: Key
    channels: frozenset[Channel] = Field(min_length=1)
    packages: tuple[PackageLicense, ...]
    modules: tuple[ModuleLicense, ...]
    licensed_pairs: frozenset[Pair]

    @model_validator(mode="after")
    def valid_combinations(self):
        features = [item.feature for item in self.packages]
        modules = [item.module for item in self.modules]

        if len(features) != len(set(features)) or len(modules) != len(set(modules)):
            raise ValueError("Duplicate entitlement")

        if any(
            p.feature not in features or p.module not in modules
            for p in self.licensed_pairs
        ):
            raise ValueError("Combination references an absent entitlement")

        return self


class UserAccess(Model):
    user_id: Key
    company_id: Key
    installation_id: Key
    revision: int = Field(strict=True, ge=1)
    enabled: bool = Field(strict=True)
    roles: frozenset[Key] = frozenset()
    channels: frozenset[Channel] = Field(min_length=1)
    assigned_pairs: frozenset[Pair] = frozenset()
    rules: tuple[Rule, ...] = ()


def _unique_object(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value

    return result


def _json(raw: bytes):
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
    )


def _decode(value: str) -> bytes:
    raw = value.encode("ascii")
    return base64.b64decode(
        raw,
        altchars=b"-_",
        validate=True,
    )


def _clock(now):
    current = datetime.now(timezone.utc) if now is None else now

    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Use a timezone-aware server time")

    return current


def verify_license(
    raw: bytes,
    public_keys: dict[str, bytes],
    *,
    company_id: str,
    installation_id: str,
    minimum_revision: int,
    now=None,
) -> CompanyLicense:
    """Verify signed bytes, installation binding, status and outer validity."""
    current = _clock(now)

    if type(minimum_revision) is not int or minimum_revision < 1:
        raise ValueError("A trusted minimum license revision is required")

    if not isinstance(raw, bytes) or len(raw) > MAX_LICENSE_BYTES:
        raise AccessDenied("LICENSE_INVALID")

    try:
        envelope = SignedLicense.model_validate(_json(raw))
        key = public_keys.get(envelope.key_id)

        if key is None:
            raise AccessDenied("LICENSE_KEY_UNKNOWN")

        payload = _decode(envelope.payload)
        signature = _decode(envelope.signature)

        message = (
            SIGNING_CONTEXT
            + envelope.key_id.encode("ascii")
            + b"\x00"
            + payload
        )

        Ed25519PublicKey.from_public_bytes(key).verify(
            signature,
            message,
        )

        license = CompanyLicense.model_validate(_json(payload))

    except (
        InvalidSignature,
        ValidationError,
        ValueError,
        TypeError,
        UnicodeError,
        binascii.Error,
        RecursionError,
    ):
        raise AccessDenied("LICENSE_INVALID") from None

    if (
        license.company_id,
        license.installation_id,
    ) != (
        company_id,
        installation_id,
    ):
        raise AccessDenied("LICENSE_INSTALLATION_MISMATCH")

    if license.revision < minimum_revision:
        raise AccessDenied("LICENSE_REVISION_REJECTED")

    if license.status != "active":
        raise AccessDenied("COMPANY_LICENSE_INACTIVE")

    if current < license.starts_at:
        raise AccessDenied("COMPANY_LICENSE_NOT_STARTED")

    if license.expires_at is not None and current >= license.expires_at:
        raise AccessDenied("COMPANY_LICENSE_EXPIRED")

    return license


def resolve_policy(
    identity: Identity,
    raw_license: bytes,
    public_keys: dict[str, bytes],
    access: UserAccess,
    *,
    minimum_revision: int,
    now=None,
) -> Policy:
    """Build a short-lived policy from a signed purchase and server-side grants."""
    current = _clock(now)

    license = verify_license(
        raw_license,
        public_keys,
        company_id=identity.company_id,
        installation_id=identity.installation_id,
        minimum_revision=minimum_revision,
        now=current,
    )

    if (
        access.company_id,
        access.installation_id,
        access.user_id,
    ) != (
        identity.company_id,
        identity.installation_id,
        identity.user_id,
    ):
        raise AccessDenied("USER_ACCESS_MISMATCH")

    if identity.expires_at <= current:
        raise AccessDenied("SESSION_EXPIRED")

    if not access.enabled:
        raise AccessDenied("USER_DISABLED")

    channels = license.channels & access.channels

    if identity.channel not in channels:
        raise AccessDenied("CHANNEL_DENIED")

    deadlines = [
        current + timedelta(minutes=5),
        identity.expires_at,
    ]

    if license.expires_at is not None:
        deadlines.append(license.expires_at)

    try:
        return Policy(
            user_id=identity.user_id,
            company_id=identity.company_id,
            installation_id=identity.installation_id,
            revision=access.revision,
            valid_until=min(deadlines),
            enabled=access.enabled,
            channels=channels,
            packages=license.packages,
            modules=license.modules,
            licensed_pairs=license.licensed_pairs,
            assigned_pairs=access.assigned_pairs,
            rules=access.rules,
        )

    except ValidationError:
        raise AccessDenied("USER_ACCESS_INVALID") from None