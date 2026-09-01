#!/usr/bin/env python3
"""Mark Sentry issues resolved once their fix has merged.

Closes the loop the digest opens: an agent picks a row out of the Sentry digest
issue, ships the fix, then runs this to resolve it on the Sentry side. Accepts
short ids (``ARX2-6``, translated via the shortids endpoint - the bulk API takes
numeric ids only) or numeric ids, resolved together in one call. Needs
``SENTRY_AUTH_TOKEN`` with the ``event:write`` scope.
"""

import argparse
import sys

from sentry_constants import (
    SENTRY_ORG,
    SENTRY_PROJECT_ID,
    SentryAPIError,
    SentryAuthError,
    api_request,
    numeric_issue_id,
)

STATUSES = ("resolved", "resolvedInNextRelease", "ignored")


def resolve(identifiers: list[str], status: str) -> list[str]:
    """Set the given Sentry issues to `status`, returning the numeric ids acted on."""
    numeric = [numeric_issue_id(i) for i in identifiers]
    api_request(
        f"/organizations/{SENTRY_ORG}/issues/",
        params={"id": numeric, "project": SENTRY_PROJECT_ID},
        method="PUT",
        body={"status": status},
    )
    return numeric


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issues", nargs="+", help="Sentry short ids (ARX2-6) or numeric ids")
    parser.add_argument("--status", choices=STATUSES, default="resolved")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change only")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would set {', '.join(args.issues)} to {args.status}.")
        return 0

    try:
        numeric = resolve(args.issues, args.status)
    except (SentryAuthError, SentryAPIError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    pairs = ", ".join(f"{s} ({n})" for s, n in zip(args.issues, numeric, strict=True))
    print(f"Set {pairs} to {args.status}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
