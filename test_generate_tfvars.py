import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.generate_tfvars import ConfigError, build_tfvars, load_config


def valid_config() -> dict:
    return {
        "environment": "dev",
        "resource_name": "platform-data",
        "owner": "data-platform",
        "tags": {"cost_center": "RND", "criticality": "medium"},
    }


def test_build_tfvars_applies_defaults() -> None:
    result = build_tfvars(valid_config())

    assert result["region"] == "us-west-2"
    assert result["versioning_enabled"] is True
    assert result["encryption_algorithm"] == "AES256"


def test_invalid_environment_is_rejected() -> None:
    config = valid_config()
    config["environment"] = "sandbox"

    with pytest.raises(ConfigError, match="environment"):
        build_tfvars(config)


def test_kms_requires_key() -> None:
    config = valid_config()
    config["encryption_algorithm"] = "aws:kms"

    with pytest.raises(ConfigError, match="kms_key_arn"):
        build_tfvars(config)


def test_invalid_json_reports_helpful_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"environment": ', encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid JSON"):
        load_config(path)


def test_cli_writes_tfvars_json(tmp_path: Path) -> None:
    config_path = tmp_path / "dev.json"
    output_path = tmp_path / "dev.tfvars.json"
    config_path.write_text(json.dumps(valid_config()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_tfvars.py",
            str(config_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    generated = json.loads(output_path.read_text(encoding="utf-8"))
    assert generated["environment"] == "dev"
    assert generated["resource_name"] == "platform-data"


def test_unknown_field_is_rejected() -> None:
    config = valid_config()
    config["typo_field"] = "value"

    with pytest.raises(ConfigError, match="Unsupported field"):
        build_tfvars(config)
