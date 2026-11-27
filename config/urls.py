from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from lms.views import CourseViewSet, LessonViewSet, PaymentViewSet, UserViewSet
from lms.schema import LoginView, RefreshView

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("courses", CourseViewSet)
router.register("lessons", LessonViewSet)
router.register("payments", PaymentViewSet)

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("admin/", admin.site.urls),
    path("api/token/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),
]
