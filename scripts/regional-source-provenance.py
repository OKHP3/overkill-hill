"""Resolve the reviewed regional source baseline without rewriting its history."""
from __future__ import annotations

import json
import re
from pathlib import Path


BASE_RECORD = "i18n/pilot/source-hashes-murderbird-stills-2026-09-06.json"
HOMEPAGE_UPDATE = "i18n/pilot/regional-homepage-modal-removal.json"


def load_release_shell(root: Path) -> dict:
    base = json.loads((root / BASE_RECORD).read_text(encoding="utf-8"))
    shell = base["current_release_shell"].copy()
    routes = shell["normalized_routes"].copy()
    update = json.loads((root / HOMEPAGE_UPDATE).read_text(encoding="utf-8"))
    if (update.get("base_record") != BASE_RECORD
            or update.get("route") != "/"
            or update.get("previous_normalized_sha256") != routes.get("/")
            or not re.fullmatch(r"[0-9a-f]{64}", update.get("normalized_sha256", ""))):
        raise ValueError("invalid regional homepage source provenance")
    routes["/"] = update["normalized_sha256"]
    shell["normalized_routes"] = routes
    return shell
