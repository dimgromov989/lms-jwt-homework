from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Course, Lesson, User
from .permissions import is_moderator
from .validators import validate_youtube_links


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
        fields = ("id", "title", "description", "owner", "is_subscribed")
        read_only_fields = ("owner",)
        extra_kwargs = {
            "title": {"validators": [validate_youtube_links]},
            "description": {"validators": [validate_youtube_links]},
        }


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ("id", "title", "description", "course", "owner")
        read_only_fields = ("owner",)
        extra_kwargs = {
            "title": {"validators": [validate_youtube_links]},
            "description": {"validators": [validate_youtube_links]},
        }

    def validate_course(self, course):
        # Keep course and lesson ownership aligned, including moderator edits.
        user = self.context["request"].user
        owner_id = self.instance.owner_id if self.instance and is_moderator(user) else user.pk
        if course.owner_id != owner_id:
            raise serializers.ValidationError("Курс должен принадлежать владельцу урока.")
        return course
