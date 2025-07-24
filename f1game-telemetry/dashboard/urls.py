# dashboard/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # YENİ: Ana sayfa artık dashboard_view'ı gösterecek. İsmi 'dashboard'.
    path('', views.dashboard_view, name='dashboard'),
    
    # YENİ: Seans listesi artık /sessions/ adresinde olacak. İsmi 'session_list'.
    path('sessions/', views.session_list_view, name='session_list'),
    
    # Bu zaten vardı, aynı kalıyor.
    path('session/<str:session_uid>/', views.session_detail_view, name='session_detail'),
]