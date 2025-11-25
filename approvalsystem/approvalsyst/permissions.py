from rest_framework import permissions
from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsFinance(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name='finance').exists()

def user_has_role(user, role_name):
    if not user.is_authenticated:
        return False

    # Approver roles: match dynamic levels like approver-level-1, approver-level-2, ...
    if role_name == 'approver':
        return user.groups.filter(name__startswith='approver-level-').exists()

    # Finance, staff, etc: exact match
    return (
        user.groups.filter(name=role_name).exists() or 
        getattr(user, 'role', None) == role_name
    )

class IsStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, 'staff')

class IsApprover(permissions.BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, 'approver') or user_has_role(request.user, 'approver-level-1') or user_has_role(request.user, 'approver-level-2')

class IsFinance(permissions.BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, 'finance')

class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.created_by == request.user
