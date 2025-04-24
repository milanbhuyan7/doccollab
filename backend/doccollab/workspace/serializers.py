from rest_framework import serializers
from .models import Workspace, File, FileContent

class FileContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileContent
        fields = ('content',)

class FileSerializer(serializers.ModelSerializer):
    content = FileContentSerializer(read_only=True)
    
    class Meta:
        model = File
        fields = ('id', 'name', 'type', 'parent', 'content', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ('id', 'name', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

class ScrapeWebsiteSerializer(serializers.Serializer):
    url = serializers.URLField()

class SaveContentSerializer(serializers.Serializer):
    file_id = serializers.UUIDField()
    content = serializers.JSONField()
