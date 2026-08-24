"""Authorization subrequest for the Arx I static archive (#3320, ADR-0232).

Caddy serves ``/arxmush-archive/*`` from disk and asks this endpoint whether the
request may have it (``forward_auth``). Django is therefore in the authorization
path but never in the data path: it answers a bodyless verdict and serves no
archive bytes.

``forward_auth`` proxies any non-2xx response straight back to the browser, so a
302 here is what redirects a logged-out reader to the SPA login route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from evennia_extensions.models import PlayerData
from world.gm.permissions import IsGMOrStaff

if TYPE_CHECKING:
    from rest_framework.request import Request

#: Where the archive is mounted on the web vhost. Must stay in step with
#: roles/caddy's ``caddy_archive_url_prefix`` and roles/arx1_archive's
#: ``arx1_archive_url_prefix`` - the Caddyfile mounts it, the sync script
#: rewrites the exported HTML's root-relative links to it, and this default
#: only matters when a proxy forwards no ``X-Forwarded-Uri``.
ARCHIVE_URL_PREFIX = "/arxmush-archive/"

#: SPA login route (frontend/src/App.tsx). ``next`` survives the round trip so a
#: reader lands back on the archive page they asked for.
LOGIN_PATH = "/login"


def request_may_read_arx1_archive(request: Request, view: APIView) -> bool:
    """Whether ``request``\'s account may read the Arx I archive.

    Staff and anyone holding a ``GMProfile`` are admitted outright - GMs refer to
    Arx I data as source material, and gating that behind a second per-account
    tick would be a flag to keep in sync with GM approval for no benefit. That
    half of the test is exactly ``IsGMOrStaff``, so it is delegated rather than
    restated. Everyone else needs the explicit
    ``PlayerData.arx1_archive_access`` grant, which defaults to ``False``.
    """
    if IsGMOrStaff().has_permission(request, view):
        return True
    try:
        # Deliberately NOT ``request.user.player_data``: the Account typeclass
        # shadows that reverse accessor with a get_or_CREATE property
        # (typeclasses/accounts.py), and forward_auth fires once per file a
        # page pulls - an authorization check has no business writing rows,
        # least of all at that rate. PlayerData is a primary_key=True O2O onto
        # the account, so its pk IS the account pk and this get is served from
        # the idmapper cache on repeat requests.
        player_data = PlayerData.objects.get(pk=request.user.pk)
    except PlayerData.DoesNotExist:
        return False
    return player_data.arx1_archive_access


class Arx1ArchiveAuthorizeAPIView(APIView):
    """Answer Caddy's ``forward_auth`` subrequest for the Arx I archive.

    Deliberately ``AllowAny`` with the verdict computed in the body: DRF's own
    401/403 for an unauthenticated request would leave a logged-out reader
    staring at a JSON error instead of the login page.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request, *args, **kwargs) -> Response:
        """Return 200 (allowed), 403 (denied), or 302 to login (anonymous)."""
        if not request.user.is_authenticated:
            return Response(
                status=status.HTTP_302_FOUND,
                headers={"Location": self._login_redirect(request)},
            )
        if not request_may_read_arx1_archive(request, self):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(status=status.HTTP_200_OK)

    @staticmethod
    def _login_redirect(request: Request) -> str:
        """Build the SPA login URL, preserving the archive path as ``next``.

        ``forward_auth`` sets ``X-Forwarded-Uri`` to the ORIGINAL request path,
        not this endpoint's - without it we would send every reader back to the
        archive index instead of the page they asked for.
        """
        target = request.headers.get("X-Forwarded-Uri") or ARCHIVE_URL_PREFIX
        # A caller-supplied header must not be able to bounce a reader off-site,
        # so keep only same-origin absolute paths and fall back to the index.
        if not target.startswith("/") or target.startswith("//"):
            target = ARCHIVE_URL_PREFIX
        return f"{LOGIN_PATH}?{urlencode({'next': target}, quote_via=quote)}"
