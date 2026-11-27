from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Course, Lesson, Payment, User
from .permissions import is_moderator
from .validators import validate_youtube_links, validate_youtube_url


class PublicProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name")


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    email = serializers.EmailField(max_length=254)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "password")

    def validate_email(self, value):
        email = value.lower()
        users = User.objects.filter(email__iexact=email)
        if self.instance:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise serializers.ValidationError("Этот email уже зарегистрирован.")
        return email

    def validate(self, attrs):
        if "password" in attrs:
            candidate = User(**{
                field: attrs.get(field, getattr(self.instance, field, ""))
                for field in ("username", "email", "first_name", "last_name")
            })
            try:
                validate_password(attrs["password"], user=candidate)
            except DjangoValidationError as error:
                raise serializers.ValidationError({"password": error.messages}) from error
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError("Логин или email уже зарегистрирован.") from error

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password is not None:
            instance.set_password(password)
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError("Логин или email уже используется.") from error


class CourseSerializer(serializers.ModelSerializer):
    is_subscribed = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Course
        fields = ("id", "title", "description", "price", "owner", "is_subscribed")
        read_only_fields = ("owner",)
        extra_kwargs = {
            "title": {"validators": [validate_youtube_links]},
            "description": {"validators": [validate_youtube_links]},
        }


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ("id", "title", "description", "video_url", "course", "owner")
        read_only_fields = ("owner",)
        extra_kwargs = {
            "title": {"validators": [validate_youtube_links]},
            "description": {"validators": [validate_youtube_links]},
            "video_url": {"validators": [validate_youtube_url]},
        }

    def validate_course(self, course):
        # Keep course and lesson ownership aligned, including moderator edits.
        user = self.context["request"].user
        owner_id = self.instance.owner_id if self.instance and is_moderator(user) else user.pk
        if course.owner_id != owner_id:
            raise serializers.ValidationError("Курс должен принадлежать владельцу урока.")
        return course


class PaymentCreateSerializer(serializers.Serializer):
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    request_id = serializers.UUIDField(required=False, help_text="UUID покупки. Повторите его для безопасного повтора запроса.")

    def validate_course(self, course):
        if course.price <= 0:
            raise serializers.ValidationError("Для оплаты цена курса должна быть больше нуля.")
        return course


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id", "user", "course", "request_id", "amount", "currency", "product_name",
            "stripe_product_id", "stripe_price_id", "stripe_session_id", "checkout_url",
            "success_url", "cancel_url", "status", "payment_status", "created_at",
        )
        read_only_fields = fields
