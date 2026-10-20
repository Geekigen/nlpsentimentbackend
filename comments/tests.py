from unittest.mock import patch

from openai import APIError

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from comments.models import AskQuota, Comment, Delivery, Driver
from comments.chat import ChartSpec, ChatBlock, ChatReply
from comments.queries import ranked_drivers, resolve_driver, score_to_stars
from comments.sentiment import (
    AspectScore,
    DriverAspects,
    DriverSentiment,
    SentimentUnavailable,
    analyze_driver_comment,
)


def sample_analysis() -> DriverSentiment:
    mentioned = AspectScore(rating="positive", note="Called ahead.")
    silent = AspectScore(rating="not_mentioned", note="")
    return DriverSentiment(
        sentiment="positive",
        score=0.7,
        summary="The driver was courteous and communicated well.",
        aspects=DriverAspects(
            punctuality=silent,
            courtesy=mentioned,
            package_care=silent,
            communication=mentioned,
            professionalism=mentioned,
        ),
        highlights=["called ahead"],
    )


class McpAdminLoginTests(TestCase):
    def test_active_admin_can_sign_in(self):
        from mcp_server import admin_login_ok

        User.objects.create_user("desk-admin", password="desk-secret", is_staff=True)
        self.assertTrue(admin_login_ok("desk-admin", "desk-secret"))

    def test_non_admin_and_wrong_password_are_rejected(self):
        from mcp_server import admin_login_ok

        User.objects.create_user("rider", password="desk-secret", is_staff=False)
        User.objects.create_user("desk-admin", password="desk-secret", is_staff=True)
        self.assertFalse(admin_login_ok("rider", "desk-secret"))
        self.assertFalse(admin_login_ok("desk-admin", "wrong-secret"))


class ScoreToStarsTests(SimpleTestCase):
    def test_buckets(self):
        self.assertEqual(score_to_stars(1), 5)
        self.assertEqual(score_to_stars(0.6), 5)
        self.assertEqual(score_to_stars(0.59), 4)
        self.assertEqual(score_to_stars(0.2), 4)
        self.assertEqual(score_to_stars(0.19), 3)
        self.assertEqual(score_to_stars(0), 3)
        self.assertEqual(score_to_stars(-0.2), 3)
        self.assertEqual(score_to_stars(-0.21), 2)
        self.assertEqual(score_to_stars(-0.6), 2)
        self.assertEqual(score_to_stars(-0.61), 1)
        self.assertEqual(score_to_stars(-1), 1)


class AnalyzeCommentTests(SimpleTestCase):
    def test_missing_api_key(self):
        with self.settings(OPENAI_API_KEY=""):
            with self.assertRaisesMessage(SentimentUnavailable, "API key error"):
                analyze_driver_comment("The driver was late.")

    @patch("comments.sentiment.OpenAI")
    def test_rejected_key_does_not_reveal_it(self, client):
        client.return_value.responses.parse.side_effect = APIError(
            "Incorrect API key provided: sk-secret-value.",
            request=None,
            body={"error": {"code": "invalid_api_key"}},
        )
        with self.settings(OPENAI_API_KEY="present"):
            with self.assertRaises(SentimentUnavailable) as raised:
                analyze_driver_comment("The driver was late.")
        self.assertEqual(str(raised.exception), "API key error")
        self.assertNotIn("sk-", str(raised.exception))


class ResolveDriverTests(TestCase):
    def setUp(self):
        self.driver = Driver.objects.create(name="Zawadi Tester", employee_code="DRV-901")

    def test_resolves_by_code_or_name(self):
        self.assertEqual(resolve_driver("drv-901"), self.driver)
        self.assertEqual(resolve_driver("zawadi"), self.driver)
        self.assertEqual(resolve_driver(str(self.driver.pk)), self.driver)


class SeedTests(TestCase):
    def test_seed_counts_and_links(self):
        codes = ["DRV-014", "DRV-027", "DRV-033", "DRV-041", "DRV-052"]
        self.assertEqual(Driver.objects.filter(employee_code__in=codes).count(), 5)
        self.assertEqual(Delivery.objects.count(), 50)
        self.assertEqual(Comment.objects.count(), 50)
        for comment in Comment.objects.select_related("delivery"):
            self.assertLessEqual(len(comment.body), 250)
            self.assertGreaterEqual(len(comment.body), 8)
            self.assertEqual(comment.driver_id, comment.delivery.driver_id)
            self.assertEqual(comment.stars, score_to_stars(comment.score))
            self.assertGreaterEqual(comment.stars, 1)
            self.assertLessEqual(comment.stars, 5)

    def test_rankings_follow_the_seed(self):
        response_codes = list(ranked_drivers().values_list("employee_code", flat=True))
        self.assertEqual(response_codes, ["DRV-014", "DRV-052", "DRV-033", "DRV-041", "DRV-027"])


