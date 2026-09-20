"""Verify the installed distribution without importing from the source tree."""

from importlib.metadata import metadata, version
from pathlib import Path
import tomllib

import auth_sdk


project = Path(__file__).resolve().parents[1] / "pyproject.toml"
project_metadata = tomllib.loads(project.read_text())["project"]
distribution_name = project_metadata["name"]
expected_version = project_metadata["version"]

distribution = metadata(distribution_name)

assert version(distribution_name) == expected_version
assert distribution["License-Expression"] == "Apache-2.0"
assert set(distribution["Requires-Python"].split(",")) == {">=3.11", "<3.13"}
assert auth_sdk.AuthConfig
assert auth_sdk.verify_token
assert auth_sdk.require_user
