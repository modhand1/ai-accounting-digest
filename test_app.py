"""Небольшие проверки основных страниц и формы."""

import tempfile
import unittest
from pathlib import Path

import app as app_module


class SiteTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.REQUESTS_FILE = Path(self.temp_dir.name) / "requests.csv"
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_home_and_all_materials_open(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        for item in app_module.MATERIALS:
            response = self.client.get(f"/material/{item['slug']}")
            self.assertEqual(response.status_code, 200)

    def test_about_page_shows_verified_experience(self):
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn("20 лет", response.get_data(as_text=True))
        self.assertIn("about-practitioner-open.jpg", response.get_data(as_text=True))

    def test_unknown_material_returns_404(self):
        self.assertEqual(self.client.get("/material/net-takogo").status_code, 404)

    def test_health_and_security_headers(self):
        health_response = self.client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.get_json(), {"status": "ok"})

        home_response = self.client.get("/")
        self.assertEqual(
            home_response.headers["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertIn(
            "frame-ancestors 'self'",
            home_response.headers["Content-Security-Policy"],
        )

    def test_valid_request_is_saved(self):
        response = self.client.post(
            "/request",
            data={
                "name": "Тест",
                "task": "Повторяющаяся синтетическая задача для проверки формы.",
                "format": "Разбор одной задачи",
                "privacy": "yes",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(app_module.REQUESTS_FILE.exists())


if __name__ == "__main__":
    unittest.main()
