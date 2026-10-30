"""Read installation security configuration from a private server directory."""

import base64
import json
import os
from pathlib import Path

from pydantic import Field, ValidationError

from spia.security.access_control import AccessDenied, Identity, Key, Model
from spia.security.license_policy import MAX_LICENSE_BYTES, UserAccess, resolve_policy


class SecurityConfigurationError(RuntimeError):
    pass


class Installation(Model):
    company_id: Key
    installation_id: Key
    minimum_revision: int = Field(strict=True, ge=1)
    public_keys: dict[Key, str] = Field(min_length=1)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _read(path, limit):
    try:
        with path.open("rb") as file:
            value = file.read(limit + 1)
        if len(value) > limit:
            raise ValueError("Configuration file is too large")
        return value
    except (OSError, ValueError):
        raise SecurityConfigurationError(
            f"Cannot read security configuration: {path.name}"
        ) from None


def _json(path, limit):
    try:
        return json.loads(
            _read(path, limit).decode("utf-8"),
            object_pairs_hook=_unique,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise SecurityConfigurationError(
            f"Invalid security configuration: {path.name}"
        ) from None


def read_configuration(directory=None):
    """Read trusted server files or a server-only encoded configuration."""
    bundle = None
    encoded = os.environ.get('SPIA_SECURITY_CONFIG_B64') if directory is None else None
    if encoded is not None:
        try:
            if not encoded or len(encoded) > 48000:
                raise ValueError('Configuration exceeds environment limits')
            bundle = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'), object_pairs_hook=_unique)
            expected = {'installation.json', 'company_license.json', 'user_access.json'}
            if not isinstance(bundle, dict) or set(bundle) != expected:
                raise ValueError('Incomplete environment configuration')
            if any((not isinstance(value, str) for value in bundle.values())):
                raise ValueError('Invalid environment configuration values')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise SecurityConfigurationError('Invalid server environment security configuration') from None
        root = None
    else:
        selected = directory if directory is not None else os.environ.get('SPIA_SECURITY_DIR')
        if not selected:
            raise SecurityConfigurationError('SPIA_SECURITY_DIR is not configured')
        root = Path(selected).expanduser()
        if not root.is_absolute():
            raise SecurityConfigurationError('SPIA_SECURITY_DIR must be an absolute path')

    def _config_read(filename, limit):
        if bundle is None:
            return _read(root / filename, limit)
        value = bundle[filename].encode('utf-8')
        if len(value) > limit:
            raise SecurityConfigurationError('Security configuration exceeds limits')
        return value

    def _config_json(filename, limit):
        return json.loads(_config_read(filename, limit).decode('utf-8'), object_pairs_hook=_unique)
    try:
        settings = Installation.model_validate(_config_json('installation.json', 65536))
        public_keys = {key_id: base64.b64decode(value.encode('ascii'), validate=True) for key_id, value in settings.public_keys.items()}
        if any((len(value) != 32 for value in public_keys.values())):
            raise ValueError('Invalid public key length')
        raw_users = _config_json('user_access.json', 4 * 1024 * 1024)
        if not isinstance(raw_users, list):
            raise ValueError('Expected a list of users')
        users = {}
        for raw in raw_users:
            access = UserAccess.model_validate(raw)
            if access.user_id in users:
                raise ValueError('Duplicate user')
            if (access.company_id, access.installation_id) != (settings.company_id, settings.installation_id):
                raise ValueError('User belongs to a different installation')
            users[access.user_id] = access
        license_bytes = _config_read('company_license.json', MAX_LICENSE_BYTES)
        return (settings, public_keys, users, license_bytes)
    except (ValidationError, ValueError, TypeError, UnicodeError):
        raise SecurityConfigurationError('Invalid installation or user-access settings') from None


def load_policy(identity: Identity, *, directory=None, now=None):
    """Reload current files and resolve access for an already verified identity."""
    settings, public_keys, users, license_bytes = read_configuration(
        directory
    )

    if (
        identity.company_id,
        identity.installation_id,
    ) != (
        settings.company_id,
        settings.installation_id,
    ):
        raise AccessDenied("INSTALLATION_IDENTITY_MISMATCH")

    access = users.get(identity.user_id)

    if access is None:
        raise AccessDenied("USER_NOT_CONFIGURED")

    return resolve_policy(
        identity,
        license_bytes,
        public_keys,
        access,
        minimum_revision=settings.minimum_revision,
        now=now,
    )