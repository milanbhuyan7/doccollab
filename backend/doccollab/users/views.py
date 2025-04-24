import json
import logging
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from .serializers import UserCreateSerializer, UserSerializer, CustomTokenObtainPairSerializer, TeamMemberSerializer
from .models import TeamMember

logger = logging.getLogger(__name__)
User = get_user_model()

class UserCreateView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate token
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'token': str(refresh.access_token),
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class UserDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

class TeamMemberCreateView(generics.CreateAPIView):
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TeamMember.objects.filter(invited_by=self.request.user)
        
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team_member = serializer.save()
        
        # Send invitation email
        try:
            send_invitation_email(team_member)
            logger.info(f"Invitation email sent to {team_member.user.email}")
        except Exception as e:
            logger.error(f"Error sending invitation email: {str(e)}")
        
        return Response(
            TeamMemberSerializer(team_member).data,
            status=status.HTTP_201_CREATED
        )

def send_invitation_email(team_member):
    """Send invitation email to team member."""
    subject = f"You've been invited to join DocCollab by {team_member.invited_by.name}"
    
    # Create invitation link
    invitation_link = f"{settings.FRONTEND_URL}/join?email={team_member.user.email}"
    
    message = f"""
    Hello,
    
    {team_member.invited_by.name} ({team_member.invited_by.email}) has invited you to collaborate on DocCollab.
    
    Click the link below to join:
    {invitation_link}
    
    If you already have an account, you can simply log in.
    
    Best regards,
    The DocCollab Team
    """
    
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [team_member.user.email]
    
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)

# import json
# from rest_framework import status, generics
# from rest_framework.response import Response
# from rest_framework.permissions import AllowAny, IsAuthenticated
# from rest_framework_simplejwt.views import TokenObtainPairView
# from django.contrib.auth import get_user_model
# from django.core.mail import send_mail
# from django.conf import settings
# from .serializers import UserCreateSerializer, UserSerializer, CustomTokenObtainPairSerializer, TeamMemberSerializer
# from .models import TeamMember

# User = get_user_model()

# class UserCreateView(generics.CreateAPIView):
#     queryset = User.objects.all()
#     serializer_class = UserCreateSerializer
#     permission_classes = [AllowAny]

#     def create(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         user = serializer.save()
        
#         # Generate token
#         from rest_framework_simplejwt.tokens import RefreshToken
#         refresh = RefreshToken.for_user(user)
        
#         return Response({
#             'token': str(refresh.access_token),
#             'user': UserSerializer(user).data
#         }, status=status.HTTP_201_CREATED)

# class CustomTokenObtainPairView(TokenObtainPairView):
#     serializer_class = CustomTokenObtainPairSerializer

# class UserDetailView(generics.RetrieveAPIView):
#     queryset = User.objects.all()
#     serializer_class = UserSerializer
#     permission_classes = [IsAuthenticated]

#     def get_object(self):
#         return self.request.user

# class TeamMemberCreateView(generics.CreateAPIView):
#     serializer_class = TeamMemberSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         return TeamMember.objects.filter(invited_by=self.request.user)
        
#     def create(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         team_member = serializer.save()
        
#         # Send invitation email
#         try:
#             send_invitation_email(team_member)
#         except Exception as e:
#             print(f"Error sending invitation email: {str(e)}")
        
#         return Response(
#             TeamMemberSerializer(team_member).data,
#             status=status.HTTP_201_CREATED
#         )

# def send_invitation_email(team_member):
#     """Send invitation email to team member."""
#     subject = f"You've been invited to join DocCollab by {team_member.invited_by.name}"
    
#     # Create invitation link
#     invitation_link = f"{settings.FRONTEND_URL}/join?email={team_member.user.email}"
    
#     message = f"""
#     Hello,
    
#     {team_member.invited_by.name} ({team_member.invited_by.email}) has invited you to collaborate on DocCollab.
    
#     Click the link below to join:
#     {invitation_link}
    
#     If you already have an account, you can simply log in.
    
#     Best regards,
#     The DocCollab Team
#     """
    
#     from_email = settings.DEFAULT_FROM_EMAIL
#     recipient_list = [team_member.user.email]
    
#     send_mail(subject, message, from_email, recipient_list, fail_silently=False)
