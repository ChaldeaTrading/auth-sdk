"""Validate that a release tag matches the package being built."""
import os
from pathlib import Path
import tomllib


def validate_release(version, env):
    tag = env.get("RELEASE_TAG", "")
    if tag != f"auth-sdk-python-v{version}":
        raise ValueError("Release tag must match the package version")
    if env.get("CODEBUILD_BUILD_ID") and env.get("CODEBUILD_SOURCE_VERSION") not in {
        tag, f"refs/tags/{tag}",
    }:
        raise ValueError("CodeBuild source version must be the release tag")


if __name__ == "__main__":
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    version = tomllib.loads(project.read_text())["project"]["version"]
    try:
        validate_release(version, os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
