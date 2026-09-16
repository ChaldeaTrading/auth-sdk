"""Validate release identity and private registry settings without logging secrets."""
import argparse
import os
from pathlib import Path
import tomllib
from urllib.parse import urlsplit


def validate_release(version, env, *, tag_only=False):
    tag = env.get("RELEASE_TAG", "")
    if tag != f"auth-sdk-python-v{version}":
        raise ValueError("Release tag must match the package version")
    if env.get("CODEBUILD_BUILD_ID") and env.get("CODEBUILD_SOURCE_VERSION") not in {
        tag, f"refs/tags/{tag}",
    }:
        raise ValueError("CodeBuild source version must be the release tag")
    if tag_only:
        return

    try:
        url = urlsplit(env.get("TWINE_REPOSITORY_URL", ""))
        hostname = (url.hostname or "").lower().rstrip(".")
        if (
            url.scheme != "https" or not hostname or url.username or url.password
            or url.query or url.fragment or url.port == 0
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Configure an HTTPS private registry upload URL without credentials") from None
    if (
        hostname in {"pypi.org", "pypi.python.org", "pythonhosted.org"}
        or hostname.endswith((".pypi.org", ".pythonhosted.org"))
    ):
        raise ValueError("A private Python registry is required")
    if not env.get("TWINE_USERNAME", "").strip() or not env.get("TWINE_PASSWORD", "").strip():
        raise ValueError("Configure Python package credentials through CI secrets")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag-only", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    version = tomllib.loads(project.read_text())["project"]["version"]
    try:
        validate_release(version, os.environ, tag_only=args.tag_only)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
