import django_filters
from .models import ImageLocation

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
        model = ImageLocation
        fields = []

    def filter_by_radius(self, queryset, name, value):
        # Извлекаем все три параметра из данных фильтра
        lat = self.data.get('lat')
        lon = self.data.get('lon')
        radius_km_param = self.data.get('radius_km')

        # Проверяем, все ли необходимые параметры присутствуют
        if lat is not None and lon is not None:
            try:
                lat = float(lat)
                lon = float(lon)
                radius_km = float(radius_km_param) if radius_km_param is not None else self.DEFAULT_RADIUS
            except (ValueError, TypeError):
                # Если не удается преобразовать в float, возвращаем пустой queryset или изначальный
                return queryset

            # SQL-выражение для расчета расстояния (Haversine formula approximation через acos)
            sql = """
            6371 * acos(
                cos(radians(%s)) *
                cos(radians(lat)) *
                cos(radians(lon) - radians(%s)) +
                sin(radians(%s)) *
                sin(radians(lat))
            ) <= %s
            """

            # Используем extra для добавления условия WHERE
            queryset = queryset.extra(
                where=[sql],
                params=[lat, lon, lat, radius_km]
            )
        return queryset