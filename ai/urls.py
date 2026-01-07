from django.urls import path
from . import views

urlpatterns = [
    path('conversations/', views.get_conversations),
    path('conversations/<uuid:conversation_id>/messages/', views.get_messages),
    path('conversations/<uuid:conversation_id>/delete/', views.delete_conversation),
]