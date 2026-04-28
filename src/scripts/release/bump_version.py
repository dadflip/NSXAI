#!/usr/bin/env python3
"""
Version management script for NSXAI.
Uses bump-my-version (bump2version fork) to manage semantic versions.

Usage:
    python bump_version.py [major|minor|patch|release|build]

Examples:
    python bump_version.py patch      # 0.1.0-dev -> 0.1.1-dev
    python bump_version.py minor      # 0.1.0-dev -> 0.2.0-dev
    python bump_version.py release    # 0.1.0-dev -> 0.1.0
"""

import subprocess
import sys
from pathlib import Path


def get_current_version():
    """Reads current version from VERSION file."""
    version_file = Path(__file__).parent.parent.parent.parent / "VERSION"
    return version_file.read_text().strip()


def bump_version(part):
    """Bumps version using bump-my-version."""
    try:
        result = subprocess.run(
            ["bump-my-version", "bump", part],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        print(f"\nVersion updated: {get_current_version()}")
    except subprocess.CalledProcessError as e:
        print(f"Error bumping version: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: bump-my-version is not installed.", file=sys.stderr)
        print("Install it with: pip install bump-my-version", file=sys.stderr)
        sys.exit(1)


def show_version():
    """Displays current version."""
    print(f"Current version: {get_current_version()}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        show_version()
        sys.exit(0)

    part = sys.argv[1].lower()

    valid_parts = ["major", "minor", "patch", "release", "build"]
    if part not in valid_parts:
        print(f"Invalid part: {part}")
        print(f"Valid parts: {', '.join(valid_parts)}")
        sys.exit(1)

    bump_version(part)


if __name__ == "__main__":
    main()
