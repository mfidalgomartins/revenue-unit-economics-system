"""Hash an API key from a hidden prompt or standard input."""

from __future__ import annotations

import getpass
import hashlib
import sys


def main() -> None:
    secret = (
        getpass.getpass("API key: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    )
    if len(secret) < 24:
        raise SystemExit("API keys must contain at least 24 characters")
    print(hashlib.sha256(secret.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
