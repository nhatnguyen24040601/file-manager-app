from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, exceptions, permissions
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import SecurableObject, Folder, File, Permission, ObjectPath, ObjectType, Group, GroupMembership
from .serializers import (
    FolderSerializer, FileSerializer, PermissionSerializer, 
    SecurableObjectSerializer, NestedFolderSerializer,
    FolderCreateSerializer, FileCreateSerializer, ObjectRenameSerializer,
    UserSerializer, GroupSerializer, GroupMembershipInputSerializer
)

User = get_user_model()

class FolderDetailView(APIView):
    """
    GET: Retrieves folder metadata, breadcrumbs, and immediate children.
    """
    permission_classes = [AllowAny]
    def get(self, request, pk):
        try:
            folder = Folder.objects.get(pk=pk)
            
            # 1. Get breadcrumbs via Closure Table (O(1) ancestry check)
            breadcrumbs = ObjectPath.objects.filter(descendant=folder).select_related('ancestor').order_by('-depth')
            path_collection = [
                {"id": p.ancestor.id, "name": p.ancestor.name} for p in breadcrumbs
            ]

            # 2. List immediate children (Folders first, then Files)
            subfolders = Folder.objects.filter(parent=folder)
            
            # File references use ObjectPath since it doesn't have an explicit parent field in DBML
            file_paths = ObjectPath.objects.filter(ancestor=folder, depth=1, descendant__type='file').select_related('descendant__file_detail')
            files = [p.descendant.file_detail for p in file_paths if hasattr(p.descendant, 'file_detail')]

            return Response({
                "metadata": FolderSerializer(folder).data,
                "path_collection": path_collection,
                "entries": {
                    "folders": FolderSerializer(subfolders, many=True).data,
                    "files": FileSerializer(files, many=True).data
                }
            })
        except Folder.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

class FolderTreeView(APIView):
    """
    GET: Returns a nested JSON structure for sidebar navigation.
    """
    permission_classes = [AllowAny]
    def get(self, request, pk):
        try:
            folder = Folder.objects.get(pk=pk)
            depth = int(request.query_params.get('depth', 3))
            serializer = NestedFolderSerializer(folder, context={'depth': depth})
            return Response(serializer.data)
        except Folder.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

class ObjectPermissionView(APIView):
    """
    GET: List all ACL entries for an object.
    PUT: Update permissions (Add/Overwrite).
    """
    permission_classes = [AllowAny]
    def get(self, request, pk):
        perms = Permission.objects.filter(securable_object_id=pk)
        serializer = PermissionSerializer(perms, many=True)
        return Response(serializer.data)

    def put(self, request, pk):
        op_type = request.data.get('opType', 1)  # 1=Upsert, 2=Overwrite All, 3=Remove Specific
        permissions_data = request.data.get('permissions', [])

        if op_type == 2:
            # FULL RESET: Delete everything for this object and start fresh
            Permission.objects.filter(securable_object_id=pk).delete()

        for item in permissions_data:
            p_id = item.get('principal_id')
            p_type = item.get('principal_type')
            
            if not p_id or not p_type:
                continue

            if op_type == 3:
                # REMOVE: Delete permissions for this specific principal
                Permission.objects.filter(
                    securable_object_id=pk, 
                    principal_id=p_id, 
                    principal_type=p_type
                ).delete()
            else:
                # UPSERT: Update if exists, otherwise create
                Permission.objects.update_or_create(
                    securable_object_id=pk,
                    principal_id=p_id,
                    principal_type=p_type,
                    defaults={
                        "allow_mask": item.get('allow_mask', 0),
                        "deny_mask": item.get('deny_mask', 0),
                        "inheritance_flags": item.get('inheritance_flags', '')
                    }
                )

        # Return updated permissions
        perms = Permission.objects.filter(securable_object_id=pk)
        return Response(PermissionSerializer(perms, many=True).data)

class ObjectMoveView(APIView):
    """
    PATCH: Moves an object to a new parent and updates the Closure Table.
    """
    permission_classes = [AllowAny]
    @transaction.atomic
    def patch(self, request, pk):
        new_parent_id = request.data.get('new_parent_id')
        try:
            obj = SecurableObject.objects.get(pk=pk)
            new_parent = Folder.objects.get(pk=new_parent_id)
        except (SecurableObject.DoesNotExist, Folder.DoesNotExist):
            return Response(status=status.HTTP_404_NOT_FOUND)

        # 1. Delete old paths for this object and its descendants
        ObjectPath.objects.filter(descendant=obj).delete()

        # 2. Re-calculate Closure Table rows
        ancestors = ObjectPath.objects.filter(descendant=new_parent)
        new_paths = [
            ObjectPath(ancestor=p.ancestor, descendant=obj, depth=p.depth + 1)
            for p in ancestors
        ]
        new_paths.append(ObjectPath(ancestor=obj, descendant=obj, depth=0))
        ObjectPath.objects.bulk_create(new_paths)

        # 3. Update actual parent pointer (only applicable to Folders in DBML)
        if obj.type == 'folder':
            folder_record = Folder.objects.get(pk=obj.id)
            folder_record.parent = new_parent
            folder_record.save()

        return Response({"status": "moved"})

