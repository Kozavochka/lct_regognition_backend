import django_filters
from .models import ImageLocation

class ImageLocationFilter(django_filters.FilterSet):
    # Фильтрация по дате создания (без времени)
    created_date_after = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_date_before = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = ImageLocation
        fields = []

class ImageLocationFilter(django_filters.FilterSet):
    lat = django_filters.NumberFilter(method='filter_by_radius')
    lon = django_filters.NumberFilter(method='filter_by_radius')
    radius_km = django_filters.NumberFilter(method='filter_by_radius')

    class Meta:
        model = ImageLocation
        fields = []

    def filter_by_radius(self, queryset, name, value):
        # Получаем lat, lon и radius из GET-параметров
        lat = self.data.get('lat')
        lon = self.data.get('lon')
        radius_km = self.data.get('radius_km')

        if lat and lon and radius_km:
            lat = float(lat)
            lon = float(lon)
            radius_km = float(radius_km)

            sql = """
            6371 * acos(
                cos(radians(%s)) *
                cos(radians(lat)) *
                cos(radians(lon) - radians(%s)) +
                sin(radians(%s)) *
                sin(radians(lat))
            ) <= %s
            """

            queryset = queryset.extra(
                where=[sql],
                params=[lat, lon, lat, radius_km]
            )
        return queryset