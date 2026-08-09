from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("benefits", views.benefits, name="benefits"),
    path("questions", views.questions, name="questions"),
    path("ask", views.ask, name="ask"),
    path("results/<str:result_id>", views.result_page, name="result-page"),
    path("results/<str:result_id>/download", views.result_download, name="result-download"),
]
