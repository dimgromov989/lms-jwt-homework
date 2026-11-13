from rest_framework.permissions import BasePermission

from .models import MODERATORS


def is_moderator(user):
    return user.groups.filter(name=MODERATORS).exists()


class OwnerOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.pk


class OwnerOrModerator(OwnerOnly):
    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) or is_moderator(request.user)


class NotModerator(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and not is_moderator(request.user)


class OwnProfile(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.pk == request.user.pk
