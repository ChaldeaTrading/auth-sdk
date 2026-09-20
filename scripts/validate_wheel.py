"""Validate the explicit SDK build input before installing it in an image."""
import argparse
from email.parser import BytesParser
import hashlib
from pathlib import Path
import re
from zipfile import ZipFile


def validate_wheel(path: Path, *, version: str, sha256: str) -> None:
    if not re.fullmatch(r'[0-9a-f]{64}', sha256):
        raise ValueError('an explicit SHA-256 checksum is required')
    if path.name != f'chaldeatrading_auth_sdk-{version}-py3-none-any.whl':
        raise ValueError('unexpected SDK wheel filename')
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise ValueError('SDK wheel checksum mismatch')
    with ZipFile(path) as wheel:
        metadata = BytesParser().parsebytes(
            wheel.read(f'chaldeatrading_auth_sdk-{version}.dist-info/METADATA')
        )
    if metadata['Name'] != 'chaldeatrading-auth-sdk' or metadata['Version'] != version:
        raise ValueError('SDK wheel metadata mismatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    try:
        validate_wheel(args.wheel, version=args.version, sha256=args.sha256)
    except Exception:
        parser.exit(1, 'SDK wheel validation failed\n')
    print('SDK wheel validated')
