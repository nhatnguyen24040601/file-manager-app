from django.urls import path
from .views import FolderDetailView, FolderTreeView, ObjectPermissionView, ObjectMoveView

urlpatterns = [
    path('folders/<uuid:pk>/', FolderDetailView.as_view(), name='folder-detail'),
    path('folders/<uuid:pk>/tree/', FolderTreeView.as_view(), name='folder-tree'),
    path('objects/<uuid:pk>/permissions/', ObjectPermissionView.as_view(), name='object-permissions'),
    path('objects/<uuid:pk>/move/', ObjectMoveView.as_view(), name='object-move'),
]