from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserCreateView, CustomTokenObtainPairView, UserDetailView, TeamMemberCreateView

urlpatterns = [
    path('signup/', UserCreateView.as_view(), name='signup'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('user/me/', UserDetailView.as_view(), name='user_detail'),
    path('invite-member/', TeamMemberCreateView.as_view(), name='invite_member'),
]
