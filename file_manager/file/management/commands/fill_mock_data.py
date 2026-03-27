import uuid
import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from file.models import (
    SecurableObject, Folder, File, ObjectPath, 
    Group, Permission, FileVersion, AuditLog, ObjectType, PrincipalType
)

User = get_user_model()

# Permission Constants (Bitmasks)
READ = 1      # 0001
WRITE = 2     # 0010
DELETE = 4    # 0100
SHARE = 8     # 1000

class Command(BaseCommand):
    help = "Fills the database with detailed enterprise-level mock data."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Cleaning database...")
        # Since Folder and File inherit from SecurableObject, deleting from SecurableObject is enough.
        # However, due to CASCADE, we should delete them individually if needed.
        SecurableObject.objects.all().delete()
        Group.objects.all().delete()
        User.objects.filter(username__in=["admin", "manager", "staff_editor", "guest_viewer"]).delete()

        # 1. Create Users & Group Hierarchy
        self.stdout.write("Creating Users and Group Hierarchy...")
        admin_user = User.objects.create_superuser("admin", "admin@corp.com", "pass")
        manager_user = User.objects.create_user("manager", "mgr@corp.com", "pass")
        editor_user = User.objects.create_user("staff_editor", "edit@corp.com", "pass")
        viewer_user = User.objects.create_user("guest_viewer", "view@corp.com", "pass")

        system_admin_group = Group.objects.create(name="System Admin")
        dept_head_group = Group.objects.create(name="Dept Head", parent_group=system_admin_group)
        staff_group = Group.objects.create(name="General Staff", parent_group=dept_head_group)

        # 2. Create Deep Folder Structure (Scenario: 10 levels deep)
        # Root -> Finance -> 2025 -> Q1 -> Projects -> Internal ->...
        self.stdout.write("Creating Deep Hierarchy & Closure Table...")
        current_parent = None
        folder_chain = []
        folder_names = ["Root", "Finance", "2025", "Q1", "Projects", "Internal", "Resources", "Confidential", "Teams", "Development"]
        
        for name in folder_names:
            folder = Folder.objects.create(
                name=name,
                type=ObjectType.FOLDER,
                owner=admin_user,
                parent=current_parent
            )
            folder_chain.append(folder)
            self._update_closure_table(folder, current_parent)
            current_parent = folder

        # 3. Create Files with Versions (Scenario: 3 versions for a key document)
        self.stdout.write("Creating Files and Versions...")
        deep_folder = folder_chain[-1]
        tax_file = File.objects.create(
            name="Tax_Report_Final.pdf",
            type=ObjectType.FILE,
            owner=manager_user,
            file_size=1024500,
            mime_type="application/pdf",
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        self._update_closure_table(tax_file, deep_folder)

        for v in range(1, 4):
            FileVersion.objects.create(
                file_object=tax_file,
                version_num=v,
                storage_path=f"s3://bucket/tax_v{v}.pdf",
                created_by=manager_user
            )

        # 4. Complex ACL Scenarios
        self.stdout.write("Applying Granular Permissions...")
        
        # Case A: Inherited Allow at Root level for General Staff
        Permission.objects.create(
            securable_object=folder_chain[0], # Root
            principal_id=staff_group.id,
            principal_type=PrincipalType.GROUP,
            allow_mask=READ,
            inheritance_flags="fd" # File and Dir inherit
        )

        # Case B: Explicit Deny at 'Sensitive' level (Deny always wins)
        # Viewer is allowed at Root but denied at this specific folder
        Permission.objects.create(
            securable_object=folder_chain[1], # Sensitive Folder (Finance)
            principal_id=viewer_user.id,
            principal_type=PrincipalType.USER,
            deny_mask=READ | WRITE | DELETE
        )

        # Case C: Inherit Only (i) flag
        # Editor can Write to children of 'Projects', but not 'Projects' itself
        Permission.objects.create(
            securable_object=folder_chain[4], # Projects
            principal_id=editor_user.id,
            principal_type=PrincipalType.USER,
            allow_mask=WRITE,
            inheritance_flags="fi" # File inherit, Inherit Only
        )

        # 5. Soft Delete Scenario
        self.stdout.write("Creating Soft-Deleted Data...")
        deleted_folder = Folder.objects.create(
            name="Old_Archive_2020",
            type=ObjectType.FOLDER,
            owner=admin_user,
            parent=folder_chain[0],
            deleted_at=timezone.now()
        )
        self._update_closure_table(deleted_folder, folder_chain[0])

        # 6. Audit Logging
        self.stdout.write("Generating Audit Logs...")
        AuditLog.objects.create(
            user=admin_user,
            securable_object=tax_file,
            action="CREATE",
            outcome="SUCCESS",
            ip_address="192.168.1.1"
        )
        AuditLog.objects.create(
            user=viewer_user,
            securable_object=folder_chain[1],
            action="READ",
            outcome="DENIED",
            ip_address="10.0.0.5"
        )

        self.stdout.write(self.style.SUCCESS("Successfully filled mock data!"))

    def _update_closure_table(self, obj, parent):
        """
        Helper to maintain the Closure Table (ObjectPath).
        In a real app, this should be in a Service layer or Signal.
        """
        # 1. Links to self (depth 0)
        ObjectPath.objects.create(ancestor=obj, descendant=obj, depth=0)
        
        # 2. Links to all ancestors of parent
        if parent:
            ancestor_paths = ObjectPath.objects.filter(descendant=parent)
            new_paths = [
                ObjectPath(
                    ancestor=path.ancestor, 
                    descendant=obj, 
                    depth=path.depth + 1
                ) for path in ancestor_paths
            ]
            ObjectPath.objects.bulk_create(new_paths)
