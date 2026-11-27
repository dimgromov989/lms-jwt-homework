import uuid

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Exists, OuterRef
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Course, Lesson, Payment, Subscription, User
from . import services
from .paginators import MaterialPagination
from .permissions import NotModerator, OwnerOnly, OwnerOrModerator, OwnProfile, is_moderator
from .serializers import (
    CourseSerializer, LessonSerializer, PaymentCreateSerializer, PaymentSerializer,
    PublicProfileSerializer, UserSerializer,
)
from .schema import course_schema, lesson_schema, payment_schema, subscription_schema, user_schema


class ActionPermissionsMixin:
    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as error:
            raise serializers.ValidationError("Удаление невозможно, объект связан с платежами.") from error

    def get_permissions(self):
        classes = self.action_permissions.get(self.action, (IsAuthenticated,))
        return [permission() for permission in classes]


@user_schema
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
        if getattr(self, "swagger_fake_view", False):
            return super().get_authenticators()
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
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if is_moderator(self.request.user):
            return queryset
        return queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@course_schema
class CourseViewSet(OwnedViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    action_permissions = {**OwnedViewSet.action_permissions, "subscription": (IsAuthenticated,)}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        subscribed = Subscription.objects.filter(user=self.request.user, course_id=OuterRef("pk"))
        return super().get_queryset().annotate(is_subscribed=Exists(subscribed))

    @subscription_schema
    @action(detail=True, methods=["post", "delete"])
    @transaction.atomic
    def subscription(self, request, pk=None):
        course = get_object_or_404(Course.objects.select_for_update(), pk=pk)
        subscriptions = Subscription.objects.filter(user=request.user, course=course)
        deleted, _ = subscriptions.delete()
        if deleted:
            return Response({"detail": "Подписка удалена.", "is_subscribed": False})
        if request.method == "DELETE":
            return Response({"detail": "Подписка не найдена."}, status=status.HTTP_404_NOT_FOUND)

        Subscription.objects.create(user=request.user, course=course)
        return Response(
            {"detail": "Подписка оформлена.", "is_subscribed": True},
            status=status.HTTP_201_CREATED,
        )


@lesson_schema
class LessonViewSet(OwnedViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer


@payment_schema
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = MaterialPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        return super().get_queryset().filter(user=self.request.user)

    def create(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = services.stripe_client()
        course = serializer.validated_data["course"]
        request_id = serializer.validated_data.get("request_id", uuid.uuid4())
        with transaction.atomic():
            payment, created = Payment.objects.get_or_create(
                user=request.user, request_id=request_id,
                defaults={"course": course, "amount": course.price, "product_name": course.title,
                          "currency": settings.STRIPE_CURRENCY,
                          "success_url": settings.STRIPE_SUCCESS_URL, "cancel_url": settings.STRIPE_CANCEL_URL},
            )
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.course_id != course.pk:
                return Response({"detail": "request_id уже используется для другого курса."}, status=400)
            try:
                services.start_checkout(client, payment)
            except stripe.StripeError:
                # Commit successful stages so the same purchase can be resumed.
                payment.status = "failed"
                payment.save(update_fields=["status"])
                return Response(
                    {"detail": str(services.StripeUnavailable.default_detail),
                     "payment_id": payment.pk, "request_id": str(payment.request_id)}, status=503,
                )
        return Response(PaymentSerializer(payment).data, status=201 if created else 200)

    @action(detail=True, methods=["post"], url_path="sync")
    def sync(self, request, pk=None):
        client = services.stripe_client()
        with transaction.atomic():
            payment = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if not payment.stripe_session_id:
                return Response({"detail": "Сессия оплаты ещё не создана."}, status=400)
            try:
                session = services.retrieve_session(client, payment)
            except stripe.StripeError as error:
                raise services.StripeUnavailable() from error
            payment.status = session["status"]
            payment.payment_status = session["payment_status"]
            payment.save(update_fields=["status", "payment_status"])
        return Response(PaymentSerializer(payment).data)
