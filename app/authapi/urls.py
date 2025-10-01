from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import UserViewSet,CurrentUserView

router = DefaultRouter()
router.register(r'users', UserViewSet)

urlpatterns = [
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
    path('', include(router.urls)),
    path('auth/me/', CurrentUserView.as_view(), name='current-user'),   
]
