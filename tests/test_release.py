import pytest

from scripts.validate_release import validate_release


@pytest.fixture
def release_env():
    return {
        "RELEASE_TAG": "auth-sdk-python-v0.1.0",
        "TWINE_REPOSITORY_URL": "https://packages.example.com/repository/python/",
        "TWINE_USERNAME": "publisher",
        "TWINE_PASSWORD": "private-secret",
    }


def test_valid_private_release(release_env):
    validate_release("0.1.0", release_env)


def test_release_tag_must_match_version(release_env):
    release_env["RELEASE_TAG"] = "auth-sdk-python-v0.2.0"
    with pytest.raises(ValueError, match="tag must match"):
        validate_release("0.1.0", release_env)


@pytest.mark.parametrize("key", ["RELEASE_TAG", "TWINE_REPOSITORY_URL", "TWINE_USERNAME", "TWINE_PASSWORD"])
def test_missing_release_configuration_is_rejected(key, release_env):
    release_env.pop(key)
    with pytest.raises(ValueError):
        validate_release("0.1.0", release_env)


@pytest.mark.parametrize("url", [
    "https://upload.pypi.org/legacy/", "https://test.pypi.org/legacy/",
    "https://pypi.org/simple/", "https://UPLOAD.PYPI.ORG./legacy/",
    "https://pypi.python.org/pypi", "http://private.example.com/upload/",
    "https://publisher:private-secret@private.example.com/upload/",
    "https://private.example.com/upload/?token=private-secret",
])
def test_unsafe_upload_url_is_rejected_without_echoing_secrets(url, release_env):
    release_env["TWINE_REPOSITORY_URL"] = url
    with pytest.raises(ValueError) as caught:
        validate_release("0.1.0", release_env)
    assert "private-secret" not in str(caught.value)


def test_tag_only_validation_does_not_require_registry():
    validate_release("0.1.0", {"RELEASE_TAG": "auth-sdk-python-v0.1.0"}, tag_only=True)


def test_codebuild_release_must_build_its_tag(release_env):
    release_env.update(CODEBUILD_BUILD_ID="sdk:test", CODEBUILD_SOURCE_VERSION="main")
    with pytest.raises(ValueError, match="source version"):
        validate_release("0.1.0", release_env)


@pytest.mark.parametrize("source_version", ["auth-sdk-python-v0.1.0", "refs/tags/auth-sdk-python-v0.1.0"])
def test_codebuild_tag_source_is_accepted(source_version, release_env):
    release_env.update(CODEBUILD_BUILD_ID="sdk:test", CODEBUILD_SOURCE_VERSION=source_version)
    validate_release("0.1.0", release_env)
