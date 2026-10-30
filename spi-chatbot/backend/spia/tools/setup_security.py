"""Issuer-side setup utility. Run manually; never expose as an HTTP endpoint.

Build starter access profiles from the current presentation dataset.
Production purchases and SPIA user assignments require explicit provisioning.
The encrypted signing key stays on the issuer workstation, outside this project.
"""

from spia.core.paths import BACKEND_DIR

import argparse
import base64
import getpass
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from spia.security.access_control import Identity
from spia.security.license_policy import CompanyLicense, SIGNING_CONTEXT, UserAccess
from spia.security.store import Installation, load_policy

PROJECT = BACKEND_DIR.parent.parent

BASE_FIELDS = {
    "stock": "item_id warehouse_id quantity_available",
    "sales_orders": (
        "id customer_party_id item_id quantity status order_date"
    ),
    "purchase_orders": (
        "id supplier_party_id item_id quantity status order_date "
        "requested_delivery_date"
    ),
    "credit_return_notes": (
        "id sales_order_id customer_party_id item_id "
        "quantity_returned status date"
    ),
    "payroll": (
        "id employee_id period currency gross deductions net status"
    ),
    "tickets": "id module subject status created_at",
}

MONEY_FIELDS = {
    "sales_orders": "unit_price_pkr total_amount_pkr",
    "purchase_orders": (
        "unit_price_pkr total_amount_pkr requested_by"
    ),
    "credit_return_notes": (
        "credit_amount_pkr reason approved_by"
    ),
}


