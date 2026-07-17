"""Project-wide default pagination.

Wired as ``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`` so every list endpoint
is paginated unless it explicitly opts out with ``pagination_class = None``
(2026-07 audit). Pagination-by-default is the safe posture: a new ViewSet can
no longer accidentally ship an unbounded list. Endpoints whose result set is
intrinsically small (a scene's speaker queue, one character's sanctums) opt out
so their response stays a bare array.
"""

from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """PageNumber pagination with an opt-in ``?page_size=`` override.

    ``page_size=50`` matches the most common per-endpoint convention already in
    use across the codebase; ``max_page_size`` caps a client asking for more.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