@override_settings(KUTUMA_API_KEY="test-key", JWT_SECRET="test-jwt-secret", JWT_ACCESS_MINUTES=30)
class CommentApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.driver = Driver.objects.create(name="Test Driver", employee_code="DRV-900")
        self.other = Driver.objects.create(name="Other Driver", employee_code="DRV-899")
        self.delivery = Delivery.objects.create(driver=self.driver, reference="DEL-API-1")
        issued = self.client.post("/api/auth/token/", HTTP_X_API_KEY="test-key")
        self.assertEqual(issued.status_code, 200)
        self.assertNotIn("test-key", str(issued.data))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.data['access']}")

    def test_api_requires_a_jwt(self):
        self.client.credentials()
        response = self.client.get("/api/drivers/")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("test-key", str(response.data))

    def test_wrong_api_key_is_rejected_without_echoing_it(self):
        response = self.client.post("/api/auth/token/", HTTP_X_API_KEY="not-the-key")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "API key error")
        self.assertNotIn("not-the-key", str(response.data))

    def test_two_comments_per_ip_per_minute(self):
        payload = {
            "delivery": self.delivery.pk,
            "body": "The driver called ahead and was polite at the door.",
        }
        first = self.client.post("/api/comments/", payload, format="json", REMOTE_ADDR="203.0.113.10")
        second = self.client.post("/api/comments/", payload, format="json", REMOTE_ADDR="203.0.113.10")
        third = self.client.post("/api/comments/", payload, format="json", REMOTE_ADDR="203.0.113.10")
        other = self.client.post("/api/comments/", payload, format="json", REMOTE_ADDR="203.0.113.11")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.data["detail"], "Only 2 comments per IP per minute.")
        self.assertEqual(other.status_code, 201)

    def test_submit_waits_for_analyze(self):
        with patch("comments.services.analyze_driver_comment") as analysis:
            response = self.client.post(
                "/api/comments/",
                {
                    "driver": self.other.pk,
                    "delivery": self.delivery.pk,
                    "customer_name": "Wanjiru",
                    "order_reference": "ORD-9",
                    "body": "The driver called ahead and was polite at the door.",
                },
                format="json",
            )
            analysis.assert_not_called()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["analysis_status"], "submitted")
        self.assertIsNone(response.data["sentiment"])
        self.assertIsNone(response.data["stars"])
        self.assertEqual(response.data["driver"], self.driver.pk)
        self.assertEqual(response.data["delivery_reference"], "DEL-API-1")
        self.assertEqual(response.data["order_reference"], "")

        drivers = self.client.get("/api/drivers/")
        match = next(item for item in drivers.data if item["id"] == self.driver.pk)
        self.assertEqual(match["comment_count"], 0)
        self.assertIsNone(match["average_stars"])

    @patch("comments.services.analyze_driver_comment", return_value=sample_analysis())
    def test_analyze_stores_sentiment(self, _analysis):
        created = self.client.post(
            "/api/comments/",
            {
                "delivery": self.delivery.pk,
                "customer_name": "Wanjiru",
                "body": "The driver called ahead and was polite at the door.",
            },
            format="json",
        )
        response = self.client.post(f"/api/comments/{created.data['id']}/analyze/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["analysis_status"], "analyzed")
        self.assertEqual(response.data["sentiment"], "positive")
        self.assertEqual(response.data["score"], 0.7)
        self.assertEqual(response.data["stars"], 5)

        listed = self.client.get(f"/api/comments/?driver={self.driver.pk}")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

        drivers = self.client.get("/api/drivers/")
        match = next(item for item in drivers.data if item["id"] == self.driver.pk)
        self.assertEqual(match["comment_count"], 1)
        self.assertEqual(match["dominant_sentiment"], "positive")
        self.assertEqual(match["average_stars"], 5.0)

    def test_rejects_comment_over_250_characters(self):
        response = self.client.post(
            "/api/comments/",
            {"delivery": self.delivery.pk, "body": "x" * 251},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_comment_under_8_characters(self):
        response = self.client.post(
            "/api/comments/",
            {"delivery": self.delivery.pk, "body": "short"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delivery_list_is_filtered_by_driver(self):
        created = self.client.post(
            "/api/deliveries/",
            {"driver": self.driver.pk, "reference": "DEL-API-9"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        listed = self.client.get(f"/api/deliveries/?driver={self.driver.pk}")
        references = {item["reference"] for item in listed.data}
        self.assertIn("DEL-API-9", references)
        self.assertIn("DEL-API-1", references)
        other = self.client.get(f"/api/deliveries/?driver={self.other.pk}")
        self.assertEqual(other.data, [])

    def test_rankings_name_the_top_driver(self):
        response = self.client.get("/api/rankings/")
        self.assertEqual(response.status_code, 200)
        rankings = response.data["rankings"]
        self.assertGreaterEqual(len(rankings), 5)
        self.assertEqual(response.data["top_driver"]["employee_code"], "DRV-014")
        self.assertEqual(response.data["top_driver"], rankings[0])
        self.assertEqual(rankings[0]["rank"], 1)
        averages = [row["average_stars"] for row in rankings]
        self.assertEqual(averages, sorted(averages, reverse=True))
        codes = [row["employee_code"] for row in rankings]
        self.assertNotIn("DRV-900", codes)

    def test_driver_without_comments_sorts_last(self):
        hire = Driver.objects.create(name="Zed Hire", employee_code="DRV-998")
        response = self.client.get("/api/drivers/")
        self.assertEqual(response.data[-1]["id"], hire.pk)
        self.assertIsNone(response.data[-1]["average_stars"])


@override_settings(
    KUTUMA_API_KEY="test-key",
    JWT_SECRET="test-jwt-secret",
    JWT_ACCESS_MINUTES=30,
    OPENAI_API_KEY="test-openai-key",
    OPENAI_MODEL="gpt-4o-mini",
)
class AskAiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user("ask-admin", password="ask-secret", is_staff=True)
        self.staff_token = self.client.post(
            "/api/auth/admin/",
            {"username": "ask-admin", "password": "ask-secret"},
            format="json",
        ).data["access"]

    def staff(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.staff_token}")

    def test_staff_login_issues_a_staff_token(self):
        import jwt

        response = self.client.post(
            "/api/auth/admin/",
            {"username": "ask-admin", "password": "ask-secret"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = jwt.decode(response.data["access"], "test-jwt-secret", algorithms=["HS256"])
        self.assertEqual(payload["role"], "staff")
        self.assertEqual(payload["sub"], "ask-admin")
        self.assertEqual(response.data["asks_remaining"], 15)
        self.assertNotIn("ask-secret", response.content.decode())

    def test_non_admin_is_rejected_without_echoing_the_password(self):
        User.objects.create_user("rider", password="rider-secret", is_staff=False)
        response = self.client.post(
            "/api/auth/admin/",
            {"username": "rider", "password": "rider-secret"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Admin login failed.")
        self.assertNotIn("rider-secret", response.content.decode())

        wrong = self.client.post(
            "/api/auth/admin/",
            {"username": "ask-admin", "password": "wrong-secret"},
            format="json",
        )
        self.assertEqual(wrong.status_code, 401)
        self.assertNotIn("wrong-secret", wrong.content.decode())

    def test_api_key_token_cannot_ask(self):
        issued = self.client.post("/api/auth/token/", HTTP_X_API_KEY="test-key")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.data['access']}")
        response = self.client.post("/api/ask/", {"question": "Who leads?"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_question_length_is_limited(self):
        self.staff()
        empty = self.client.post("/api/ask/", {"question": "   "}, format="json")
        self.assertEqual(empty.status_code, 400)
        long = self.client.post("/api/ask/", {"question": "x" * 501}, format="json")
        self.assertEqual(long.status_code, 400)
        history = [{"role": "user", "content": "Who leads?"}] * 9
        oversized = self.client.post(
            "/api/ask/",
            {"question": "Who leads?", "history": history},
            format="json",
        )
        self.assertEqual(oversized.status_code, 400)

    @patch("comments.chat.OpenAI")
    def test_six_questions_per_ip(self, client):
        client.return_value.responses.parse.return_value.output_parsed = ChatReply(
            blocks=[ChatBlock(kind="text", text="Amina leads.")]
        )
        self.staff()
        for _ in range(6):
            response = self.client.post(
                "/api/ask/",
                {"question": "Who leads?"},
                format="json",
                REMOTE_ADDR="203.0.113.20",
            )
            self.assertEqual(response.status_code, 200)
        blocked = self.client.post(
            "/api/ask/",
            {"question": "Who leads?"},
            format="json",
            REMOTE_ADDR="203.0.113.20",
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.data["detail"], "Only 6 questions per IP per minute.")
        other = self.client.post(
            "/api/ask/",
            {"question": "Who leads?"},
            format="json",
            REMOTE_ADDR="203.0.113.21",
        )
        self.assertEqual(other.status_code, 200)

    @patch("comments.chat.OpenAI")
    def test_mocked_reply_returns_markdown_and_a_chart(self, client):
        client.return_value.responses.parse.return_value.output_parsed = ChatReply(
            blocks=[
                ChatBlock(kind="text", text="Amina leads on stars."),
                ChatBlock(
                    kind="markdown",
                    markdown="## Ratings\n\n- **Amina** leads.\n<script>alert(1)</script>",
                ),
                ChatBlock(
                    kind="chart",
                    chart=ChartSpec(title="Average stars", labels=["Amina", "Baraka"], values=[4.8, 4.2]),
                ),
            ]
        )
        self.staff()
        response = self.client.post("/api/ask/", {"question": "Write a short report."}, format="json")
        self.assertEqual(response.status_code, 200)
        kinds = [block["kind"] for block in response.data["blocks"]]
        self.assertEqual(kinds, ["text", "markdown", "chart"])
        markdown = response.data["blocks"][1]["markdown"]
        self.assertIn("**Amina**", markdown)
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("<", markdown)
        chart = response.data["blocks"][2]["chart"]
        self.assertEqual(chart["title"], "Average stars")
        self.assertEqual(chart["labels"], ["Amina", "Baraka"])
        self.assertEqual(chart["values"], [4.8, 4.2])
        self.assertEqual(response.data["asks_remaining"], 14)


@override_settings(JWT_SECRET="test-jwt-secret", OPENAI_API_KEY="test-openai-key", OPENAI_MODEL="gpt-4o-mini")
class AskQuotaTests(APITestCase):
    def setUp(self):
        cache.clear()

    def _token(self, username, password):
        response = self.client.post(
            "/api/auth/admin/",
            {"username": username, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response

    @patch("comments.chat.OpenAI")
    def test_staff_admin_stops_after_15_chats(self, client):
        client.return_value.responses.parse.return_value.output_parsed = ChatReply(
            blocks=[ChatBlock(kind="text", text="Amina leads.")]
        )
        User.objects.create_user("capped", password="capped-secret", is_staff=True)
        issued = self._token("capped", "capped-secret")
        self.assertEqual(issued.data["asks_remaining"], 15)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.data['access']}")
        AskQuota.objects.create(user=User.objects.get(username="capped"), used=14)
        allowed = self.client.post("/api/ask/", {"question": "Who leads?"}, format="json")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["asks_remaining"], 0)
        blocked = self.client.post("/api/ask/", {"question": "Who leads?"}, format="json")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.data["detail"], "Only 15 chat requests.")

    @patch("comments.chat.OpenAI")
    def test_superuser_is_not_capped(self, client):
        client.return_value.responses.parse.return_value.output_parsed = ChatReply(
            blocks=[ChatBlock(kind="text", text="Amina leads.")]
        )
        User.objects.create_superuser("root", "root@example.com", "root-secret")
        issued = self._token("root", "root-secret")
        self.assertIsNone(issued.data["asks_remaining"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.data['access']}")
        for _ in range(3):
            response = self.client.post("/api/ask/", {"question": "Who leads?"}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.data["asks_remaining"])
        self.assertFalse(AskQuota.objects.filter(user__username="root").exists())


class SuperuserCreatesAdminTests(TestCase):
    def test_superuser_creates_a_staff_admin(self):
        User.objects.create_superuser("root", "root@example.com", "root-secret")
        self.client.login(username="root", password="root-secret")
        response = self.client.post(
            "/admin/auth/user/add/",
            {
                "username": "desk-admin",
                "password1": "desk-secret-1",
                "password2": "desk-secret-1",
            },
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:500])
        created = User.objects.get(username="desk-admin")
        self.assertTrue(created.is_active)
        self.assertTrue(created.is_staff)
        self.assertFalse(created.is_superuser)

    def test_staff_admin_cannot_create_users(self):
        User.objects.create_user("desk-admin", password="desk-secret", is_staff=True)
        self.client.login(username="desk-admin", password="desk-secret")
        response = self.client.get("/admin/auth/user/add/")
        self.assertEqual(response.status_code, 403)
