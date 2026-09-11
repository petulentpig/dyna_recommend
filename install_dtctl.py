#!/usr/bin/env python3
"""Install pinned upstream dtctl locally, verifying its published SHA-256."""
import hashlib
import io
import platform
import tarfile
from pathlib import Path
from urllib.request import urlopen

VERSION = '0.38.0'

def main():
    system=platform.system().lower()
    arch={'aarch64':'arm64','arm64':'arm64','x86_64':'amd64'}.get(platform.machine())
    if system not in {'darwin','linux'} or not arch:
        raise SystemExit('Use official dtctl installation instructions for this platform.')
    name=f'dtctl_{VERSION}_{system}_{arch}.tar.gz'
    base=f'https://github.com/dynatrace-oss/dtctl/releases/download/v{VERSION}/'
    with urlopen(base+'checksums.txt',timeout=60) as response:
        sums=response.read().decode()
    expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1]==name)
    with urlopen(base+name,timeout=60) as response:
        archive=response.read()
    if hashlib.sha256(archive).hexdigest()!=expected:
        raise SystemExit('Checksum mismatch; no binary installed.')
    target=Path(__file__).resolve().parent/'.tools'/'dtctl'
    target.parent.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        binary=tar.extractfile('dtctl').read()
    target.write_bytes(binary)
    target.chmod(0o755)
    print(f'Installed dtctl {VERSION}: {target}')

if __name__=='__main__': main()