class FolderCreateView(APIView):
    """
    POST: Creates a new folder, base object, and updates Closure Table.
    """
    permission_classes = [AllowAny]
    @transaction.atomic
    def post(self, request):
        serializer = FolderCreateSerializer(data=request.data)
        if serializer.is_valid():
            parent_id = serializer.validated_data['parent_id']
            try:
                parent_folder = Folder.objects.get(pk=parent_id)
            except Folder.DoesNotExist:
                return Response({"error": "Parent folder not found."}, status=status.HTTP_404_NOT_FOUND)

            owner = request.user if request.user.is_authenticated else User.objects.first()
            if not owner:
                return Response({"error": "No users available for ownership."}, status=status.HTTP_400_BAD_REQUEST)

            new_folder = Folder.objects.create(
                name=serializer.validated_data['name'],
                type=ObjectType.FOLDER,
                owner=owner,
                parent=parent_folder
            )

            ObjectPath.objects.create(ancestor=new_folder, descendant=new_folder, depth=0)
            ancestors = ObjectPath.objects.filter(descendant=parent_folder)
            new_paths = [
                ObjectPath(ancestor=p.ancestor, descendant=new_folder, depth=p.depth + 1) 
                for p in ancestors
            ]
            ObjectPath.objects.bulk_create(new_paths)

            return Response(FolderSerializer(new_folder).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FileCreateView(APIView):
    """
    POST: Creates a file metadata object and maps it in closure table.
    """
    permission_classes = [AllowAny]
    @transaction.atomic
    def post(self, request):
        serializer = FileCreateSerializer(data=request.data)
        if serializer.is_valid():
            parent_id = serializer.validated_data['parent_id']
            try:
                parent_folder = Folder.objects.get(pk=parent_id)
            except Folder.DoesNotExist:
                return Response({"error": "Parent folder not found."}, status=status.HTTP_404_NOT_FOUND)

            owner = request.user if request.user.is_authenticated else User.objects.first()
            if not owner:
                return Response({"error": "No users available for ownership."}, status=status.HTTP_400_BAD_REQUEST)

            new_file = File.objects.create(
                name=serializer.validated_data['name'],
                type=ObjectType.FILE,
                owner=owner,
                file_size=serializer.validated_data.get('file_size'),
                mime_type=serializer.validated_data.get('mime_type'),
                sha256_hash=serializer.validated_data.get('sha256_hash'),
            )

            ObjectPath.objects.create(ancestor=new_file, descendant=new_file, depth=0)
            ancestors = ObjectPath.objects.filter(descendant=parent_folder)
            new_paths = [
                ObjectPath(ancestor=p.ancestor, descendant=new_file, depth=p.depth + 1) 
                for p in ancestors
            ]
            ObjectPath.objects.bulk_create(new_paths)

            return Response(FileSerializer(new_file).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ObjectRenameView(APIView):
    """
    PATCH: Renames a securable object.
    """
    permission_classes = [AllowAny]
    def patch(self, request, pk):
        try:
            obj = SecurableObject.objects.get(pk=pk)
        except SecurableObject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
        serializer = ObjectRenameSerializer(data=request.data)
        if serializer.is_valid():
            obj.name = serializer.validated_data['name']
            obj.save(update_fields=['name'])
            return Response({"status": "renamed", "name": obj.name})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ObjectDeleteView(APIView):
    """
    DELETE: Soft-deletes a securable object.
    """
    permission_classes = [AllowAny]
    def delete(self, request, pk):
        try:
            obj = SecurableObject.objects.get(pk=pk)
        except SecurableObject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
        obj.deleted_at = timezone.now()
        obj.save(update_fields=['deleted_at'])
        return Response({"status": "deleted"}, status=status.HTTP_204_NO_CONTENT)

class UserListView(APIView):
    """
    GET: List all users for assigning permissions or adding to groups.
    """
    permission_classes = [AllowAny]
    def get(self, request):
        users = User.objects.all()
        return Response(UserSerializer(users, many=True).data)

class GroupListCreateView(APIView):
    """
    GET: List all groups.
    POST: Create a new group.
    """
    permission_classes = [AllowAny]
    def get(self, request):
        groups = Group.objects.all()
        return Response(GroupSerializer(groups, many=True).data)

    def post(self, request):
        serializer = GroupSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GroupDetailView(APIView):
    """
    GET: Retrieve specific group.
    PATCH: Update group (e.g., name or parent).
    DELETE: Remove group.
    """
    permission_classes = [AllowAny]
    def get_object(self, pk):
        try:
            return Group.objects.get(pk=pk)
        except Group.DoesNotExist:
            return None

    def get(self, request, pk):
        group = self.get_object(pk)
        if not group: return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(GroupSerializer(group).data)

    def patch(self, request, pk):
        group = self.get_object(pk)
        if not group: return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = GroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        group = self.get_object(pk)
        if not group: return Response(status=status.HTTP_404_NOT_FOUND)
        group.delete()
        # Note: If there are foreign keys protecting deletion, Django will raise ProtectedError.
        return Response(status=status.HTTP_204_NO_CONTENT)

class GroupMembershipView(APIView):
    """
    GET: List users in group.
    POST: Add user to group.
    DELETE: Remove user from group.
    """
    permission_classes = [AllowAny]
    def get(self, request, pk):
        memberships = GroupMembership.objects.filter(group_id=pk).select_related('user')
        users = [m.user for m in memberships]
        return Response(UserSerializer(users, many=True).data)

    @transaction.atomic
    def post(self, request, pk):
        try:
            group = Group.objects.get(pk=pk)
        except Group.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        serializer = GroupMembershipInputSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
            GroupMembership.objects.get_or_create(group=group, user=user)
            return Response({"status": "user added to group"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def delete(self, request, pk):
        serializer = GroupMembershipInputSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            deleted, _ = GroupMembership.objects.filter(group_id=pk, user_id=user_id).delete()
            if deleted == 0:
                return Response({"error": "User was not in group."}, status=status.HTTP_404_NOT_FOUND)
            return Response({"status": "user removed from group"}, status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)