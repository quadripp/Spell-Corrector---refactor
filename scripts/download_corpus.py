"""Download Norvig's big.txt corpus into data/big.txt.

Usage:
    python scripts/download_corpus.py            # writes data/big.txt
    python scripts/download_corpus.py --output some/other/big.txt
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

URL = 'https://raw.githubusercontent.com/norvig/pytudes/main/data/text/big.txt'
# SHA-256 of the copy the tests were written against. The tests check exact
# word counts, so a different file would make them fail in confusing ways.
EXPECTED_SHA256 = 'fa066c7d40f0f201ac4144e652aa62430e58a6b3805ec70650f678da5804e87b'
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / 'data' / 'big.txt'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--force', action='store_true', help='download even if the file exists')
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        print(f'{args.output} already exists; use --force to download again.')
        return

    print(f'Downloading {URL}')
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read()

    # Write to a temporary name first so an interrupted download never
    # leaves a half-written big.txt behind.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix('.part')
    partial.write_bytes(data)
    partial.replace(args.output)

    digest = hashlib.sha256(data).hexdigest()
    print(f'Saved {len(data):,} bytes to {args.output}')
    if digest != EXPECTED_SHA256:
        print(f'Warning: SHA-256 is {digest}, expected {EXPECTED_SHA256}. '
              'The upstream file may have changed, so the tests may fail.')


if __name__ == '__main__':
    main()
