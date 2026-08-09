"""Root URL configuration."""

from django.urls import include, path, re_path

from analytics_api.views import frontend

urlpatterns = [
    path("api/", include("analytics_api.urls")),
    re_path(r"^(?!api/).*$", frontend, name="frontend"),
]
