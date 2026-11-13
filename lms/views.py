from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Course, Lesson, Subscription, User
from .paginators import MaterialPagination
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
    pagination_class = MaterialPagination
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
    action_permissions = {**OwnedViewSet.action_permissions, "subscription": (IsAuthenticated,)}

    def get_queryset(self):
        subscribed = Subscription.objects.filter(user=self.request.user, course_id=OuterRef("pk"))
        return super().get_queryset().annotate(is_subscribed=Exists(subscribed))

    @action(detail=True, methods=["post", "delete"])
    def subscription(self, request, pk=None):
        course = get_object_or_404(Course, pk=pk)
        subscriptions = Subscription.objects.filter(user=request.user, course=course)
        if request.method == "DELETE":
            deleted, _ = subscriptions.delete()
            if not deleted:
                return Response({"detail": "Подписка не найдена."}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": "Подписка удалена.", "is_subscribed": False})

        _, created = Subscription.objects.get_or_create(user=request.user, course=course)
        return Response(
            {
                "detail": "Подписка оформлена." if created else "Подписка уже существует.",
                "is_subscribed": True,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class LessonViewSet(OwnedViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
