import hashlib
import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest


def test_wheel_validator_exists():
    assert Path('scripts/validate_wheel.py').is_file()


def test_wheel_metadata_and_hash(tmp_path):
    spec = importlib.util.spec_from_file_location('validate_wheel', 'scripts/validate_wheel.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / 'auth_sdk-0.2.0-py3-none-any.whl'
    with ZipFile(wheel, 'w') as package:
        package.writestr('auth_sdk-0.2.0.dist-info/METADATA', 'Name: auth-sdk\nVersion: 0.2.0\n')
    checksum = hashlib.sha256(wheel.read_bytes()).hexdigest()
    module.validate_wheel(wheel, version='0.2.0', sha256=checksum)
    for version, digest in [('0.1.0', checksum), ('0.2.0', '0' * 64), ('0.2.0', '')]:
        with pytest.raises(ValueError):
            module.validate_wheel(wheel, version=version, sha256=digest)
