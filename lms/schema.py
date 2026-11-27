from drf_spectacular.utils import (
    OpenApiParameter, OpenApiResponse, PolymorphicProxySerializer, extend_schema,
    extend_schema_view, inline_serializer,
)
from rest_framework import serializers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    CourseSerializer, LessonSerializer, PaymentCreateSerializer, PaymentSerializer,
    PublicProfileSerializer, UserSerializer,
)

DETAIL = inline_serializer("DetailError", fields={"detail": serializers.CharField()})
VALIDATION = OpenApiResponse(
    response={"oneOf": [
        {"type": "object", "additionalProperties": {
            "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
        }},
        {"type": "array", "items": {"type": "string"}},
    ]},
    description="Ошибки полей. При запрете удаления связанного с платежом объекта — список ошибок.",
)
ERRORS = {
    400: VALIDATION, 401: OpenApiResponse(DETAIL, description="Нужен действительный JWT."),
    403: OpenApiResponse(DETAIL, description="Недостаточно прав."),
    404: OpenApiResponse(DETAIL, description="Объект отсутствует или недоступен."),
}
PAGES = [
    OpenApiParameter("page", int, description="Номер страницы, начиная с 1."),
    OpenApiParameter("page_size", int, description="Размер страницы. По умолчанию 10, максимум 50."),
]


def crud_schema(serializer, description, *, user=False):
    pages = [OpenApiParameter("page", int, description="Номер страницы, по 20 профилей.")] if user else PAGES
    return extend_schema_view(
        list=extend_schema(description=description, parameters=pages,
                           responses={200: serializer(many=True), 401: ERRORS[401], 404: ERRORS[404]}),
        retrieve=extend_schema(description=description, responses={200: serializer, **ERRORS}),
        create=extend_schema(description=description, responses={201: serializer, **ERRORS}),
        update=extend_schema(description=description, responses={200: serializer, **ERRORS}),
        partial_update=extend_schema(description=description, responses={200: serializer, **ERRORS}),
        destroy=extend_schema(description=description, responses={204: None, **ERRORS}),
    )


course_schema = crud_schema(
    CourseSerializer,
    "Владелец управляет своими курсами. Модератор читает и редактирует все курсы, "
    "создание и удаление ему запрещены. price — цена в основных единицах валюты STRIPE_CURRENCY, "
    "неотрицательная, два знака после запятой. is_subscribed относится к текущему пользователю. "
    "Название и описание допускают ссылки только на youtube.com и его поддомены.",
)
lesson_schema = crud_schema(
    LessonSerializer,
    "Владелец управляет своими уроками. Модератор может читать и редактировать все уроки. "
    "Курс и урок должны иметь одного владельца. Ссылки допускаются только на youtube.com "
    "и его поддомены. video_url необязателен.",
)
profile = PolymorphicProxySerializer(
    component_name="Profile", serializers=[UserSerializer, PublicProfileSerializer],
    resource_type_field_name=None,
)
user_schema = extend_schema_view(
    list=extend_schema(description="Публичные профили. JWT обязателен, по 20 записей.",
                       responses={200: PublicProfileSerializer(many=True), 401: ERRORS[401]}),
    retrieve=extend_schema(description="Свой полный профиль или публичные поля чужого профиля.",
                           responses={200: profile, 401: ERRORS[401], 404: ERRORS[404]}),
    create=extend_schema(description="Публичная регистрация. Пароль принимается только на запись.",
                         responses={201: UserSerializer, 400: VALIDATION}),
    update=extend_schema(description="Обновление только своего профиля.", responses={200: UserSerializer, **ERRORS}),
    partial_update=extend_schema(description="Частичное обновление своего профиля.", responses={200: UserSerializer, **ERRORS}),
    destroy=extend_schema(description="Удаление своего профиля. Профиль с платежами защищён от удаления.",
                          responses={204: None, **ERRORS}),
)
subscription_result = inline_serializer("SubscriptionResult", fields={
    "detail": serializers.CharField(), "is_subscribed": serializers.BooleanField(),
})
def subscription_schema(method):
    method = extend_schema(
        methods=["POST"], request=None,
        description="Переключает подписку текущего пользователя на любой курс по ID. "
        "Создание возвращает 201, отписка 200.",
        responses={200: subscription_result, 201: subscription_result,
                   401: ERRORS[401], 404: ERRORS[404]},
    )(method)
    return extend_schema(
        methods=["DELETE"], request=None, description="Снимает подписку. Отсутствие подписки даёт 404.",
        responses={200: subscription_result, 401: ERRORS[401], 404: ERRORS[404]},
    )(method)


stripe_error = inline_serializer("StripeError", fields={
    "detail": serializers.CharField(),
    "payment_id": serializers.IntegerField(required=False),
    "request_id": serializers.UUIDField(required=False),
})
payment_schema = extend_schema_view(
    list=extend_schema(description="Только свои платежи, включая незавершённые.", parameters=PAGES,
                       responses={200: PaymentSerializer(many=True), 401: ERRORS[401], 404: ERRORS[404]}),
    retrieve=extend_schema(description="Сохранённые данные своего платежа без запроса в Stripe.",
                           responses={200: PaymentSerializer, 401: ERRORS[401], 404: ERRORS[404]}),
    create=extend_schema(
        request=PaymentCreateSerializer,
        description="Покупка любого существующего курса с положительной ценой. Сумма берётся с сервера "
        "и умножается на 100. Создаются Product, Price и Checkout Session. UUID request_id "
        "обеспечивает повтор покупки без дублирования. Для новой покупки используйте новый UUID. "
        "При сбое сохранённые этапы продолжаются повтором с тем же request_id.",
        responses={200: PaymentSerializer, 201: PaymentSerializer, 400: VALIDATION, 401: ERRORS[401],
                   503: OpenApiResponse(stripe_error, description="Stripe недоступен или не настроен. "
                                        "При сбое создания также возвращаются payment_id и request_id.")},
    ),
    sync=extend_schema(
        request=None, description="Получить Stripe Session и сохранить status (open, complete, expired) "
        "и payment_status (unpaid, paid, no_payment_required). Только для своего платежа.",
        responses={200: PaymentSerializer, 400: ERRORS[400], 401: ERRORS[401], 404: ERRORS[404],
                   503: OpenApiResponse(DETAIL, description="Stripe недоступен или не настроен.")},
    ),
)


@extend_schema_view(post=extend_schema(
    description="Получить JWT access и refresh по username и password.",
    responses={200: inline_serializer("TokenPair", fields={
        "access": serializers.CharField(), "refresh": serializers.CharField(),
    }), 400: VALIDATION, 401: ERRORS[401]},
))
class LoginView(TokenObtainPairView):
    pass


@extend_schema_view(post=extend_schema(
    description="Обновить access по действительному refresh.",
    responses={200: inline_serializer("AccessToken", fields={"access": serializers.CharField()}),
               400: VALIDATION, 401: ERRORS[401]},
))
class RefreshView(TokenRefreshView):
    pass
