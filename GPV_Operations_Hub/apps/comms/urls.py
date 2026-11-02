from django.urls import path

from . import views

app_name = "comms"
urlpatterns = [
    path("", views.announcement_list, name="list"),
    path("nuevo/", views.announcement_edit, name="create"),
    path("<int:ann_id>/", views.announcement_detail, name="detail"),
    path("<int:ann_id>/editar/", views.announcement_edit, name="edit"),
    path("<int:ann_id>/confirmar/", views.announcement_ack, name="ack"),
    path("<int:ann_id>/retirar/", views.announcement_unpublish, name="unpublish"),
    path("comentarios/", views.comment_post, name="comment"),
    path("comentarios/<int:comment_id>/resolver/", views.comment_resolve, name="comment_resolve"),
    path("incidencias/", views.incidents, name="incidents"),
    path("conversaciones/", views.conversation_list, name="conversations"),
    path("conversaciones/nueva/", views.conversation_create, name="conversation_create"),
    path("conversaciones/<int:conv_id>/", views.conversation_detail, name="conversation"),
]
