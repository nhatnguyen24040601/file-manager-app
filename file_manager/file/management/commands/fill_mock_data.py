import uuid
import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from file.models import (
    SecurableObject, Folder, File, ObjectPath, 
    Group, Permission, FileVersion, AuditLog, ObjectType, PrincipalType, PermissionBits
)

User = get_user_model()

class Command(BaseCommand):
    help = "Fills the database with detailed enterprise-level mock data."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Cleaning database...")
        SecurableObject.objects.all().delete()
        Group.objects.all().delete()
        User.objects.filter(username__in=["admin", "manager", "staff_editor", "guest_viewer"]).delete()

        self.stdout.write("Creating Users and Group Hierarchy...")
        admin_user = User.objects.create_superuser("admin", "admin@corp.com", "pass")
        manager_user = User.objects.create_user("manager", "mgr@corp.com", "pass")
        editor_user = User.objects.create_user("staff_editor", "edit@corp.com", "pass")
        viewer_user = User.objects.create_user("guest_viewer", "view@corp.com", "pass")

        system_admin_group = Group.objects.create(name="System Admin")
        dept_head_group = Group.objects.create(name="Dept Head", parent_group=system_admin_group)
        staff_group = Group.objects.create(name="General Staff", parent_group=dept_head_group)

        self.stdout.write("Creating Broad Enterprise Folder Structure...")
        
        # Helper to create folders
        def make_folder(name, parent, owner):
            folder = Folder.objects.create(name=name, type=ObjectType.FOLDER, owner=owner, parent=parent)
            self._update_closure_table(folder, parent)
            return folder

        # Helper to create files
        def make_file(name, parent, owner, size, mime):
            f = File.objects.create(
                name=name, type=ObjectType.FILE, owner=owner,
                file_size=size, mime_type=mime,
                sha256_hash="mockhash" + str(random.randint(1000, 9999))
            )
            self._update_closure_table(f, parent)
            return f

        # Root level
        root_folder = make_folder("Corporate Drive", None, admin_user)

        # Department Level
        finance = make_folder("Finance", root_folder, manager_user)
        engineering = make_folder("Engineering", root_folder, admin_user)
        hr = make_folder("Human Resources", root_folder, manager_user)
        marketing = make_folder("Marketing", root_folder, editor_user)

        # Finance Content
        fin_2025 = make_folder("2025", finance, manager_user)
        make_file("Q1_Budget.xlsx", fin_2025, manager_user, 1500000, "application/vnd.ms-excel")
        make_file("Q2_Forecast.xlsx", fin_2025, manager_user, 2000000, "application/vnd.ms-excel")
        make_file("Q3_Forecast.xlsx", fin_2025, manager_user, 2100000, "application/vnd.ms-excel")
        fin_tax = make_folder("Tax Filings", finance, manager_user)
        tax_file = make_file("Tax_Report_Final.pdf", fin_tax, manager_user, 3500000, "application/pdf")

        # Engineering Content
        eng_source = make_folder("Source Code", engineering, admin_user)
        make_file("backend_repo_v2.zip", eng_source, admin_user, 50000000, "application/zip")
        make_file("frontend_react.zip", eng_source, admin_user, 45000000, "application/zip")
        eng_design = make_folder("Architecture Designs", engineering, admin_user)
        make_file("System_Diagram.png", eng_design, admin_user, 450000, "image/png")
        make_file("API_Specs.md", eng_design, admin_user, 15000, "text/markdown")

        # HR Content
        make_file("Employee_Handbook.pdf", hr, manager_user, 4200000, "application/pdf")
        make_file("Holiday_Schedule_2026.pdf", hr, manager_user, 100000, "application/pdf")
        onboarding = make_folder("Onboarding", hr, manager_user)
        make_file("Welcome_Video.mp4", onboarding, manager_user, 120000000, "video/mp4")
        make_file("Benefits_Overview.pptx", onboarding, manager_user, 5000000, "application/vnd.ms-powerpoint")

        # Marketing Content
        make_file("Brand_Guidelines.pdf", marketing, editor_user, 8000000, "application/pdf")
        assets = make_folder("Assets", marketing, editor_user)
        make_file("Logo_Vector.svg", assets, editor_user, 850000, "image/svg+xml")
        make_file("Banner_Ad_Summer.png", assets, editor_user, 2400000, "image/png")

        self.stdout.write("Creating File Versions...")
        for v in range(1, 4):
            FileVersion.objects.create(
                file_object=tax_file, version_num=v,
                storage_path=f"s3://bucket/tax_v{v}.pdf", created_by=manager_user
            )

        self.stdout.write("Applying Granular Permissions...")
        # General staff can read Root
        Permission.objects.create(
            securable_object=root_folder, principal_id=staff_group.id,
            principal_type=PrincipalType.GROUP, allow_mask=PermissionBits.READ_DATA | PermissionBits.TRAVERSE,
            inheritance_flags="fd"
        )
        
        # Hide Finance from General Staff entirely (Deny)
        Permission.objects.create(
            securable_object=finance, principal_id=staff_group.id,
            principal_type=PrincipalType.GROUP, deny_mask=PermissionBits.READ_DATA | PermissionBits.TRAVERSE,
            inheritance_flags="fd"
        )

        AuditLog.objects.create(
            user=admin_user, securable_object=root_folder, action="CREATE", outcome="SUCCESS", ip_address="127.0.0.1"
        )

        self.stdout.write(self.style.SUCCESS("Successfully populated extended mock data!"))

    def _update_closure_table(self, obj, parent):
        ObjectPath.objects.create(ancestor=obj, descendant=obj, depth=0)
        if parent:
            ancestor_paths = ObjectPath.objects.filter(descendant=parent)
            new_paths = [
                ObjectPath(ancestor=path.ancestor, descendant=obj, depth=path.depth + 1) 
                for path in ancestor_paths
            ]
            ObjectPath.objects.bulk_create(new_paths)
