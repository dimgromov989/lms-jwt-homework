"""Stripe operations return JSON-compatible dictionaries."""

import stripe
from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from rest_framework.exceptions import APIException


class StripeUnavailable(APIException):
    status_code = 503
    default_detail = "Сервис оплаты временно недоступен. Повторите запрос с тем же request_id."


def stripe_client():
    if not settings.STRIPE_SECRET_KEY:
        raise StripeUnavailable("Оплата не настроена. Обратитесь к администратору.")
    try:
        validator = URLValidator(schemes=["http", "https"])
        validator(settings.STRIPE_SUCCESS_URL)
        validator(settings.STRIPE_CANCEL_URL)
    except ValidationError as error:
        raise StripeUnavailable("Администратор должен настроить URL возврата после оплаты.") from error
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=2)


def create_product(client, payment):
    return client.v1.products.create(
        {"name": payment.product_name, "metadata": {"payment_id": str(payment.pk)}},
        options={"idempotency_key": f"lms-{payment.user_id}-{payment.request_id}-product"},
    ).to_dict(for_json=True)


def create_price(client, payment):
    return client.v1.prices.create(
        {"product": payment.stripe_product_id, "currency": payment.currency,
         "unit_amount": int(payment.amount * 100)},
        options={"idempotency_key": f"lms-{payment.user_id}-{payment.request_id}-price"},
    ).to_dict(for_json=True)


def create_session(client, payment):
    return client.v1.checkout.sessions.create(
        {"mode": "payment", "line_items": [{"price": payment.stripe_price_id, "quantity": 1}],
         "success_url": payment.success_url, "cancel_url": payment.cancel_url,
         "client_reference_id": str(payment.pk), "metadata": {"payment_id": str(payment.pk)}},
        options={"idempotency_key": f"lms-{payment.user_id}-{payment.request_id}-session"},
    ).to_dict(for_json=True)


def retrieve_session(client, payment):
    return client.v1.checkout.sessions.retrieve(payment.stripe_session_id).to_dict(for_json=True)


def start_checkout(client, payment):
    if not payment.stripe_product_id:
        payment.stripe_product_id = create_product(client, payment)["id"]
        payment.save(update_fields=["stripe_product_id"])
    if not payment.stripe_price_id:
        payment.stripe_price_id = create_price(client, payment)["id"]
        payment.save(update_fields=["stripe_price_id"])
    if not payment.stripe_session_id:
        session = create_session(client, payment)
        payment.stripe_session_id = session["id"]
        payment.checkout_url = session["url"]
        payment.status = session["status"]
        payment.payment_status = session["payment_status"]
        payment.save(update_fields=["stripe_session_id", "checkout_url", "status", "payment_status"])
