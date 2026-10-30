"""Shared authorization policy; no HTTP routes or authentication shortcuts.

Identity and Policy must be supplied by trusted server adapters after session
and license verification. Never construct them from a browser request body.
This module evaluates access; it does not issue or verify license signatures.
"""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator,
)

Key = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Feature = Literal[
    "support_expert", "implementation_expert", "project_knowledge_expert",
    "bi_expert", "document_generator", "business_lookup", "general_assistant",
]
Module = Literal[
    "financial", "inventory", "payroll", "sales", "purchasing", "project", "general",
]
Channel = Literal["spia_tsplus", "web", "mobile"]
Action = Literal["read", "ask", "summarize", "generate", "upload", "publish", "export"]


class AccessDenied(PermissionError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class Pair(Model):
    feature: Feature
    module: Module


class LicenseTerm(Model):
    license_id: Key
    revision: Annotated[int, Field(strict=True, ge=1)]
    status: Literal["active", "scheduled", "expired", "suspended", "revoked"]
    starts_at: AwareDatetime
    expires_at: AwareDatetime | None
    perpetual: StrictBool = False

    @model_validator(mode="after")
    def valid_dates(self):
        if self.perpetual != (self.expires_at is None):
            raise ValueError("Use an expiry, or explicitly set perpetual=true with no expiry")
        if self.expires_at is not None and self.expires_at <= self.starts_at:
            raise ValueError("License expiry must be after its start")
        return self


class PackageLicense(LicenseTerm):
    feature: Feature


class ModuleLicense(LicenseTerm):
    module: Module


class Identity(Model):
    user_id: Key
    company_id: Key
    installation_id: Key
    channel: Channel
    expires_at: AwareDatetime


class Scope(Model):
    attribute: Key
    values: frozenset[Key] = Field(min_length=1)


class Rule(Pair):
    resource_type: Key
    actions: frozenset[Action] = Field(min_length=1)
    fields: frozenset[Key] = Field(min_length=1)
    classifications: frozenset[Key] = Field(min_length=1)
    scopes: tuple[Scope, ...] = ()
    all_company: StrictBool = False

    @model_validator(mode="after")
    def explicit_scope(self):
        if self.all_company == bool(self.scopes):
            raise ValueError("Provide scopes, or explicitly allow all_company")
        names = [scope.attribute for scope in self.scopes]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate scope attribute")
        return self


class Policy(Model):
    company_id: Key
    installation_id: Key
    user_id: Key
    revision: Annotated[int, Field(strict=True, ge=1)]
    valid_until: AwareDatetime
    enabled: StrictBool
    channels: frozenset[Channel] = Field(min_length=1)
    packages: tuple[PackageLicense, ...] = ()
    modules: tuple[ModuleLicense, ...] = ()
    licensed_pairs: frozenset[Pair] = frozenset()
    assigned_pairs: frozenset[Pair] = frozenset()
    rules: tuple[Rule, ...] = ()

    @model_validator(mode="after")
    def unambiguous_policy(self):
        for names in (
            [item.feature for item in self.packages],
            [item.module for item in self.modules],
        ):
            if len(names) != len(set(names)):
                raise ValueError("Duplicate active entitlement slot")
        if not self.assigned_pairs <= self.licensed_pairs:
            raise ValueError("User assignment exceeds licensed combinations")
        if any(Pair(feature=r.feature, module=r.module) not in self.assigned_pairs
               for r in self.rules):
            raise ValueError("Data rule has no matching user assignment")
        return self


class Fact(Model):
    attribute: Key
    value: Key


class Resource(Model):
    """Server-derived metadata describing the actual record or document section."""
    company_id: Key
    resource_type: Key
    module: Module
    classifications: frozenset[Key] = Field(min_length=1)
    facts: tuple[Fact, ...] = ()

    @model_validator(mode="after")
    def unique_facts(self):
        names = [fact.attribute for fact in self.facts]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate resource attribute")
        return self


def _time(now: datetime | None) -> datetime:
    value = datetime.now(timezone.utc) if now is None else now
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Use a timezone-aware server time")
    return value


def _check_term(term: LicenseTerm | None, layer: str, now: datetime) -> None:
    if term is None:
        raise AccessDenied(f"{layer}_NOT_LICENSED")
    if term.status != "active":
        raise AccessDenied(f"{layer}_INACTIVE")
    if now < term.starts_at:
        raise AccessDenied(f"{layer}_NOT_STARTED")
    if term.expires_at is not None and now >= term.expires_at:
        raise AccessDenied(f"{layer}_EXPIRED")


def require_feature(
    identity: Identity, policy: Policy, feature: Feature, module: Module,
    *, now: datetime | None = None,
) -> None:
    """Check identity binding, freshness, package, module and user assignment."""
    current = _time(now)
    pair = Pair(feature=feature, module=module)
    if identity.expires_at <= current:
        raise AccessDenied("SESSION_EXPIRED")
    if (identity.company_id, identity.installation_id, identity.user_id) != (
        policy.company_id, policy.installation_id, policy.user_id,
    ):
        raise AccessDenied("IDENTITY_MISMATCH")
    if not policy.enabled:
        raise AccessDenied("USER_DISABLED")
    if policy.valid_until <= current:
        raise AccessDenied("POLICY_EXPIRED")
    if identity.channel not in policy.channels:
        raise AccessDenied("CHANNEL_DENIED")
    if feature == "bi_expert" and identity.channel != "spia_tsplus":
        raise AccessDenied("BI_CHANNEL_DENIED")
    if feature == "general_assistant" and module != "general":
        raise AccessDenied("GENERAL_MODULE_DENIED")
    package = next((item for item in policy.packages if item.feature == feature), None)
    _check_term(package, "PACKAGE", current)
    license_module = next((item for item in policy.modules if item.module == module), None)
    _check_term(license_module, "MODULE", current)
    if pair not in policy.licensed_pairs:
        raise AccessDenied("COMBINATION_NOT_LICENSED")
    if pair not in policy.assigned_pairs:
        raise AccessDenied("FEATURE_NOT_ASSIGNED")


def allowed_fields(
    identity: Identity, policy: Policy, feature: Feature, action: Action,
    resource: Resource, *, requested_fields: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> frozenset[str]:
    """Union fields only from rules that independently match this exact resource."""
    require_feature(identity, policy, feature, resource.module, now=now)
    if resource.company_id != identity.company_id:
        raise AccessDenied("RESOURCE_DENIED")
    if feature == "general_assistant" and (
        resource.resource_type != "knowledge"
        or resource.classifications != frozenset({"general_guidance"})
    ):
        raise AccessDenied("GENERAL_DATA_DENIED")
    facts = {fact.attribute: fact.value for fact in resource.facts}
    fields: set[str] = set()
    for rule in policy.rules:
        if (rule.feature != feature or rule.module != resource.module
                or rule.resource_type != resource.resource_type
                or action not in rule.actions
                or not resource.classifications <= rule.classifications):
            continue
        if not rule.all_company and not all(
            facts.get(scope.attribute) in scope.values for scope in rule.scopes
        ):
            continue
        fields.update(rule.fields)
    if not fields:
        raise AccessDenied("DATA_ACCESS_DENIED")
    if not requested_fields <= fields:
        raise AccessDenied("FIELD_ACCESS_DENIED")
    return frozenset(fields)


def project_record(
    identity: Identity, policy: Policy, feature: Feature, action: Action,
    resource: Resource, record: dict, *, requested_fields: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> dict:
    """Return allowed scalar fields only; nested output needs its own schema."""
    fields = allowed_fields(
        identity, policy, feature, action, resource,
        requested_fields=requested_fields, now=now,
    )
    if any(record.get(fact.attribute) != fact.value for fact in resource.facts):
        raise AccessDenied("RESOURCE_METADATA_MISMATCH")
    if "company_id" in record and record["company_id"] != resource.company_id:
        raise AccessDenied("RESOURCE_METADATA_MISMATCH")
    selected = requested_fields or fields
    output = {name: value for name, value in record.items() if name in selected}
    if any(type(value) not in (str, int, float, bool, type(None)) for value in output.values()):
        raise AccessDenied("UNSAFE_NESTED_OUTPUT")
    return output