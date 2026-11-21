#!/usr/bin/env python3
"""Inventory candidate prompt files without modifying them."""

import argparse
import hashlib
import json
from pathlib import Path


def inventory(root):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as source:
            header = source.read(32)
            source.seek(0)
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        yield {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest,
            "header_hex": header.hex(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory containing candidate factory prompts")
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error(f"{args.directory} is not a directory")
    try:
        print(json.dumps(list(inventory(args.directory)), indent=2, ensure_ascii=True))
    except OSError as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
