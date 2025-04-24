from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from .models import TeamMember

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'name', 'date_joined')
        read_only_fields = ('id', 'date_joined')

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('email', 'name', 'password')

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            name=validated_data.get('name', ''),
            password=validated_data['password']
        )
        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        data['user'] = UserSerializer(self.user).data
        return data

class TeamMemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = TeamMember
        fields = ('id', 'user', 'email', 'created_at')
        read_only_fields = ('id', 'user', 'created_at')

    def create(self, validated_data):
        email = validated_data.pop('email')
        invited_by = self.context['request'].user
        
        # Get or create user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={'name': email.split('@')[0]}
        )
        
        # If user was created, set a random password
        if created:
            user.set_password(User.objects.make_random_password())
            user.save()
            # In a real app, you would send an invitation email here
        
        # Create team membership
        team_member, created = TeamMember.objects.get_or_create(
            user=user,
            invited_by=invited_by
        )
        
        return team_member
