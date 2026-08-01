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
        home_response = self.client.get("/")
        self.assertEqual(home_response.status_code, 200)
        home_html = home_response.get_data(as_text=True)
        self.assertIn(
            "коммерческую или иную охраняемую тайну",
            home_html,
        )
        self.assertIn("Какую проблему хотите решить?", home_html)
        self.assertNotIn('name="name"', home_html)
        for item in app_module.MATERIALS:
            response = self.client.get(f"/material/{item['slug']}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Морозова Юлия", response.get_data(as_text=True))

    def test_about_page_shows_verified_experience(self):
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn("20 лет", response.get_data(as_text=True))
        self.assertIn("about-practitioner-open.jpg", response.get_data(as_text=True))

    def test_material_catalog_has_ten_unique_items(self):
        numbers = [item["number"] for item in app_module.MATERIALS]
        slugs = [item["slug"] for item in app_module.MATERIALS]

        self.assertEqual(len(app_module.MATERIALS), 10)
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(numbers, [f"{number:02d}" for number in range(1, 11)])

    def test_material_ten_opens(self):
        material_ten = next(
            item for item in app_module.MATERIALS if item["number"] == "10"
        )
        response = self.client.get(f"/material/{material_ten['slug']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Как задать ИИ границы",
            response.get_data(as_text=True),
        )

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
                "problem": "Каждый месяц долго ищу расхождения между отчётами.",
                "current_process": "Вручную открываю две таблицы и сравниваю строки.",
                "desired_result": "Получить понятный порядок проверки расхождений.",
                "data_used": "Две обезличенные таблицы и итоговый отчёт.",
                "frequency": "Раз в месяц",
                "current_check": "Сверяю итоговые суммы и несколько строк выборочно.",
                "privacy": "yes",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(app_module.REQUESTS_FILE.exists())
        saved_text = app_module.REQUESTS_FILE.read_text(encoding="utf-8-sig")
        self.assertIn("Проблема", saved_text)
        self.assertNotIn("Имя", saved_text)


if __name__ == "__main__":
    unittest.main()
