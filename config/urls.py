from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('markets.urls', 'markets'), namespace='markets')),
    path('', include(('markets.urls', 'api'), namespace='api')),
]
