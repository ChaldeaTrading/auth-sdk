"""Verify the installed distribution without importing from the source tree."""

from importlib.metadata import metadata, version
from pathlib import Path
import tomllib

import auth_sdk


distribution = metadata("auth-sdk")
project = Path(__file__).resolve().parents[1] / "pyproject.toml"
expected_version = tomllib.loads(project.read_text())["project"]["version"]

assert version("auth-sdk") == expected_version
assert distribution["License-Expression"] == "Apache-2.0"
assert set(distribution["Requires-Python"].split(",")) == {">=3.11", "<3.13"}
assert auth_sdk.AuthConfig
assert auth_sdk.verify_token
assert auth_sdk.require_user
