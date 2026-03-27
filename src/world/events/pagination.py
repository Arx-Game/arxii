from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class EventPagination(PageNumberPagination):
    """Standard pagination for event endpoints."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: list[Any]) -> Response:
        if self.page is None:
            msg = "Pagination requires a resolved page before building a response."
            raise RuntimeError(msg)
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": self.page_size,
                "num_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "results": data,
            },
        )
