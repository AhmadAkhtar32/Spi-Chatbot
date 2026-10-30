"""Classification checks for published knowledge."""
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from spia.core.paths import BACKEND_DIR
from spia.security.access_control import (
    AccessDenied, Fact, Key, Model, Module,
    Resource, allowed_fields, require_feature,
)
from spia.security.store import (
    SecurityConfigurationError, load_policy,
)
from spia.services.knowledge import (
    approved_sources, get_published,
)


class SourceAccess(Model):
    expert: Literal["implementation", "support"]
    source: Key
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    modules: frozenset[Module] = Field(min_length=1)
    status: Literal["pending_review", "approved", "blocked"]
    classifications: frozenset[Key]
    facts: tuple[Fact, ...] = ()

    @model_validator(mode="after")
    def safe_metadata(self):
        if (
            Path(self.source).name != self.source
            or any(c in self.source for c in "/\\:")
        ):
            raise ValueError("Invalid source name")
        attributes = [fact.attribute for fact in self.facts]
        if (
            len(attributes) != len(set(attributes))
            or {"source", "expert"} & set(attributes)
        ):
            raise ValueError("Invalid source facts")
        if self.status == "approved" and not self.classifications:
            raise ValueError("Approved sources need classifications")
        return self


class Catalogue(Model):
    schema_version: Literal[1]
    company_id: Key
    installation_id: Key
    sources: tuple[SourceAccess, ...]

    @model_validator(mode="after")
    def unique_sources(self):
        names = [(item.expert, item.source) for item in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate source")
        return self


def digest(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def rights(policy):
    return policy.model_dump(
        mode="json",
        exclude={"valid_until"},
    )


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate catalogue key")
        result[key] = value
    return result


def read_catalogue():
    path = Path(os.environ.get('SPIA_KNOWLEDGE_ACCESS_FILE') or BACKEND_DIR / 'data/knowledge_access.json')
    if not path.is_absolute():
        path = BACKEND_DIR / path
    try:
        with path.open('rb') as file:
            raw = file.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Catalogue too large')
        catalogue = Catalogue.model_validate(json.loads(raw, object_pairs_hook=_unique))
        return (catalogue, hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, ValidationError) as exc:
        raise SecurityConfigurationError('Knowledge access catalogue unavailable') from exc


class KnowledgeAccess:
    def __init__(self, context, expert, module):
        self.context = context
        self.expert = expert
        self.module = module
        self.policy = load_policy(context.identity)
        self.feature = expert + "_expert"

        require_feature(
            context.identity,
            self.policy,
            self.feature,
            module,
        )
        if rights(self.policy) != rights(context.policy):
            raise AccessDenied("ACCESS_CHANGED")

        catalogue, self.catalogue_version = read_catalogue()
        if (
            catalogue.company_id,
            catalogue.installation_id,
        ) != (
            context.identity.company_id,
            context.identity.installation_id,
        ):
            raise AccessDenied("KNOWLEDGE_INSTALLATION_MISMATCH")

        self.knowledge = get_published(expert)
        self.approved = approved_sources(expert, module)

        grouped = defaultdict(list)
        for chunk in self.knowledge.chunks:
            grouped[chunk["source"]].append({
                "module": chunk["module"],
                "text": chunk["text"],
            })

        self.sources = set()

        for item in catalogue.sources:
            if (
                item.expert != expert
                or item.status != "approved"
                or item.source not in self.approved
            ):
                continue

            sections = grouped.get(item.source, [])
            if (
                not sections
                or module not in item.modules
                or item.modules != {
                    section["module"] for section in sections
                }
                or item.content_sha256 != digest(sections)
            ):
                continue

            resource = Resource(
                company_id=context.identity.company_id,
                resource_type="knowledge",
                module=module,
                classifications=item.classifications,
                facts=(
                    {"attribute": "source", "value": item.source},
                    {"attribute": "expert", "value": expert},
                    *item.facts,
                ),
            )
            try:
                for action in ("read", "ask"):
                    allowed_fields(
                        context.identity,
                        self.policy,
                        self.feature,
                        action,
                        resource,
                        requested_fields=frozenset({"text", "source"}),
                    )
            except AccessDenied as exc:
                if exc.code in {
                    "DATA_ACCESS_DENIED",
                    "FIELD_ACCESS_DENIED",
                }:
                    continue
                raise

            self.sources.add(item.source)

        if not self.sources:
            raise AccessDenied("KNOWLEDGE_ACCESS_DENIED")

        self.chunks = [
            chunk
            for chunk in self.knowledge.chunks
            if (
                chunk["module"] == module
                and chunk["source"] in self.sources
            )
        ]

    def confirm(self):
        current = KnowledgeAccess(
            self.context,
            self.expert,
            self.module,
        )
        if (
            current.catalogue_version != self.catalogue_version
            or current.knowledge.version != self.knowledge.version
            or current.approved != self.approved
            or current.sources != self.sources
        ):
            raise AccessDenied("KNOWLEDGE_ACCESS_CHANGED")


# Company knowledge uploads
def require_upload_access(context, action):
    if action not in {"read", "upload"}:
        raise ValueError("Unsupported upload operation")

    policy = load_policy(context.identity)
    feature = "project_knowledge_expert"

    require_feature(
        context.identity, policy, feature, "project"
    )

    if rights(policy) != rights(context.policy):
        raise AccessDenied("ACCESS_CHANGED")

    resource = Resource(
        company_id=context.identity.company_id,
        resource_type="knowledge_uploads",
        module="project",
        classifications=["upload_receipt"],
        facts=[{
            "attribute": "owner_id",
            "value": context.identity.user_id,
        }],
    )

    fields = (
        {"text", "source"}
        if action == "upload"
        else {"id", "source", "status"}
    )

    allowed_fields(
        context.identity,
        policy,
        feature,
        action,
        resource,
        requested_fields=frozenset(fields),
    )



# Approved company document access
from functools import lru_cache as _upload_cache
from types import SimpleNamespace
import re as _upload_re

from spia.services.knowledge import KnowledgeUnavailable


@_upload_cache(maxsize=16)
def _indexed_upload(path, token, settings_key, modified, size):
    from spia.services import retrieval as rag

    try:
        if size > 128 * 1024 * 1024:
            raise ValueError("Invalid index size")

        raw = Path(path).read_bytes()
        index = json.loads(raw, object_pairs_hook=_unique)
        source = Path(path).parent.name + ".txt"
        chunks = index["chunks"]

        if (
            index["format"] != "spia-upload-index-v1"
            or index["document_id"] != Path(path).parent.name
            or index["review_token"] != token
            or index["settings"] != json.loads(settings_key)
            or not isinstance(chunks, list)
            or not chunks
            or any(
                not isinstance(chunk, dict)
                or chunk.get("source") != source
                or chunk.get("module") != "project"
                or not isinstance(chunk.get("text"), str)
                or not chunk["text"].strip()
                or not rag._valid_vector(chunk.get("embedding"))
                for chunk in chunks
            )
        ):
            raise ValueError("Invalid upload index")

        return tuple(chunks), hashlib.sha256(raw).hexdigest()

    except (OSError, ValueError, KeyError, TypeError):
        raise KnowledgeUnavailable(
            "Approved upload needs preparation"
        ) from None


class UploadedKnowledgeAccess:
    def __init__(self, context):
        from spia.services.knowledge import (
            _upload_root,
            _reviewed_upload,
        )
        from spia.services import retrieval as rag

        self.context = context
        self.policy = load_policy(context.identity)

        require_feature(
            context.identity,
            self.policy,
            "project_knowledge_expert",
            "project",
        )

        if rights(self.policy) != rights(context.policy):
            raise AccessDenied("ACCESS_CHANGED")

        root = _upload_root()
        self.sources = set()
        self.labels = {}
        chunks = []
        versions = []

        settings = json.dumps(
            rag._cache_settings(),
            sort_keys=True,
        )

        folders = sorted(root.iterdir()) if root.exists() else []

        for folder in folders:
            if _upload_re.fullmatch(
                r"[0-9a-f]{32}", folder.name
            ) is None:
                continue

            try:
                with (folder / "receipt.json").open("rb") as file:
                    raw = file.read(8193)

                if len(raw) > 8192:
                    raise ValueError("Invalid receipt")

                item = json.loads(
                    raw,
                    object_pairs_hook=_unique,
                )

                if (
                    item["company_id"],
                    item["installation_id"],
                ) != (
                    context.identity.company_id,
                    context.identity.installation_id,
                ):
                    continue

                if item["status"] != "approved":
                    continue

                if (
                    item["id"] != folder.name
                    or not item.get("classifications")
                ):
                    raise ValueError(
                        "Invalid approved receipt"
                    )

                source = item["id"] + ".txt"

                resource = Resource(
                    company_id=item["company_id"],
                    resource_type="company_knowledge",
                    module="project",
                    classifications=item["classifications"],
                    facts=[
                        {
                            "attribute": "document_id",
                            "value": item["id"],
                        },
                        {
                            "attribute": "owner_id",
                            "value": item["owner_id"],
                        },
                        {
                            "attribute": "source",
                            "value": source,
                        },
                    ],
                )

                try:
                    for action in ("read", "ask"):
                        allowed_fields(
                            context.identity,
                            self.policy,
                            "project_knowledge_expert",
                            action,
                            resource,
                            requested_fields=frozenset({
                                "text", "source",
                            }),
                        )

                except AccessDenied as exc:
                    if exc.code in {
                        "DATA_ACCESS_DENIED",
                        "FIELD_ACCESS_DENIED",
                    }:
                        continue
                    raise

                _, verified_raw, receipt, _, token = (
                    _reviewed_upload(item["id"])
                )

                if verified_raw != raw:
                    raise AccessDenied(
                        "KNOWLEDGE_ACCESS_CHANGED"
                    )

                index = folder / "index.json"
                stat = index.stat()

                prepared, index_hash = _indexed_upload(
                    str(index),
                    token,
                    settings,
                    stat.st_mtime_ns,
                    stat.st_size,
                )

                chunks.extend(prepared)
                self.sources.add(source)
                self.labels[source] = receipt["source"]

                versions.append([
                    item["id"],
                    token,
                    index_hash,
                ])

            except AccessDenied:
                raise

            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                RecursionError,
            ):
                raise KnowledgeUnavailable(
                    "Approved upload unavailable or changed"
                ) from None

        if not self.sources:
            raise AccessDenied(
                "KNOWLEDGE_ACCESS_DENIED"
            )

        self.catalogue_version = digest(versions)

        self.knowledge = SimpleNamespace(
            version=self.catalogue_version,
            chunks=tuple(chunks),
            suggestions=(),
        )

        self.chunks = chunks

    def confirm(self):
        current = UploadedKnowledgeAccess(self.context)

        if (
            current.catalogue_version != self.catalogue_version
            or current.sources != self.sources
        ):
            raise AccessDenied(
                "KNOWLEDGE_ACCESS_CHANGED"
            )
