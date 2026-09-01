#!/usr/bin/env python3
"""Mark Sentry issues resolved once their fix has merged.

Closes the loop the digest opens: an agent picks a row out of the Sentry digest
issue, ships the fix, then runs this to resolve it on the Sentry side. Accepts
short ids (``ARXII-1A``) or numeric issue ids, and resolves them together in one
call. Needs ``SENTRY_AUTH_TOKEN`` with the ``event:write`` scope.
"""

import argparse
import sys

from sentry_constants import SENTRY_ORG, SENTRY_PROJECT_ID, SentryAuthError, api_request

STATUSES = ("resolved", "resolvedInNextRelease", "ignored")


def resolve(identifiers: list[str], status: str) -> None:
    """Set the given Sentry issues to `status` in a single bulk mutation."""
    api_request(
        f"/organizations/{SENTRY_ORG}/issues/",
        params={"id": identifiers, "project": SENTRY_PROJECT_ID},
        method="PUT",
        body={"status": status},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issues", nargs="+", help="Sentry short ids (ARXII-1A) or numeric ids")
    parser.add_argument("--status", choices=STATUSES, default="resolved")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change only")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would set {', '.join(args.issues)} to {args.status}.")
        return 0

    try:
        resolve(args.issues, args.status)
    except SentryAuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Set {', '.join(args.issues)} to {args.status}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
