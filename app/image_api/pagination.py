from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'meta': {
                'per_page': self.page_size,
                'current_page': self.page.number,
                'last_page': self.page.paginator.num_pages,
                'total': self.page.paginator.count,
                'from': self.page.start_index(),
                # 'to': self.page.end_index(),  # если нужно
            },
            'data': data
        })