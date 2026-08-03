"""Небольшой сайт-дайджест на Flask.

Запуск:
    python app.py
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from content import MATERIALS


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 30

BASE_DIR = Path(__file__).resolve().parent
REQUESTS_FILE = Path(
    os.environ.get("REQUESTS_FILE", BASE_DIR / "data" / "requests.csv")
)


def safe_csv_cell(value: str) -> str:
    """Не позволяет пользовательскому тексту стать формулой в таблице."""
    formula_prefixes = ("=", "+", "-", "@", "\t", "\r")
    if value.lstrip().startswith(formula_prefixes):
        return "'" + value
    return value


@app.after_request
def add_security_headers(response):
    """Добавляет базовые защитные заголовки ко всем ответам сайта."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'; "
        "font-src 'self'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'"
    )
    return response


@app.get("/")
def home():
    """Главная страница с материалами и формой заявки."""
    return render_template(
        "index.html",
        materials=MATERIALS,
        sent=request.args.get("sent") == "1",
        error=request.args.get("error"),
    )


@app.get("/health")
def health():
    """Небольшая проверка доступности для хостинга."""
    return jsonify(status="ok")


@app.get("/about")
def about():
    """Страница об авторе проекта и профессиональном подходе."""
    return render_template("about.html")


@app.get("/material/<slug>")
def material(slug: str):
    """Страница отдельного материала."""
    current = next((item for item in MATERIALS if item["slug"] == slug), None)
    if current is None:
        abort(404)

    current_index = MATERIALS.index(current)
    next_material = MATERIALS[(current_index + 1) % len(MATERIALS)]
    return render_template(
        "material.html",
        material=current,
        next_material=next_material,
        total_materials=len(MATERIALS),
    )


@app.post("/request")
def save_request():
    """Проверяет и сохраняет обезличенное описание рабочей задачи."""
    problem = request.form.get("problem", "").strip()
    current_process = request.form.get("current_process", "").strip()
    desired_result = request.form.get("desired_result", "").strip()
    data_used = request.form.get("data_used", "").strip()
    frequency = request.form.get("frequency", "").strip()
    current_check = request.form.get("current_check", "").strip()
    privacy_confirmed = request.form.get("privacy") == "yes"

    allowed_frequencies = {
        "Каждый день",
        "Несколько раз в неделю",
        "Раз в месяц",
        "Раз в квартал",
        "Реже или по событию",
    }

    if (
        not 15 <= len(problem) <= 900
        or not 15 <= len(current_process) <= 1200
        or not 10 <= len(desired_result) <= 900
        or not 5 <= len(data_used) <= 900
        or frequency not in allowed_frequencies
        or not 5 <= len(current_check) <= 900
        or not privacy_confirmed
    ):
        return redirect(url_for("home", error="Проверьте поля формы") + "#contact")

    REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = REQUESTS_FILE.exists()

    with REQUESTS_FILE.open("a", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow(
                [
                    "Дата",
                    "Проблема",
                    "Текущий способ",
                    "Желаемый результат",
                    "Виды данных",
                    "Периодичность",
                    "Способ проверки",
                ]
            )
        writer.writerow(
            [
                datetime.now().isoformat(timespec="minutes"),
                safe_csv_cell(problem),
                safe_csv_cell(current_process),
                safe_csv_cell(desired_result),
                safe_csv_cell(data_used),
                safe_csv_cell(frequency),
                safe_csv_cell(current_check),
            ]
        )

    return redirect(url_for("home", sent="1") + "#contact")


@app.errorhandler(404)
def page_not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
