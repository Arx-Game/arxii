"""Admin 'Sphinx of Black Quartz' coverage-audit view (#2640).

Superuser-only, read-only staff instrument: which anchor-role vows are
swearable today, per Tradition. Mirrors the ``game_setup_views.game_setup``
pattern exactly (superuser + ``@require_GET`` + plain template render).
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@staff_member_required
@require_GET
def sphinx_audit(request: HttpRequest) -> HttpResponse:
    """Read-only staff page: the Sphinx's coverage audit across the catalog.

    Runs ``world.covenants.sphinx.audit_vow_coverage`` — every active anchor
    ``CovenantRole`` x every active ``Tradition``, whether the tradition's
    signature-technique pool can fully/partially/never cover the role's
    authored specialty-function demands. Validation-plan instrument 2 (#2640).
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from world.covenants.sphinx import audit_vow_coverage  # noqa: PLC0415

    context = {
        "title": "Sphinx of Black Quartz — Coverage Audit",
        "rows": audit_vow_coverage(),
    }
    return render(request, "admin/sphinx_audit.html", context)
