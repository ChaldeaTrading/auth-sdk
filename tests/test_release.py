import pytest

from scripts.validate_release import validate_release


@pytest.fixture
def release_env():
    return {"RELEASE_TAG": "auth-sdk-python-v0.1.0"}


def test_valid_release_identity(release_env):
    validate_release("0.1.0", release_env)


def test_release_tag_must_match_version(release_env):
    release_env["RELEASE_TAG"] = "auth-sdk-python-v0.2.0"
    with pytest.raises(ValueError, match="tag must match"):
        validate_release("0.1.0", release_env)


def test_missing_release_tag_is_rejected(release_env):
    release_env.pop("RELEASE_TAG")
    with pytest.raises(ValueError):
        validate_release("0.1.0", release_env)


def test_codebuild_release_must_build_its_tag(release_env):
    release_env.update(CODEBUILD_BUILD_ID="sdk:test", CODEBUILD_SOURCE_VERSION="main")
    with pytest.raises(ValueError, match="source version"):
        validate_release("0.1.0", release_env)


@pytest.mark.parametrize("source_version", ["auth-sdk-python-v0.1.0", "refs/tags/auth-sdk-python-v0.1.0"])
def test_codebuild_tag_source_is_accepted(source_version, release_env):
    release_env.update(CODEBUILD_BUILD_ID="sdk:test", CODEBUILD_SOURCE_VERSION=source_version)
    validate_release("0.1.0", release_env)
