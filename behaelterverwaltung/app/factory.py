"""Baut die Flask-App je Zugang.

- modus "ingress": Nutzung und Verwaltung, erreichbar über die HA-Seitenleiste.
- modus "direkt":  nur Nutzung, Port 8099, Ziel der QR-Codes.

Die Verwaltung wird im Direktmodus gar nicht registriert.
"""

from flask import Flask, abort, render_template, request

from . import __version__, csrf, db, filter
from .config import SUPERVISOR_IP, Einstellungen

MODI = ("ingress", "direkt")


class IngressPfad:
    """Übernimmt den Präfix aus X-Ingress-Path als SCRIPT_NAME, damit url_for() passende Links baut."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        pfad = environ.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if pfad.startswith("/"):
            environ["SCRIPT_NAME"] = pfad
        return self.wsgi_app(environ, start_response)


def create_app(modus: str, einstellungen: Einstellungen, ha=None) -> Flask:
    """ha: optionale HaSensoren-Instanz, wird nach jeder erfolgreichen Änderung angestoßen."""
    if modus not in MODI:
        raise ValueError(f"Unbekannter Modus: {modus}")

    app = Flask(__name__)
    app.config["MODUS"] = modus
    app.config["EINSTELLUNGEN"] = einstellungen
    app.config["HA"] = ha
    db.init_app(app, einstellungen.daten_ordner / "behaelter.db")
    app.secret_key = db.geheimer_schluessel(app.config["DB_PFAD"])  # für Flash-Meldungen
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    if modus == "ingress":
        app.wsgi_app = IngressPfad(app.wsgi_app)

        if not einstellungen.dev:
            @app.before_request
            def nur_supervisor():
                if request.remote_addr != SUPERVISOR_IP:
                    abort(403)

    csrf.init_app(app)
    filter.init_app(app)

    @app.context_processor
    def globale_werte():
        return {"version": __version__, "modus": modus}

    if ha is not None:
        @app.after_request
        def sensoren_aktualisieren(antwort):
            # Jede erfolgreiche Änderung (alle ändernden Aktionen sind POST) kann die Zahlen verschieben
            if request.method == "POST" and antwort.status_code < 400:
                ha.anstossen()
            return antwort

    @app.errorhandler(404)
    def nicht_gefunden(_fehler):
        return render_template("fehler_404.html"), 404

    from .nutzung.routes import bp as nutzung_bp
    app.register_blueprint(nutzung_bp)

    if modus == "ingress":
        from .verwaltung.routes import bp as verwaltung_bp
        app.register_blueprint(verwaltung_bp, url_prefix="/verwaltung")

    return app