def build_profiles(data, company, installation):
    profiles = []

    for user in data["users"]:
        rules = []
        role = user["role"]
        modules = set(user["module_licenses"])

        def add(
            feature,
            module,
            kind,
            scope=None,
            values=None,
            actions=("read",),
            pricing=False,
        ):
            fields = BASE_FIELDS.get(
                kind, "text source"
            ).split()

            if pricing:
                fields += MONEY_FIELDS.get(kind, "").split()

            rules.append({
                "feature": feature,
                "module": module,
                "resource_type": kind,
                "actions": list(actions),
                "fields": fields,
                "classifications": [
                    "general_guidance"
                    if kind == "knowledge"
                    else "business"
                ],
                "scopes": (
                    []
                    if scope is None
                    else [{
                        "attribute": scope,
                        "values": values,
                    }]
                ),
                "all_company": scope is None,
            })

        def orders(feature, actions, pricing=False):
            definitions = (
                (
                    "sales",
                    "sales_orders",
                    "customer_party_id",
                ),
                (
                    "purchasing",
                    "purchase_orders",
                    "supplier_party_id",
                ),
                (
                    "sales",
                    "credit_return_notes",
                    "customer_party_id",
                ),
            )

            for module, kind, attribute in definitions:
                if (
                    feature == "bi_expert"
                    and kind == "credit_return_notes"
                ):
                    continue

                if (
                    feature == "document_generator"
                    and kind == "sales_orders"
                ):
                    continue

                if module in modules:
                    add(
                        feature,
                        module,
                        kind,
                        attribute,
                        user["scopes"]["party_ids"],
                        actions,
                        pricing,
                    )

        if role in {"support", "implementation"}:
            feature = role + "_expert"

            if (
                feature not in user["experts"]
                or not modules <= {
                    "financial", "inventory", "payroll"
                }
            ):
                raise ValueError(
                    "Unexpected document-expert profile"
                )

            for module in sorted(modules):
                add(
                    feature,
                    module,
                    "knowledge",
                    actions=("read", "ask"),
                )

                if role == "support":
                    add(
                        feature,
                        module,
                        "tickets",
                        "id",
                        user["scopes"]["ticket_ids"],
                    )

        elif role in {
            "operations",
            "business_partner",
            "bi_internal",
            "document_clerk",
        }:
            if "inventory" in modules:
                add(
                    "business_lookup",
                    "inventory",
                    "stock",
                    "warehouse_id",
                    user["scopes"]["warehouse_ids"],
                )

            orders("business_lookup", ("read",))

            if role == "bi_internal":
                orders(
                    "bi_expert",
                    ("summarize",),
                    pricing=True,
                )

                if "inventory" in modules:
                    add(
                        "bi_expert",
                        "inventory",
                        "stock",
                        "warehouse_id",
                        user["scopes"]["warehouse_ids"],
                        ("summarize",),
                    )

            if role == "document_clerk":
                orders(
                    "document_generator",
                    ("read", "generate"),
                    pricing=True,
                )

        elif role in {"employee", "hr"}:
            if "payroll" not in modules:
                raise ValueError(
                    "Payroll module is required"
                )

            add(
                "business_lookup",
                "payroll",
                "payroll",
                "employee_id",
                user["scopes"]["employee_ids"],
            )

        else:
            raise ValueError(
                f"Unsupported source role: {role}"
            )

        profiles.append(UserAccess(
            user_id=user["id"],
            company_id=company,
            installation_id=installation,
            revision=1,
            enabled=True,
            roles=[role],
            channels=user["surfaces"],
            assigned_pairs=[
                {
                    "feature": rule["feature"],
                    "module": rule["module"],
                }
                for rule in rules
            ],
            rules=rules,
        ))

    additional = (
        (
            "knowledge_reader",
            "project_knowledge_expert",
            "project",
        ),
        (
            "general_user",
            "general_assistant",
            "general",
        ),
        (
            "stock_viewer",
            "business_lookup",
            "inventory",
        ),
    )

    for user_id, feature, module in additional:
        stock = user_id == "stock_viewer"

        profiles.append(UserAccess(
            user_id=user_id,
            company_id=company,
            installation_id=installation,
            revision=1,
            enabled=True,
            roles=[user_id],
            channels=["spia_tsplus", "web", "mobile"],
            assigned_pairs=[{
                "feature": feature,
                "module": module,
            }],
            rules=[{
                "feature": feature,
                "module": module,
                "resource_type": (
                    "stock" if stock else "knowledge"
                ),
                "actions": (
                    ["read"] if stock else ["read", "ask"]
                ),
                "fields": (
                    BASE_FIELDS["stock"].split()
                    if stock
                    else ["text", "source"]
                ),
                "classifications": [
                    "business"
                    if stock
                    else "general_guidance"
                ],
                "scopes": (
                    [{
                        "attribute": "warehouse_id",
                        "values": ["WH-LHR"],
                    }]
                    if stock
                    else []
                ),
                "all_company": not stock,
            }],
        ))

    if len({p.user_id for p in profiles}) != len(profiles):
        raise ValueError("Duplicate user IDs")

    # Original-template display fields
    from spia.services.documents import LABELS
    updated = []
    for profile in profiles:
        raw = profile.model_dump(mode="json")
        if "document_clerk" in raw["roles"]:
            for rule in raw["rules"]:
                if rule["feature"] == "document_generator":
                    extra = LABELS.get(rule["resource_type"], set())
                    rule["fields"] = sorted(set(rule["fields"]) | extra)
        updated.append(UserAccess.model_validate(raw))
    return updated


def signing_key(path, password):
    if len(password) < 16:
        raise ValueError(
            "Use a signing-key password of at least 16 characters"
        )

    if path.exists():
        key = serialization.load_pem_private_key(
            path.read_bytes(),
            password=password,
        )

        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(
                "An Ed25519 signing key is required"
            )

        return key

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()

    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )

    with path.open("xb") as file:
        file.write(pem)

    return key


