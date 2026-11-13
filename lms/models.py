from django.conf import settings
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
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses")

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return self.title


class Lesson(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
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
