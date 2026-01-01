from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class FastPagination(PageNumberPagination):
    page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })