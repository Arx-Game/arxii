from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination for most story-related endpoints.
    Returns 20 items per page by default.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return paginated response with additional metadata"""
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": self.page_size,
                "num_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "results": data,
            }
        )


class SmallResultsSetPagination(PageNumberPagination):
    """
    Smaller pagination for detailed endpoints like chapter/episode lists.
    Returns 10 items per page by default.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_paginated_response(self, data):
        """Return paginated response with additional metadata"""
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": self.page_size,
                "num_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "results": data,
            }
        )


class LargeResultsSetPagination(PageNumberPagination):
    """
    Larger pagination for high-volume endpoints like feedback lists.
    Returns 50 items per page by default.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        """Return paginated response with additional metadata"""
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": self.page_size,
                "num_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "results": data,
            }
        )
