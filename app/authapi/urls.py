from django.urls import path, include
from . import views

urlpatterns = [
    # path('register/', views.UserRegistrationView.as_view(), name='register'),
    # path('login/', views.UserLoginView.as_view(), name='login'),
    # path('logout/', views.UserLogoutView.as_view(), name='logout'),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
]

# регистрация POST /auth/users/
# {
#   "username": "john_doe",
#   "password": "MyStrongPassword123!",
#   "re_password": "MyStrongPassword123!"
# }

# Успешный ответ(201 Created):
# {
#   "username": "john_doe",
#   "email": ""  // или email, если передавался
# }

# Авторизация POST /auth/jwt/create/ HTTP/1.1
# {
#   "username": "john_doe",
#   "password": "MyStrongPassword123!"
# }

# Успешный ответ (200 OK):
# {
#   "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.xxxxx",
#   "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.yyyyy"
# }

# Обновление POST /auth/jwt/refresh/ HTTP/1.1
# {
#   "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.yyyyy"
# }

# ответ 200
# {
#   "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.new_access_token",
#   "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.new_refresh_token"  // если ROTATE_REFRESH_TOKENS=True
# }


# Выход POST /auth/jwt/logout/ HTTP/1.1
# {
#   "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.yyyyy"
# }

# Ответ 200
# {
#   "detail": "Successfully logged out"
# }

# Что делать на фронтенде при «выходе»?
# Даже если сервер добавил refresh в чёрный список — фронтенд должен удалить оба токена из памяти:
# localStorage.removeItem('access_token');
# localStorage.removeItem('refresh_token');