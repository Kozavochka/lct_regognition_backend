import django_filters
from .models import ImageLocation, DetectedImageLocation

from django.db.models import F, FloatField, ExpressionWrapper
from django.db.models.functions import ACos, Cos, Sin, Radians
DEFAULT_RADIUS = 1

class ImageLocationDateFilter(django_filters.FilterSet):
    """
    Фильтр для фильтрации по дате создания (без времени).
    Использует префиксы 'date_after' и 'date_before'.
    """
    date_after = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    date_before = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = ImageLocation
        fields = []


class RadiusFilter(django_filters.FilterSet):
    """
    Фильтр для фильтрации по радиусу от заданных координат.
    Использует параметры 'lat', 'lon', 'radius_km'.
    """
    lat = django_filters.NumberFilter(method='filter_by_radius')
    lon = django_filters.NumberFilter(method='filter_by_radius')
    radius_km = django_filters.NumberFilter(method='filter_by_radius')

    DEFAULT_RADIUS = 1

    class Meta:
        model = DetectedImageLocation
        fields = []

    def filter_by_radius(self, queryset, name, value):
        lat = self.data.get('lat')
        lon = self.data.get('lon')
        radius_km_param = self.data.get('radius_km')

        if lat is not None and lon is not None:
            try:
                lat = float(lat)
                lon = float(lon)
                radius_km = float(radius_km_param) if radius_km_param is not None else self.DEFAULT_RADIUS
            except (ValueError, TypeError):
                return queryset

            distance_expr = ExpressionWrapper(
                6371 * ACos(
                    Cos(Radians(lat)) *
                    Cos(Radians(F('lat'))) *
                    Cos(Radians(F('lon')) - Radians(lon)) +
                    Sin(Radians(lat)) *
                    Sin(Radians(F('lat')))
                ),
                output_field=FloatField()
            )

            queryset = queryset.annotate(distance=distance_expr).filter(distance__lte=radius_km)

        return queryset
