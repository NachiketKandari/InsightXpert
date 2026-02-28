from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from insightxpert.admin.models import (
    ClientConfig,
    DefaultConfig,
    FeatureToggles,
    OrgBranding,
    OrgConfig,
    UserOrgMapping,
)
from insightxpert.auth.models import AppSetting, Organization
from insightxpert.auth.models import User as UserModel

logger = logging.getLogger("insightxpert.admin")

_ADMIN_DOMAINS_KEY = "admin_domains"
_DEFAULT_FEATURES_KEY = "default_features"
_DEFAULT_BRANDING_KEY = "default_branding"


def read_config(engine) -> ClientConfig:
    """Load the full ClientConfig from the database."""
    with Session(engine) as session:
        # Admin domains
        row = session.get(AppSetting, _ADMIN_DOMAINS_KEY)
        admin_domains: list[str] = json.loads(row.value_json) if row else ["insightxpert.ai"]

        # Default feature toggles and branding
        df_row = session.get(AppSetting, _DEFAULT_FEATURES_KEY)
        default_features = (
            FeatureToggles.model_validate(json.loads(df_row.value_json)) if df_row else FeatureToggles()
        )
        db_row = session.get(AppSetting, _DEFAULT_BRANDING_KEY)
        default_branding = (
            OrgBranding.model_validate(json.loads(db_row.value_json)) if db_row else OrgBranding()
        )

        # Organizations
        organizations: dict[str, OrgConfig] = {}
        for org in session.query(Organization).all():
            organizations[org.id] = OrgConfig(
                org_id=org.id,
                org_name=org.name,
                features=FeatureToggles.model_validate(json.loads(org.features_json)),
                branding=OrgBranding.model_validate(json.loads(org.branding_json)),
            )

        # User-org mappings derived from users.org_id FK
        user_org_mappings = [
            UserOrgMapping(email=u.email, org_id=u.org_id)
            for u in session.query(UserModel.email, UserModel.org_id)
            .filter(UserModel.org_id.isnot(None))
            .all()
        ]

        return ClientConfig(
            admin_domains=admin_domains,
            user_org_mappings=user_org_mappings,
            organizations=organizations,
            defaults=DefaultConfig(features=default_features, branding=default_branding),
        )


def _upsert_setting(session: Session, key: str, value) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value_json=json.dumps(value)))
    else:
        row.value_json = json.dumps(value)


def write_config(engine, config: ClientConfig) -> None:
    """Persist global settings (admin_domains, defaults, user-org mappings) to DB."""
    with Session(engine) as session:
        _upsert_setting(session, _ADMIN_DOMAINS_KEY, config.admin_domains)
        _upsert_setting(session, _DEFAULT_FEATURES_KEY, config.defaults.features.model_dump())
        _upsert_setting(session, _DEFAULT_BRANDING_KEY, config.defaults.branding.model_dump())

        # Sync user_org_mappings → users.org_id
        mapped_emails = {m.email.lower() for m in config.user_org_mappings}

        # Clear org_id for users no longer in any mapping
        for user in session.query(UserModel).filter(UserModel.org_id.isnot(None)).all():
            if user.email.lower() not in mapped_emails:
                user.org_id = None

        # Set org_id for mapped users that exist in the DB
        for mapping in config.user_org_mappings:
            user = (
                session.query(UserModel)
                .filter(UserModel.email.ilike(mapping.email))
                .first()
            )
            if user:
                user.org_id = mapping.org_id

        session.commit()
    logger.info("Global config written to database")


def set_org_config(engine, org_id: str, org_config: OrgConfig) -> ClientConfig:
    """Upsert a single org's config and return the refreshed ClientConfig."""
    with Session(engine) as session:
        org = session.get(Organization, org_id)
        if org is None:
            org = Organization(
                id=org_id,
                name=org_config.org_name,
                features_json=json.dumps(org_config.features.model_dump()),
                branding_json=json.dumps(org_config.branding.model_dump()),
            )
            session.add(org)
        else:
            org.name = org_config.org_name
            org.features_json = json.dumps(org_config.features.model_dump())
            org.branding_json = json.dumps(org_config.branding.model_dump())
        session.commit()
    logger.info("Org config upserted: %s", org_id)
    return read_config(engine)


def delete_org_config(engine, org_id: str) -> ClientConfig:
    """Delete an org and clear its users' org_id FK."""
    with Session(engine) as session:
        org = session.get(Organization, org_id)
        if org:
            # Unlink users before deleting to honour the SET NULL FK constraint
            for user in session.query(UserModel).filter(UserModel.org_id == org_id).all():
                user.org_id = None
            session.delete(org)
        session.commit()
    logger.info("Org config deleted: %s", org_id)
    return read_config(engine)


# ---------------------------------------------------------------------------
# One-time migration: seed DB from legacy JSON file
# ---------------------------------------------------------------------------

def migrate_from_json(engine, json_path: Path) -> None:
    """Seed the DB with org config from the legacy JSON file (idempotent).

    Only runs when the ``organizations`` and ``app_settings`` tables are both
    empty, so it is safe to call on every startup.
    """
    with Session(engine) as session:
        has_orgs = session.query(Organization).first() is not None
        has_settings = session.query(AppSetting).first() is not None
        if has_orgs or has_settings:
            logger.debug("Config already in DB — skipping JSON migration")
            return

    if not json_path.exists():
        logger.info("No legacy config file found at %s — starting with defaults", json_path)
        return

    try:
        legacy = ClientConfig.model_validate(json.loads(json_path.read_text()))
    except Exception as exc:
        logger.warning("Could not parse legacy config %s: %s — skipping migration", json_path, exc)
        return

    # Write orgs
    with Session(engine) as session:
        for org in legacy.organizations.values():
            session.add(Organization(
                id=org.org_id,
                name=org.org_name,
                features_json=json.dumps(org.features.model_dump()),
                branding_json=json.dumps(org.branding.model_dump()),
            ))
        session.commit()

    # Write global settings and user-org mappings
    write_config(engine, legacy)
    logger.info(
        "Migrated config from %s: %d orgs, %d user-org mappings",
        json_path,
        len(legacy.organizations),
        len(legacy.user_org_mappings),
    )
