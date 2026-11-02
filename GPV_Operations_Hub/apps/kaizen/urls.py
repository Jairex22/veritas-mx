from django.urls import path

from . import views

app_name = "kaizen"
urlpatterns = [
    path("", views.board, name="board"),
    path("nueva/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/actualizar/", views.update, name="update"),
    path("<int:pk>/estado/", views.transition, name="transition"),
    path("<int:pk>/a3.pdf", views.a3_pdf, name="a3"),
]
