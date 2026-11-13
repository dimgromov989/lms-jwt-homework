from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Course, Lesson, User

admin.site.register(User, UserAdmin)
admin.site.register(Course)
admin.site.register(Lesson)
