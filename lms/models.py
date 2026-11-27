import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

MODERATORS = "Moderators"


class User(AbstractUser):
    email = models.EmailField(unique=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("email"), name="lms_user_email_case_insensitive"),
        ]


class Course(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses")

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return self.title


class Lesson(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video_url = models.URLField(blank=True, max_length=2048)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lessons")

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return self.title


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="subscriptions")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "course"), name="lms_unique_course_subscription"),
        ]


class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="payments")
    request_id = models.UUIDField(default=uuid.uuid4)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    product_name = models.CharField(max_length=200)
    stripe_product_id = models.CharField(max_length=255, blank=True)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    checkout_url = models.URLField(max_length=2048, blank=True)
    success_url = models.URLField(max_length=2048)
    cancel_url = models.URLField(max_length=2048)
    status = models.CharField(max_length=20, default="pending")
    payment_status = models.CharField(max_length=30, default="unpaid")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pk",)
        constraints = [
            models.UniqueConstraint(fields=("user", "request_id"), name="lms_payment_request_unique"),
        ]
