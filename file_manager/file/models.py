import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings

# --- Enums & Choices ---

class ObjectType(models.TextChoices):
    FOLDER = 'folder', 'Folder'
    FILE = 'file', 'File'

class PrincipalType(models.TextChoices):
    USER = 'user', 'User'
    GROUP = 'group', 'Group'

class PermissionBits(models.IntegerChoices):
    READ_DATA = 1, 'Read Data'
    WRITE_DATA = 2, 'Write Data'
    APPEND_DATA = 4, 'Append Data'
    CREATE = 8, 'Create'
    DELETE = 16, 'Delete'
    DELETE_CHILD = 32, 'Delete Child'
    READ_ACL = 64, 'Read ACL'
    WRITE_ACL = 128, 'Write ACL'
    TRAVERSE = 256, 'Traverse'

# --- Core Hierarchy Models ---

class SecurableObject(models.Model):
    """
    Base table 'objects'. Acts as the SSoT for permissions and hierarchy.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=ObjectType.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name='owned_objects'
    )
    created_at = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True) # Soft-delete support

    class Meta:
        db_table = 'objects'
        indexes = [
            models.Index(fields=['deleted_at', 'type']),
        ]

class Folder(SecurableObject):
    """
    Table 'folders'. Specialized metadata for directories.
    """
    securableobject_ptr = models.OneToOneField(
        SecurableObject, on_delete=models.CASCADE,
        parent_link=True, primary_key=True, db_column='object_id', related_name='folder_detail'
    )
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children'
    )

    class Meta:
        db_table = 'folders'
        verbose_name = "Folder"

class File(SecurableObject):
    """
    Table 'files'. Binary-specific metadata.
    """
    securableobject_ptr = models.OneToOneField(
        SecurableObject, on_delete=models.CASCADE,
        parent_link=True, primary_key=True, db_column='object_id', related_name='file_detail'
    )
    file_size = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=255, null=True, blank=True)
    sha256_hash = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'files'

class ObjectPath(models.Model):
    """
    The Closure Table implementation. 
    Crucial for O(1) ancestry checks and deep nesting.
    """
    ancestor = models.ForeignKey(
        SecurableObject, on_delete=models.CASCADE, related_name='descendant_links'
    )
    descendant = models.ForeignKey(
        SecurableObject, on_delete=models.CASCADE, related_name='ancestor_links'
    )
    depth = models.IntegerField() # 0 for self-reference, 1 for immediate child

    class Meta:
        db_table = 'object_paths'
        constraints = [
            models.UniqueConstraint(
                fields=['ancestor', 'descendant'], name='unique_object_path'
            )
        ]

# --- Identity & Access Control (ACL) ---

class Group(models.Model):
    """
    Customizable Security Groups
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    parent_group = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subgroups'
    )

    class Meta:
        db_table = 'groups'

class GroupMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')

    class Meta:
        db_table = 'group_memberships'
        constraints = [
            models.UniqueConstraint(fields=['user', 'group'], name='unique_group_membership')
        ]

class Permission(models.Model):
    """
    Granular ACL Entries. Implements 'Deny Always Wins' and Inheritance Flags.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    securable_object = models.ForeignKey(
        SecurableObject, on_delete=models.CASCADE, related_name='acls', db_column='object_id'
    )
    principal_id = models.UUIDField() 
    principal_type = models.CharField(max_length=10, choices=PrincipalType.choices)
    allow_mask = models.IntegerField(default=0)
    deny_mask = models.IntegerField(default=0)
    inheritance_flags = models.CharField(max_length=10, default='')

    class Meta:
        db_table = 'permissions'
        indexes = [
            models.Index(fields=['securable_object', 'principal_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['securable_object', 'principal_id', 'principal_type'],
                name='unique_object_principal_permission'
            )
        ]

# --- Versioning & Auditing ---

class FileVersion(models.Model):
    """
    The History Table pattern for temporal data integrity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_object = models.ForeignKey(
        File, on_delete=models.CASCADE, related_name='versions', db_column='object_id'
    )
    version_num = models.IntegerField()
    storage_path = models.TextField() # Pointer to S3 or physical disk
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'file_versions'

class AuditLog(models.Model):
    """
    Append-only record for forensic readiness and compliance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    securable_object = models.ForeignKey(
        SecurableObject, on_delete=models.SET_NULL, null=True, db_column='object_id'
    )
    action = models.CharField(max_length=50) # READ, WRITE, DELETE, CHANGE_PERM
    outcome = models.CharField(max_length=20) # SUCCESS, DENIED
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
