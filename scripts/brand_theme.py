"""Shared loading and validation for the reviewed browser theme contract."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAND_THEME_CONTRACT_PATH = ROOT / "config" / "brand-theme-contract.json"
BRAND_THEME_REQUIRED_FIELDS = (
    "name",
    "bodyClass",
    "storageKey",
    "light",
    "dark",
    "colorScheme",
)
BRAND_THEME_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
BRAND_THEME_COLOR_SCHEMES = {"dark light", "light dark"}


class _JSONPairs(list[tuple[str, object]]):
    """Preserve JSON object pairs until duplicate keys have been checked."""


def _materialize_json_pairs(value: object, path: tuple[str, ...] = ()) -> object:
    if isinstance(value, _JSONPairs):
        result: dict[str, object] = {}
        for key, child in value:
            if key in result:
                if path == ("brands",):
                    raise ValueError(f"duplicate brand entry {key!r} in brand theme contract")
                if len(path) >= 2 and path[0] == "brands":
                    raise ValueError(
                        f"brand {path[1]!r} has duplicate JSON key {key!r}"
                    )
                location = ".".join(path) if path else "JSON root"
                raise ValueError(
                    f"duplicate JSON key {key!r} in brand theme contract at {location}"
                )
            result[key] = _materialize_json_pairs(child, path + (key,))
        return result
    if isinstance(value, list):
        return [_materialize_json_pairs(item, path) for item in value]
    return value


def validate_brand_theme_contract(raw_contract: object) -> None:
    """Reject malformed brand theme metadata before generation or release."""
    if not isinstance(raw_contract, dict):
        raise ValueError("Brand theme contract must be a JSON object")

    brands = raw_contract.get("brands")
    if not isinstance(brands, dict) or not brands:
        raise ValueError("Brand theme contract must contain a non-empty 'brands' object")

    errors: list[str] = []
    seen_names: dict[str, str] = {}
    seen_body_classes: dict[str, str] = {}
    for brand_id, brand in brands.items():
        label = f"brand {brand_id!r}"
        if not isinstance(brand_id, str) or not brand_id.strip():
            errors.append(f"Brand entry has an invalid identifier: {brand_id!r}")
            if not isinstance(brand, dict):
                errors.append(f"{label} must be a JSON object")
            continue
        if not isinstance(brand, dict):
            errors.append(f"{label} must be a JSON object")
            continue

        missing = [field for field in BRAND_THEME_REQUIRED_FIELDS if field not in brand]
        if missing:
            errors.append(
                f"{label} is missing required field(s): {', '.join(missing)}"
            )

        for field in ("name", "bodyClass", "storageKey", "colorScheme"):
            if field not in brand:
                continue
            value = brand[field]
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{label} has invalid {field!r}; expected a non-empty string"
                )

        for field in ("light", "dark"):
            if field not in brand:
                continue
            value = brand[field]
            if not isinstance(value, str) or not BRAND_THEME_COLOR_RE.fullmatch(value):
                errors.append(
                    f"{label} has invalid {field} color {value!r}; "
                    "expected a six-digit hex color such as '#ffffff'"
                )

        color_scheme = brand.get("colorScheme")
        if isinstance(color_scheme, str) and color_scheme.strip():
            normalized_color_scheme = " ".join(color_scheme.split())
            if normalized_color_scheme not in BRAND_THEME_COLOR_SCHEMES:
                expected = " or ".join(sorted(BRAND_THEME_COLOR_SCHEMES))
                errors.append(
                    f"{label} has invalid 'colorScheme' value "
                    f"{color_scheme!r}; expected {expected!r}"
                )

        name = brand.get("name")
        if isinstance(name, str) and name.strip():
            if name in seen_names:
                errors.append(
                    f"{label} duplicates brand name {name!r} "
                    f"from brand {seen_names[name]!r}"
                )
            else:
                seen_names[name] = brand_id

        body_class = brand.get("bodyClass")
        if isinstance(body_class, str) and body_class.strip():
            if body_class in seen_body_classes:
                errors.append(
                    f"{label} duplicates body class {body_class!r} "
                    f"from brand {seen_body_classes[body_class]!r}"
                )
            else:
                seen_body_classes[body_class] = brand_id

    if errors:
        raise ValueError("\n".join(errors))


def load_brand_theme_contract(
    path: Path = BRAND_THEME_CONTRACT_PATH,
) -> dict[str, dict[str, str]]:
    """Load and validate the reviewed brand metadata contract."""
    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_JSONPairs,
        )
        raw_contract = _materialize_json_pairs(parsed)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read brand theme contract {path}: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Cannot read brand theme contract {path}: {exc}") from exc
    try:
        validate_brand_theme_contract(raw_contract)
    except ValueError as exc:
        raise ValueError(f"Invalid brand theme contract {path}:\n{exc}") from exc
    return raw_contract["brands"]


def render_brand_theme_block(
    brands: dict[str, dict[str, str]],
) -> str:
    """Render the deterministic JavaScript block embedded in app.js."""
    serialized = json.dumps(brands, ensure_ascii=False, indent=2)
    return (
        "// BEGIN GENERATED BRAND THEME CONFIG. Do not edit this block.\n"
        f"const BRAND_THEME_CONFIG = Object.freeze({serialized});\n"
        "// END GENERATED BRAND THEME CONFIG.\n"
    )