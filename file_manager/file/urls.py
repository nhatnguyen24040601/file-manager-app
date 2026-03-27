from django.urls import path
from .views import (
    FolderDetailView, FolderTreeView, ObjectPermissionView, ObjectMoveView,
    FolderCreateView, FileCreateView, ObjectRenameView, ObjectDeleteView
)

urlpatterns = [
    path('folders/', FolderCreateView.as_view(), name='folder-create'),
    path('folders/<uuid:pk>/', FolderDetailView.as_view(), name='folder-detail'),
    path('folders/<uuid:pk>/tree/', FolderTreeView.as_view(), name='folder-tree'),
    path('files/', FileCreateView.as_view(), name='file-create'),
    path('objects/<uuid:pk>/permissions/', ObjectPermissionView.as_view(), name='object-permissions'),
    path('objects/<uuid:pk>/move/', ObjectMoveView.as_view(), name='object-move'),
    path('objects/<uuid:pk>/rename/', ObjectRenameView.as_view(), name='object-rename'),
    path('objects/<uuid:pk>/', ObjectDeleteView.as_view(), name='object-delete'),
]