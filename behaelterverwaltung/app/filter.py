"""Jinja-Filter für die Anzeige."""

from datetime import datetime

from flask import Flask


def _lesen(wert):
    if not wert:
        return None
    try:
        return datetime.fromisoformat(wert)
    except ValueError:
        return None


def datum(wert):
    """12.10.2026, 14:32"""
    zeit = _lesen(wert)
    return zeit.strftime("%d.%m.%Y, %H:%M") if zeit else "–"


def datum_kurz(wert):
    """12.10.2026"""
    zeit = _lesen(wert)
    return zeit.strftime("%d.%m.%Y") if zeit else "–"


def init_app(app: Flask) -> None:
    app.add_template_filter(datum)
    app.add_template_filter(datum_kurz)
