from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Course, Lesson, User
from .permissions import NotModerator, OwnerOnly, OwnerOrModerator, OwnProfile, is_moderator
from .serializers import CourseSerializer, LessonSerializer, PublicProfileSerializer, UserSerializer


class ActionPermissionsMixin:
    def get_permissions(self):
        classes = self.action_permissions.get(self.action, (IsAuthenticated,))
        return [permission() for permission in classes]


class UserViewSet(ActionPermissionsMixin, viewsets.ModelViewSet):
    queryset = User.objects.order_by("pk")
    serializer_class = UserSerializer
    action_permissions = {
        "create": (AllowAny,),
        "list": (IsAuthenticated,),
        "retrieve": (IsAuthenticated,),
        "update": (IsAuthenticated, OwnProfile),
        "partial_update": (IsAuthenticated, OwnProfile),
        "destroy": (IsAuthenticated, OwnProfile),
    }

    def get_authenticators(self):
        # Registration remains public even when an expired access token is sent.
        if self.action_map.get(self.request.method.lower()) == "create":
            return []
        return super().get_authenticators()

    def get_serializer_class(self):
        if self.action == "list":
            return PublicProfileSerializer
        if self.action == "retrieve" and str(self.request.user.pk) != self.kwargs.get("pk"):
            return PublicProfileSerializer
        return UserSerializer


class OwnedViewSet(ActionPermissionsMixin, viewsets.ModelViewSet):
    action_permissions = {
        "list": (IsAuthenticated,),
        "retrieve": (IsAuthenticated, OwnerOrModerator),
        "create": (IsAuthenticated, NotModerator),
        "update": (IsAuthenticated, OwnerOrModerator),
        "partial_update": (IsAuthenticated, OwnerOrModerator),
        "destroy": (IsAuthenticated, NotModerator, OwnerOnly),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_moderator(self.request.user):
            return queryset
        return queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class CourseViewSet(OwnedViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer


class LessonViewSet(OwnedViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
