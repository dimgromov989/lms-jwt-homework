from django.contrib.auth.models import Group
from django.core.management import call_command
from rest_framework.test import APITestCase

from .models import Course, Lesson, Subscription, User

PASSWORD = "Practice!River923"


class ApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loaddata", "moderators", verbosity=0)
        cls.owner = User.objects.create_user("owner", "owner@example.com", PASSWORD, last_name="Private")
        cls.other = User.objects.create_user("other", "other@example.com", PASSWORD)
        cls.mod = User.objects.create_user("mod", "mod@example.com", PASSWORD)
        cls.mod.groups.add(Group.objects.get(name="Moderators"))
        cls.course = Course.objects.create(title="Course", owner=cls.owner)
        cls.lesson = Lesson.objects.create(title="Lesson", course=cls.course, owner=cls.owner)

    def test_registration_and_jwt(self):
        self.assertEqual(self.client.get("/api/courses/").status_code, 401)
        self.assertEqual(self.client.get("/api/users/").status_code, 401)
        data = {"username": "new", "email": "new@example.com", "password": PASSWORD}
        response = self.client.post("/api/users/", data)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("password", response.data)
        self.assertEqual(self.client.post("/api/users/", {**data, "username": "alt", "email": "NEW@example.com"}).status_code, 400)
        self.assertEqual(self.client.post("/api/users/", {**data, "email": "alt@example.com"}).status_code, 400)
        self.assertEqual(self.client.post("/api/token/", {"username": "new", "password": "wrong"}).status_code, 401)
        tokens = self.client.post("/api/token/", {"username": "new", "password": PASSWORD}).data
        refreshed = self.client.post("/api/token/refresh/", {"refresh": tokens["refresh"]})
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        self.assertEqual(self.client.get("/api/courses/").status_code, 200)

    def test_profile_privacy_and_ownership(self):
        self.client.force_authenticate(self.other)
        foreign = f"/api/users/{self.owner.pk}/"
        self.assertEqual(set(self.client.get(foreign).data), {"id", "username", "first_name"})
        self.assertEqual(self.client.patch(foreign, {"first_name": "No"}).status_code, 403)
        self.assertEqual(self.client.delete(foreign).status_code, 403)
        own = f"/api/users/{self.other.pk}/"
        response = self.client.patch(own, {"last_name": "Updated", "password": "Longer!Green207"})
        self.assertEqual(response.status_code, 200)
        self.other.refresh_from_db()
        self.assertTrue(self.other.check_password("Longer!Green207"))
        self.assertEqual(self.client.delete(own).status_code, 204)

    def test_course_and_lesson_permissions(self):
        for endpoint, item, payload in [
            ("courses", self.course, {"title": "New"}),
            ("lessons", self.lesson, {"title": "New", "course": self.course.pk}),
        ]:
            collection = f"/api/{endpoint}/"
            detail = f"{collection}{item.pk}/"
            with self.subTest(endpoint=endpoint):
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.get(collection).data["count"], 0)
                for method in (self.client.get, self.client.put, self.client.patch, self.client.delete):
                    self.assertEqual(method(detail).status_code, 404)
                self.client.force_authenticate(self.mod)
                self.assertEqual(self.client.get(collection).data["count"], 1)
                self.assertEqual(self.client.get(detail).status_code, 200)
                self.assertEqual(self.client.put(detail, payload).status_code, 200)
                self.assertEqual(self.client.patch(detail, {"title": "Moderated"}).status_code, 200)
                self.assertEqual(self.client.post(collection, payload).status_code, 403)
                self.assertEqual(self.client.delete(detail).status_code, 403)
                self.client.force_authenticate(self.owner)
                response = self.client.post(collection, {**payload, "owner": self.other.pk})
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["owner"], self.owner.pk)
                self.assertEqual(self.client.delete(f"{collection}{response.data['id']}/").status_code, 204)

    def test_cannot_attach_lesson_to_foreign_course(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post("/api/lessons/", {
            "title": "Foreign", "course": self.course.pk,
        }).status_code, 400)


class MaterialTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("alice", "alice@example.com")
        self.other = User.objects.create_user("bob", "bob@example.com")
        self.moderator = User.objects.create_user("mod", "moderator@example.com")
        self.moderator.groups.add(Group.objects.create(name="Moderators"))
        self.course = Course.objects.create(title="Python", owner=self.owner)
        self.lesson = Lesson.objects.create(title="Введение", course=self.course, owner=self.owner)
        self.course_url = f"/api/courses/{self.course.pk}/"
        self.lesson_url = f"/api/lessons/{self.lesson.pk}/"
        self.subscription_url = f"{self.course_url}subscription/"

    def test_owner_can_create_read_update_and_delete_lesson(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post("/api/lessons/", {
            "title": "Функции", "course": self.course.pk,
            "description": "Видео: https://www.youtube.com/watch?v=123",
        })
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/lessons/{response.data['id']}/"
        self.assertEqual(self.client.get(url).data["owner"], self.owner.pk)
        self.assertEqual(self.client.patch(url, {"title": "Функции Python"}).status_code, 200)
        self.assertEqual(self.client.get(url).data["title"], "Функции Python")
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_validator_checks_both_fields_on_both_resources(self):
        self.client.force_authenticate(self.owner)
        for url in (self.course_url, self.lesson_url):
            for field, link in (
                ("title", "https://other.example/video"),
                ("description", "https://youtube.com.evil.org/video"),
                ("description", "https://youtube.com@evil.org/video"),
                ("description", "Текст [ссылка](//evil.org/video)"),
                ("description", "example.org/video"),
                ("description", "https://[invalid"),
                ("description", "https://youtube.com/watch?v=1 https://evil.org"),
            ):
                with self.subTest(url=url, field=field, link=link):
                    response = self.client.patch(url, {field: link})
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn("youtube.com", str(response.data[field]))
            response = self.client.patch(url, {"description": "(https://WWW.YOUTUBE.COM/watch?v=123)"})
            self.assertEqual(response.status_code, 200, response.data)

    def test_subscription_lifecycle_and_scope(self):
        self.client.force_authenticate(self.owner)
        self.assertFalse(self.client.get(self.course_url).data["is_subscribed"])
        self.assertEqual(self.client.post(self.subscription_url).status_code, 201)
        self.assertEqual(self.client.post(self.subscription_url).status_code, 200)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertTrue(self.client.get(self.course_url).data["is_subscribed"])
        self.assertTrue(self.client.get("/api/courses/").data["results"][0]["is_subscribed"])

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.course_url).status_code, 404)
        self.assertEqual(self.client.delete(self.subscription_url).status_code, 404)
        self.assertEqual(self.client.post(self.subscription_url).status_code, 201)
        self.assertEqual(Subscription.objects.count(), 2)
        self.assertEqual(self.client.post("/api/courses/99999/subscription/").status_code, 404)

        self.client.force_authenticate(self.moderator)
        self.assertFalse(self.client.get(self.course_url).data["is_subscribed"])
        self.assertEqual(self.client.post(self.subscription_url).status_code, 201)
        self.assertTrue(self.client.get(self.course_url).data["is_subscribed"])

        self.client.force_authenticate(self.owner)
        response = self.client.delete(self.subscription_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_subscribed"])
        self.assertFalse(self.client.get(self.course_url).data["is_subscribed"])
        self.assertEqual(Subscription.objects.count(), 2)

    def test_guest_cannot_access_materials_or_subscriptions(self):
        for url in ("/api/courses/", "/api/lessons/"):
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.post(self.subscription_url).status_code, 401)
        self.assertEqual(self.client.delete(self.subscription_url).status_code, 401)

    def test_pagination_for_both_lists(self):
        Course.objects.bulk_create([Course(title=f"Курс {n}", owner=self.owner) for n in range(54)])
        Lesson.objects.bulk_create([
            Lesson(title=f"Урок {n}", owner=self.owner, course=self.course) for n in range(54)
        ])
        self.client.force_authenticate(self.owner)
        for endpoint in ("courses", "lessons"):
            url = f"/api/{endpoint}/"
            with self.subTest(endpoint=endpoint):
                first = self.client.get(url).data
                second = self.client.get(url, {"page": 2, "page_size": 10}).data
                self.assertEqual(first["count"], 55)
                self.assertEqual(len(first["results"]), 10)
                self.assertGreater(second["results"][0]["id"], first["results"][-1]["id"])
                self.assertEqual(len(self.client.get(url, {"page_size": 100}).data["results"]), 50)
                self.assertEqual(self.client.get(url, {"page": 100}).status_code, 404)
