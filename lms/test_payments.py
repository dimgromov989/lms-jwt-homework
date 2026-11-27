import uuid
from decimal import Decimal
from unittest.mock import patch

import stripe
from django.test import override_settings
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema
from rest_framework.test import APITestCase

from .models import Course, Payment, User


@override_settings(STRIPE_SECRET_KEY="sk_test_mock", STRIPE_CURRENCY="usd")
class PaymentTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("seller", "seller@example.com")
        self.buyer = User.objects.create_user("buyer", "buyer@example.com")
        self.course = Course.objects.create(title="Python", price="125.49", owner=self.owner)
        self.client.force_authenticate(self.buyer)
        self.request_id = str(uuid.uuid4())
        self.payload = {"course": self.course.pk, "request_id": self.request_id}
        self.patcher = patch("lms.services.stripe.StripeClient")
        self.sdk = self.patcher.start().return_value
        self.addCleanup(self.patcher.stop)
        self.sdk.v1.products.create.return_value = stripe.Product(id="prod_test")
        self.sdk.v1.prices.create.return_value = stripe.Price(id="price_test")
        self.session = {
            "id": "cs_test", "url": "https://checkout.stripe.com/c/pay/test",
            "status": "open", "payment_status": "unpaid",
        }
        self.sdk.v1.checkout.sessions.create.return_value = stripe.checkout.Session.construct_from(self.session, "sk_test_mock")

    def create_payment(self):
        response = self.client.post("/api/payments/", self.payload)
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_checkout_parameters_persistence_and_repeated_request(self):
        response = self.create_payment()
        payment = Payment.objects.get()
        self.assertEqual(payment.user, self.buyer)
        self.assertEqual(payment.course, self.course)
        self.assertEqual(payment.amount, Decimal("125.49"))
        self.assertEqual(payment.stripe_product_id, "prod_test")
        self.assertEqual(payment.stripe_price_id, "price_test")
        self.assertEqual(payment.stripe_session_id, "cs_test")
        self.assertEqual(response.data["checkout_url"], self.session["url"])
        self.assertEqual(self.sdk.v1.products.create.call_args.args[0]["name"], "Python")
        price = self.sdk.v1.prices.create.call_args.args[0]
        self.assertEqual(price, {"product": "prod_test", "currency": "usd", "unit_amount": 12549})
        session = self.sdk.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(session["line_items"], [{"price": "price_test", "quantity": 1}])
        self.assertEqual(session["mode"], "payment")
        self.assertIn("{CHECKOUT_SESSION_ID}", session["success_url"])
        self.assertTrue(session["cancel_url"].startswith("http"))
        again = self.client.post("/api/payments/", self.payload)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["id"], response.data["id"])
        self.assertEqual(Payment.objects.count(), 1)
        self.sdk.v1.checkout.sessions.create.assert_called_once()
        self.assertEqual(self.client.get("/api/payments/").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/payments/{payment.pk}/").status_code, 200)

    def test_stripe_errors_preserve_completed_stages_and_allow_retry(self):
        for stage in ("products", "prices", "sessions"):
            with self.subTest(stage=stage):
                self.payload["request_id"] = str(uuid.uuid4())
                resource = self.sdk.v1.checkout.sessions if stage == "sessions" else getattr(self.sdk.v1, stage)
                resource.create.side_effect = stripe.APIConnectionError("private gateway information")
                response = self.client.post("/api/payments/", self.payload)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("private gateway", str(response.data))
                payment = Payment.objects.get(pk=response.data["payment_id"])
                self.assertEqual(payment.status, "failed")
                self.assertEqual(bool(payment.stripe_product_id), stage != "products")
                self.assertEqual(bool(payment.stripe_price_id), stage == "sessions")
                resource.create.side_effect = None
                retry = self.client.post("/api/payments/", self.payload)
                self.assertEqual(retry.status_code, 200, retry.data)
                payment.refresh_from_db()
                self.assertEqual(payment.status, "open")

    def test_status_sync_and_isolation(self):
        payment_id = self.create_payment().data["id"]
        url = f"/api/payments/{payment_id}/sync/"
        for status, paid in (("open", "unpaid"), ("complete", "paid"), ("expired", "unpaid"),
                             ("complete", "no_payment_required")):
            self.sdk.v1.checkout.sessions.retrieve.return_value.to_dict.return_value = {
                **self.session, "status": status, "payment_status": paid,
            }
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)
            payment = Payment.objects.get(pk=payment_id)
            self.assertEqual((payment.status, payment.payment_status), (status, paid))
        self.sdk.v1.checkout.sessions.retrieve.assert_called_with("cs_test")
        self.sdk.v1.checkout.sessions.retrieve.side_effect = stripe.InvalidRequestError("bad", "id")
        self.assertEqual(self.client.post(url).status_code, 503)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/payments/").data["count"], 0)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.get(f"/api/payments/{payment_id}/").status_code, 404)

    def test_validation_authentication_and_protected_records(self):
        self.assertEqual(self.client.post("/api/payments/", {}).status_code, 400)
        self.assertEqual(self.client.post("/api/payments/", {"course": 99999}).status_code, 400)
        free = Course.objects.create(title="Free", owner=self.owner)
        self.assertEqual(self.client.post("/api/payments/", {"course": free.pk}).status_code, 400)
        self.assertEqual(self.client.post("/api/payments/", {**self.payload, "request_id": "bad"}).status_code, 400)
        self.create_payment()
        self.assertEqual(self.client.delete(f"/api/users/{self.buyer.pk}/").status_code, 400)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.delete(f"/api/courses/{self.course.pk}/").status_code, 400)
        self.client.force_authenticate(None)
        for method, url in ((self.client.post, "/api/payments/"), (self.client.get, "/api/payments/"),
                            (self.client.get, "/api/payments/1/"), (self.client.post, "/api/payments/1/sync/")):
            self.assertEqual(method(url).status_code, 401)

    def test_missing_configuration_and_session(self):
        with override_settings(STRIPE_SECRET_KEY=""):
            self.assertEqual(self.client.post("/api/payments/", self.payload).status_code, 503)
        with override_settings(STRIPE_SUCCESS_URL="invalid"):
            self.assertEqual(self.client.post("/api/payments/", self.payload).status_code, 503)
        self.sdk.v1.products.create.side_effect = stripe.AuthenticationError("secret")
        payment_id = self.client.post("/api/payments/", self.payload).data["payment_id"]
        self.assertEqual(self.client.post(f"/api/payments/{payment_id}/sync/").status_code, 400)

    def test_request_id_cannot_be_reused_for_another_course(self):
        self.create_payment()
        other = Course.objects.create(title="Other", price=10, owner=self.owner)
        response = self.client.post("/api/payments/", {**self.payload, "course": other.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 1)


class DocumentationTests(APITestCase):
    def test_public_documentation_and_valid_schema(self):
        for url in ("/api/docs/", "/api/redoc/", "/api/schema/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
        schema = SchemaGenerator().get_schema(request=None, public=True)
        validate_schema(schema)
        for path in ("/api/lessons/", "/api/courses/", "/api/users/", "/api/token/",
                     "/api/token/refresh/", "/api/payments/", "/api/payments/{id}/sync/"):
            self.assertIn(path, schema["paths"])
        payment = schema["paths"]["/api/payments/"]["post"]
        self.assertIn("503", payment["responses"])
