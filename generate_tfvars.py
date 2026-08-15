#!/usr/bin/env python3
"""Generate Terraform .tfvars.json input from a validated JSON configuration file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_ENVIRONMENTS = {"dev", "test", "prod"}
RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}[a-z0-9]$")
SUPPORTED_FIELDS = {
    "environment",
    "resource_name",
    "owner",
    "tags",
    "region",
    "versioning_enabled",
    "noncurrent_version_expiration_days",
    "encryption_algorithm",
    "kms_key_arn",
}

DEFAULTS: dict[str, Any] = {
    "region": "us-west-2",
    "versioning_enabled": True,
    "noncurrent_version_expiration_days": 90,
    "encryption_algorithm": "AES256",
}


class ConfigError(ValueError):
    """Raised when the supplied configuration is invalid."""


def load_config(path: Path) -> dict[str, Any]:
    """Load JSON configuration from disk and return it as a dictionary."""
    try:
        with path.open(encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError("Top-level JSON value must be an object.")
    return data


def validate_config(config: dict[str, Any]) -> None:
    """Validate required fields and basic constraints before Terraform sees them."""
    unknown = sorted(set(config) - SUPPORTED_FIELDS)
    if unknown:
        raise ConfigError(f"Unsupported field(s): {', '.join(unknown)}")

    required_fields = ("environment", "resource_name", "owner", "tags")
    missing = [field for field in required_fields if field not in config]
    if missing:
        raise ConfigError(f"Missing required field(s): {', '.join(missing)}")

    environment = config["environment"]
    if environment not in ALLOWED_ENVIRONMENTS:
        raise ConfigError(
            f"environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}; got {environment!r}"
        )

    resource_name = config["resource_name"]
    if not isinstance(resource_name, str) or not RESOURCE_NAME_PATTERN.fullmatch(resource_name):
        raise ConfigError(
            "resource_name must be 3-42 lowercase alphanumeric/hyphen characters "
            "and cannot start or end with a hyphen."
        )

    owner = config["owner"]
    if not isinstance(owner, str) or not owner.strip():
        raise ConfigError("owner must be a non-empty string.")

    tags = config["tags"]
    if not isinstance(tags, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in tags.items()
    ):
        raise ConfigError("tags must be a JSON object containing only string keys and values.")

    versioning = config.get("versioning_enabled", DEFAULTS["versioning_enabled"])
    if not isinstance(versioning, bool):
        raise ConfigError("versioning_enabled must be true or false.")

    region = config.get("region", DEFAULTS["region"])
    if not isinstance(region, str) or not region.strip():
        raise ConfigError("region must be a non-empty string.")

    retention = config.get(
        "noncurrent_version_expiration_days",
        DEFAULTS["noncurrent_version_expiration_days"],
    )
    if not isinstance(retention, int) or isinstance(retention, bool) or retention < 30:
        raise ConfigError("noncurrent_version_expiration_days must be an integer >= 30.")

    encryption = config.get("encryption_algorithm", DEFAULTS["encryption_algorithm"])
    if encryption not in {"AES256", "aws:kms"}:
        raise ConfigError("encryption_algorithm must be either 'AES256' or 'aws:kms'.")
    if encryption == "aws:kms" and not config.get("kms_key_arn"):
        raise ConfigError("kms_key_arn is required when encryption_algorithm is 'aws:kms'.")


def build_tfvars(config: dict[str, Any]) -> dict[str, Any]:
    """Return Terraform variables, applying documented defaults while preserving extensions."""
    result = {**DEFAULTS, **config}
    validate_config(result)
    return result


def write_tfvars(tfvars: dict[str, Any], output_path: Path) -> None:
    """Write deterministic JSON suitable for Terraform's .tfvars.json format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file_handle:
        json.dump(tfvars, file_handle, indent=2, sort_keys=True)
        file_handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate JSON configuration and generate Terraform .tfvars.json input."
    )
    parser.add_argument("config", type=Path, help="Input JSON configuration file")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output path. Defaults to <environment>.tfvars.json in the current directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        tfvars = build_tfvars(config)
        output_path = args.output or Path(f"{tfvars['environment']}.tfvars.json")
        write_tfvars(tfvars, output_path)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: Unable to write output: {exc}", file=sys.stderr)
        return 3

    print(f"Generated Terraform variables: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
