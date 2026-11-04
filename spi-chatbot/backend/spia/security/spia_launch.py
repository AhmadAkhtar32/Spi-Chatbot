"""Backend boundary for a future SPIA desktop launch."""
from datetime import datetime, timezone
from typing import Protocol

from pydantic import ValidationError

from spia.security.access_control import AccessDenied, Identity


class SPIALaunchVerifier(Protocol):
    def verify_and_consume(self, credential: str) -> Identity:
        """Verify with SPIA and prevent reuse before returning its identity."""
        ...


def resolve_spia_launch(
    credential: str,
    *,
    verifier: SPIALaunchVerifier,
    company_id: str,
    installation_id: str,
) -> Identity:
    """Bind a verified launch to this server's installation."""
    if not isinstance(credential, str) or not credential.strip():
        raise AccessDenied("SPIA_LAUNCH_INVALID")

    try:
        identity = Identity.model_validate(
            verifier.verify_and_consume(credential)
        )
    except ValidationError:
        raise AccessDenied("SPIA_LAUNCH_INVALID") from None

    if identity.channel != "spia_tsplus":
        raise AccessDenied("SPIA_LAUNCH_CHANNEL_INVALID")
    if (identity.company_id, identity.installation_id) != (
        company_id, installation_id
    ):
        raise AccessDenied("SPIA_LAUNCH_INSTALLATION_MISMATCH")
    if identity.expires_at <= datetime.now(timezone.utc):
        raise AccessDenied("SPIA_LAUNCH_EXPIRED")
    return identity