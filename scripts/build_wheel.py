"""Build the versioned wheel context consumed by all application images."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def main():
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    output = ROOT / 'dist' / version
    subprocess.run([sys.executable, '-m', 'build', '--outdir', str(output)], cwd=ROOT, check=True)
    wheel = output / f'auth_sdk-{version}-py3-none-any.whl'
    sdist = output / f'auth_sdk-{version}.tar.gz'
    subprocess.run([sys.executable, '-m', 'twine', 'check', str(wheel), str(sdist)], check=True)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (output / 'SHA256SUMS').write_text(f'{digest}  {wheel.name}\n')
    shutil.copyfile(ROOT / 'scripts' / 'validate_wheel.py', output / 'validate_wheel.py')
    print(f'Build context: {output}')
    print(f'AUTH_SDK_WHEEL_SHA256={digest}')


if __name__ == '__main__':
    main()
