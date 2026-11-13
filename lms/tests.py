from django.contrib.auth.models import Group
from django.core.management import call_command
from rest_framework.test import APITestCase

from .models import Course, Lesson, User

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
