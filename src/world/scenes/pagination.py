from rest_framework.pagination import CursorPagination, PageNumberPagination


class ScenePagination(PageNumberPagination):
    """
    Standard pagination for scenes list
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PersonaPagination(PageNumberPagination):
    """
    Standard pagination for personas list
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class SceneMessageCursorPagination(CursorPagination):
    """
    Cursor-based pagination for scene messages to support infinite scroll.
    Orders by sequence_number for chronological display.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "sequence_number"  # Chronological order
    cursor_query_param = "cursor"
    cursor_query_description = "The pagination cursor value."
