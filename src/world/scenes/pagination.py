from rest_framework.pagination import PageNumberPagination


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
