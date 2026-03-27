from django.contrib import admin
from .models import SecurableObject, Folder, File, ObjectPath, Group, Permission, FileVersion, AuditLog

# Register your models here.
admin.site.register(SecurableObject)
admin.site.register(Folder)
admin.site.register(File)
admin.site.register(ObjectPath)
admin.site.register(Group)
admin.site.register(Permission)
admin.site.register(FileVersion)
admin.site.register(AuditLog)
