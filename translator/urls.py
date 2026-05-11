from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_document, name='upload_document'),
    path('status/<uuid:document_id>/', views.get_status, name='get_status'), # <-- AÑADIR ESTA
]