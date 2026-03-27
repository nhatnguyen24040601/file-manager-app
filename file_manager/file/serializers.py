from rest_framework import serializers
from .models import SecurableObject, Folder, File, Permission, ObjectPath, Group

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name', 'parent_group']

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'principal_id', 'principal_type', 'allow_mask', 'deny_mask', 'inheritance_flags']

class SecurableObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurableObject
        fields = ['id', 'name', 'type', 'owner', 'created_at']

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ['id', 'name', 'owner', 'file_size', 'mime_type', 'sha256_hash', 'created_at']

class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ['id', 'name', 'owner', 'parent', 'created_at']

# Serializer for building the recursive navigation tree
class NestedFolderSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = ['id', 'name', 'type', 'children']

    def get_children(self, obj):
        # Limit depth to prevent payload bloat in deep hierarchies
        depth = self.context.get('depth', 3)
        current_level = self.context.get('current_level', 0)
        
        if current_level < depth:
            child_folders = Folder.objects.filter(parent=obj)
            return NestedFolderSerializer(
                child_folders, 
                many=True, 
                context={'depth': depth, 'current_level': current_level + 1}
            ).data
        return

class FolderCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    parent_id = serializers.UUIDField(required=True)

class FileCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    parent_id = serializers.UUIDField(required=True)
    file_size = serializers.IntegerField(required=False, allow_null=True)
    mime_type = serializers.CharField(max_length=255, required=False, allow_blank=True)
    sha256_hash = serializers.CharField(max_length=255, required=False, allow_blank=True)

class ObjectRenameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
