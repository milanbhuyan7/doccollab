from django.urls import path
from . import views

urlpatterns = [
    path('workspace/', views.get_workspace, name='get_workspace'),
    path('scrape-website/', views.scrape_website, name='scrape_website'),
    path('content/<uuid:file_id>/', views.get_file_content, name='get_file_content'),
    path('save-content/', views.save_content, name='save_content'),
    path('file/<uuid:file_uuid>/', views.get_file_by_uuid, name='get_file_by_uuid'),
    path('team-members/', views.get_team_members, name='get_team_members'),
]
