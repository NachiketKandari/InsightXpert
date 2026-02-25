from __future__ import annotations

import json
import logging
from pathlib import Path

from insightxpert.admin.models import ClientConfig, OrgConfig

logger = logging.getLogger("insightxpert.admin")


def read_config(config_path: Path) -> ClientConfig:
    try:
        data = json.loads(config_path.read_text())
        return ClientConfig.model_validate(data)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        logger.warning("Could not read config from %s: %s — using defaults", config_path, e)
        return ClientConfig()


def write_config(config_path: Path, config: ClientConfig) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config.model_dump(), indent=2))
    logger.info("Config written to %s", config_path)


def set_org_config(config_path: Path, org_id: str, org_config: OrgConfig) -> ClientConfig:
    cfg = read_config(config_path)
    cfg.organizations[org_id] = org_config
    write_config(config_path, cfg)
    return cfg


def delete_org_config(config_path: Path, org_id: str) -> ClientConfig:
    cfg = read_config(config_path)
    cfg.organizations.pop(org_id, None)
    write_config(config_path, cfg)
    return cfg