def prepare(
    dataset,
    output,
    key_path,
    company,
    installation,
    days,
    password,
):
    output = Path(output).resolve()
    key_path = Path(key_path).resolve()

    if output.exists():
        raise ValueError(
            "Security directory already exists; "
            "setup will not overwrite it"
        )

    if not 1 <= days <= 365:
        raise ValueError(
            "Initial license days must be between 1 and 365"
        )

    if (
        output.is_relative_to(PROJECT)
        or key_path.is_relative_to(PROJECT)
    ):
        raise ValueError(
            "Keep security configuration and signing keys "
            "outside this project"
        )

    if key_path.is_relative_to(output):
        raise ValueError(
            "Keep the private signing key outside "
            "the server configuration"
        )

    data = json.loads(
        Path(dataset).read_text(encoding="utf-8")
    )

    profiles = build_profiles(
        data,
        company,
        installation,
    )

    now = datetime.now(timezone.utc)

    term = {
        "revision": 1,
        "status": "active",
        "starts_at": now,
        "expires_at": now + timedelta(days=days),
    }

    pairs = {
        pair
        for profile in profiles
        for pair in profile.assigned_pairs
    }

    purchase = CompanyLicense(
        **term,
        license_id="installation-license",
        company_id=company,
        installation_id=installation,
        channels=["spia_tsplus", "web", "mobile"],
        packages=[
            {
                **term,
                "license_id": "package-" + feature,
                "feature": feature,
            }
            for feature in sorted({
                pair.feature for pair in pairs
            })
        ],
        modules=[
            {
                **term,
                "license_id": "module-" + module,
                "module": module,
            }
            for module in sorted({
                pair.module for pair in pairs
            })
        ],
        licensed_pairs=pairs,
    )

    key = signing_key(key_path, password)
    key_id = "issuer-1"

    payload = purchase.model_dump_json().encode("utf-8")

    signature = key.sign(
        SIGNING_CONTEXT
        + key_id.encode("ascii")
        + b"\x00"
        + payload
    )

    envelope = {
        "key_id": key_id,
        "payload": base64.urlsafe_b64encode(
            payload
        ).decode("ascii"),
        "signature": base64.urlsafe_b64encode(
            signature
        ).decode("ascii"),
    }

    settings = Installation(
        company_id=company,
        installation_id=installation,
        minimum_revision=1,
        public_keys={
            key_id: base64.b64encode(
                key.public_key().public_bytes_raw()
            ).decode("ascii")
        },
    )

    output.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(tempfile.mkdtemp(
        prefix="spia-security-",
        dir=output.parent,
    ))

    try:
        (temporary / "installation.json").write_text(
            settings.model_dump_json(indent=2),
            encoding="utf-8",
        )

        (temporary / "company_license.json").write_text(
            json.dumps(envelope, indent=2),
            encoding="utf-8",
        )

        (temporary / "user_access.json").write_text(
            json.dumps(
                [
                    profile.model_dump(mode="json")
                    for profile in profiles
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        for profile in profiles:
            identity = Identity(
                user_id=profile.user_id,
                company_id=company,
                installation_id=installation,
                channel="spia_tsplus",
                expires_at=now + timedelta(minutes=10),
            )

            load_policy(
                identity,
                directory=temporary,
                now=now,
            )

        if output.exists():
            raise ValueError(
                "Security directory appeared during setup; "
                "nothing overwritten"
            )

        temporary.rename(output)

    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    return len(profiles), purchase.expires_at


def main():
    parser = argparse.ArgumentParser(
        description="Prepare an internal SPIA installation"
    )

    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--issuer-key", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--installation", required=True)
    parser.add_argument("--days", type=int, required=True)

    args = parser.parse_args()

    password = getpass.getpass(
        "Signing-key password (16+ characters): "
    )

    if not Path(args.issuer_key).exists():
        repeated = getpass.getpass(
            "Repeat signing-key password: "
        )

        if password != repeated:
            raise SystemExit(
                "SETUP FAILED: passwords do not match"
            )

    count, expiry = prepare(
        args.dataset,
        args.output,
        args.issuer_key,
        args.company,
        args.installation,
        args.days,
        password.encode("utf-8"),
    )

    print(f"CREATED: {count} user-access profiles")
    print(f"LICENSE EXPIRES: {expiry.isoformat()}")
    print(
        f"SECURITY DIRECTORY: "
        f"{Path(args.output).resolve()}"
    )
    print(
        "PASS: installation security configuration "
        "saved and verified"
    )



def renewal_main():
    """Issuer-only: preview or export a renewal."""
    from spia.security.license_policy import (
        MAX_LICENSE_BYTES, SignedLicense, verify_license,
    )
    from spia.security.access_control import AccessDenied

    parser = argparse.ArgumentParser(
        description="Preview or issue a signed SPIA renewal"
    )
    parser.add_argument("--renew-license", required=True)
    parser.add_argument("--installation-config", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--installation", required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument(
        "--renew-package", action="append", default=[]
    )
    parser.add_argument(
        "--renew-module", action="append", default=[]
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--issuer-key")
    parser.add_argument("--license-output")
    args = parser.parse_args()

    if not 1 <= args.days <= 365:
        parser.error("Additional days must be between 1 and 365")

    if not args.preview and (
        not args.issuer_key or not args.license_output
    ):
        parser.error(
            "Issuing requires --issuer-key and --license-output"
        )

    if args.preview and (
        args.issuer_key or args.license_output
    ):
        parser.error(
            "Preview does not accept a signing key or output path"
        )

    source = Path(args.renew_license).resolve()
    config = Path(args.installation_config).resolve()

    def read_limited(path, limit):
        with path.open("rb") as file:
            raw = file.read(limit + 1)
        if len(raw) > limit:
            raise ValueError(
                "Input exceeds its size limit: " + path.name
            )
        return raw

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    original_license = read_limited(
        source, MAX_LICENSE_BYTES
    )
    settings_raw = read_limited(config, 65536)

    settings = Installation.model_validate(
        json.loads(settings_raw, object_pairs_hook=unique)
    )

    if (
        settings.company_id,
        settings.installation_id,
    ) != (
        args.company,
        args.installation,
    ):
        raise ValueError(
            "Installation does not match the requested "
            "company/installation"
        )

    keys = {
        name: base64.b64decode(value, validate=True)
        for name, value in settings.public_keys.items()
    }

    envelope = SignedLicense.model_validate(
        json.loads(
            original_license,
            object_pairs_hook=unique,
        )
    )
    payload = base64.b64decode(
        envelope.payload,
        altchars=b"-_",
        validate=True,
    )
    candidate = CompanyLicense.model_validate(
        json.loads(payload, object_pairs_hook=unique)
    )

    try:
        # Issuer-side verification at the original start time
        # allows renewal of a genuinely expired license.
        # Runtime request verification is unchanged.
        old = verify_license(
            original_license,
            keys,
            company_id=args.company,
            installation_id=args.installation,
            minimum_revision=settings.minimum_revision,
            now=candidate.starts_at,
        )
    except AccessDenied as exc:
        raise ValueError(
            "Source license rejected: " + exc.code
        ) from None

    now = datetime.now(timezone.utc)

    if old.starts_at > now:
        raise ValueError(
            "A future-starting company license "
            "cannot be renewed here"
        )

    if old.expires_at is None:
        raise ValueError(
            "A perpetual company license "
            "does not need date renewal"
        )

    expiry = max(now, old.expires_at) + timedelta(
        days=args.days
    )

    requested = [
        set(args.renew_package),
        set(args.renew_module),
    ]

    for selected, supplied in zip(
        requested,
        [args.renew_package, args.renew_module],
    ):
        if len(selected) != len(supplied):
            raise ValueError(
                "Duplicate package or module selection"
            )

    updated = old.model_dump(mode="json")
    updated["revision"] = old.revision + 1
    updated["expires_at"] = expiry.isoformat()

    selections = [
        ("packages", "feature", requested[0]),
        ("modules", "module", requested[1]),
    ]

    for collection, attribute, names in selections:
        known = {
            item[attribute]
            for item in updated[collection]
        }

        if names - known:
            raise ValueError(
                "Unknown " + collection + ": "
                + ", ".join(sorted(names - known))
            )

        for item in updated[collection]:
            if item[attribute] not in names:
                continue

            if item["status"] != "active":
                raise ValueError(
                    "Renewal cannot reactivate "
                    "an inactive entitlement"
                )

            start = datetime.fromisoformat(
                item["starts_at"]
            )
            previous = item["expires_at"]

            if start > now or previous is None:
                raise ValueError(
                    "Selected entitlement is "
                    "future-starting or perpetual"
                )

            if datetime.fromisoformat(previous) >= expiry:
                raise ValueError(
                    "Renewal would not extend "
                    "a selected entitlement"
                )

            item["revision"] += 1
            item["expires_at"] = expiry.isoformat()

    renewed = CompanyLicense.model_validate(updated)

    print("COMPANY:", renewed.company_id)
    print("INSTALLATION:", renewed.installation_id)
    print("REVISION:", old.revision, "->", renewed.revision)
    print(
        "COMPANY EXPIRY:",
        old.expires_at.isoformat(),
        "->",
        expiry.isoformat(),
    )

    for collection, attribute, names in [
        (renewed.packages, "feature", requested[0]),
        (renewed.modules, "module", requested[1]),
    ]:
        for item in collection:
            label = getattr(item, attribute)
            print(
                "RENEW" if label in names else "UNCHANGED",
                label,
                item.expires_at,
            )

    if args.preview:
        print(
            "PASS: verified renewal preview; "
            "no files changed"
        )
        return

    key_path = Path(args.issuer_key).resolve()
    destination = Path(args.license_output).resolve()

    if not key_path.is_file():
        raise ValueError(
            "Existing issuer key is required; "
            "no new key will be created"
        )

    if (
        key_path.is_relative_to(PROJECT)
        or destination.is_relative_to(PROJECT)
    ):
        raise ValueError(
            "Keep issuer keys and exported licenses "
            "outside the project"
        )

    if (
        destination.is_relative_to(source.parent)
        or destination.is_relative_to(config.parent)
    ):
        raise ValueError(
            "Export outside the installation "
            "configuration folders"
        )

    if destination == key_path or destination.exists():
        raise ValueError(
            "Output already exists "
            "or targets the issuer key"
        )

    password = getpass.getpass(
        "Existing signing-key password: "
    ).encode("utf-8")

    key = signing_key(key_path, password)

    if (
        key.public_key().public_bytes_raw()
        != keys[envelope.key_id]
    ):
        raise ValueError(
            "Issuer key does not match "
            "this license's trusted key"
        )

    body = renewed.model_dump_json().encode("utf-8")
    result = {
        "key_id": envelope.key_id,
        "payload": base64.urlsafe_b64encode(
            body
        ).decode("ascii"),
        "signature": base64.urlsafe_b64encode(
            key.sign(
                SIGNING_CONTEXT
                + envelope.key_id.encode("ascii")
                + b"\x00"
                + body
            )
        ).decode("ascii"),
    }

    exported = (
        json.dumps(result, indent=2) + "\n"
    ).encode("utf-8")

    try:
        verified = verify_license(
            exported,
            keys,
            company_id=args.company,
            installation_id=args.installation,
            minimum_revision=renewed.revision,
            now=now,
        )
    except AccessDenied as exc:
        raise ValueError(
            "Renewal verification failed: " + exc.code
        ) from None

    if verified != renewed:
        raise ValueError(
            "Renewal differs from the requested result"
        )

    if (
        source.read_bytes() != original_license
        or config.read_bytes() != settings_raw
    ):
        raise ValueError(
            "Source configuration changed; preview again"
        )

    destination.parent.mkdir(
        parents=True, exist_ok=True
    )

    created = False
    try:
        with destination.open("xb") as file:
            created = True
            file.write(exported)
            file.flush()
            import os
            os.fsync(file.fileno())
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise

    print("EXPORTED:", destination)
    print(
        "PASS: signed renewal exported; installed "
        "license and user access unchanged"
    )



def install_license_main():
    """Install a verified renewal using public keys only."""
    import os
    from spia.security.access_control import AccessDenied
    from spia.security.license_policy import (
        MAX_LICENSE_BYTES, SignedLicense, verify_license,
    )
    from spia.security.store import read_configuration

    parser = argparse.ArgumentParser(
        description="Verify and install a signed SPIA renewal"
    )
    parser.add_argument("--install-license", required=True)
    parser.add_argument("--security-dir", required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    root = Path(args.security_dir).resolve()

    if not root.is_dir() or root.is_relative_to(PROJECT):
        raise ValueError(
            "Use the existing private security directory "
            "outside the project"
        )

    license_path = root / "company_license.json"
    settings_path = root / "installation.json"
    incoming = Path(args.install_license).resolve()

    with incoming.open("rb") as file:
        proposed = file.read(MAX_LICENSE_BYTES + 1)

    if len(proposed) > MAX_LICENSE_BYTES:
        raise ValueError("Renewal file exceeds the size limit")

    def inspect():
        before = settings_path.read_bytes()
        settings, keys, _, current = read_configuration(root)

        if settings_path.read_bytes() != before:
            raise ValueError(
                "Installation settings changed; retry"
            )

        try:
            renewed = verify_license(
                proposed,
                keys,
                company_id=settings.company_id,
                installation_id=settings.installation_id,
                minimum_revision=settings.minimum_revision,
            )

            envelope = SignedLicense.model_validate_json(
                current
            )
            payload = base64.b64decode(
                envelope.payload,
                altchars=b"-_",
                validate=True,
            )
            candidate = CompanyLicense.model_validate_json(
                payload
            )

            old = verify_license(
                current,
                keys,
                company_id=settings.company_id,
                installation_id=settings.installation_id,
                minimum_revision=settings.minimum_revision,
                now=candidate.starts_at,
            )

        except AccessDenied as exc:
            raise ValueError(
                "License rejected: " + exc.code
            ) from None

        if renewed.license_id != old.license_id:
            raise ValueError(
                "Renewal belongs to a different license"
            )

        if renewed.revision < old.revision:
            raise ValueError(
                "An older license revision cannot be installed"
            )

        if (
            renewed.revision == old.revision
            and proposed != current
        ):
            raise ValueError(
                "Different licenses cannot share "
                "an installed revision"
            )

        if renewed.revision > old.revision and (
            old.expires_at is None
            or renewed.expires_at is None
            or renewed.expires_at <= old.expires_at
        ):
            raise ValueError(
                "Renewal must extend the company expiry"
            )

        return settings, before, current, renewed

    settings, before, current, renewed = inspect()

    print("COMPANY:", settings.company_id)
    print("INSTALLATION:", settings.installation_id)
    print("NEW EXPIRY:", renewed.expires_at)
    print("LICENSE REVISION:", renewed.revision)

    if args.preview:
        print(
            "PASS: installation preview verified; "
            "no files changed"
        )
        return

    lock = root / ".license-install.lock"

    try:
        lock_file = lock.open("xb")
    except FileExistsError:
        raise ValueError(
            "License installation is locked; "
            "check for another installer"
        ) from None

    try:
        with lock_file:
            settings, before, current, renewed = inspect()

            if (
                proposed == current
                and settings.minimum_revision == renewed.revision
            ):
                print(
                    "PASS: this renewal is already installed"
                )
                return

            next_settings = Installation.model_validate({
                **settings.model_dump(mode="json"),
                "minimum_revision": renewed.revision,
            })

            settings_bytes = (
                next_settings.model_dump_json(indent=2)
                .encode("utf-8")
            )

            stamp = datetime.now(timezone.utc).strftime(
                "%Y%m%d-%H%M%S-%f"
            )
            backup = root / "license_backups" / stamp
            backup.mkdir(parents=True)

            (backup / "company_license.json").write_bytes(
                current
            )
            (backup / "installation.json").write_bytes(
                before
            )

            def replace_bytes(path, raw):
                temporary = None

                try:
                    with tempfile.NamedTemporaryFile(
                        dir=root,
                        prefix="license-stage-",
                        delete=False,
                    ) as file:
                        temporary = Path(file.name)
                        file.write(raw)
                        file.flush()
                        os.fsync(file.fileno())

                    os.replace(temporary, path)

                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)

            if (
                settings_path.read_bytes() != before
                or license_path.read_bytes() != current
            ):
                raise ValueError(
                    "Installed configuration changed; "
                    "nothing replaced"
                )

            # Replace the license first, then raise the
            # minimum accepted revision. Retrying completes
            # an interrupted revision update.
            replace_bytes(license_path, proposed)

            if settings_path.read_bytes() != before:
                raise ValueError(
                    "Settings changed; "
                    "do not restore files manually"
                )

            try:
                replace_bytes(
                    settings_path, settings_bytes
                )
            except OSError:
                raise RuntimeError(
                    "Renewal written but revision update failed. "
                    "Re-run this same command; "
                    "do not issue another renewal."
                ) from None

            installed, _, _, raw = read_configuration(root)

            if (
                raw != proposed
                or installed.minimum_revision != renewed.revision
            ):
                raise RuntimeError(
                    "Final installation verification failed"
                )

            print("BACKUP:", backup)
            print(
                "PASS: signed renewal installed "
                "and revision floor updated"
            )
            print(
                "PASS: user assignments and "
                "document files were not modified"
            )

    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        import sys
        if "--renew-license" in sys.argv:
            renewal_main()
        elif "--install-license" in sys.argv:
            install_license_main()
        else:
            main()
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
    ) as exc:
        raise SystemExit(
            f"SETUP FAILED: {exc}"
        ) from None