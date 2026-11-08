"""CSRF-Schutz ohne Login und ohne Sitzungen (Double-Submit-Cookie).

Jeder Browser bekommt ein zufälliges Token als Cookie; jedes Formular schickt
es als verstecktes Feld mit. Eine fremde Seite kann das Cookie nicht lesen und
deshalb kein gültiges Formular abschicken.
"""

import hmac
import secrets

from flask import Flask, g, render_template, request

COOKIE = "bv_csrf"
FELD = "csrf"


def _token() -> str:
    if "csrf_token" not in g:
        vorhanden = request.cookies.get(COOKIE, "")
        g.csrf_token = vorhanden if len(vorhanden) == 43 else secrets.token_urlsafe(32)
    return g.csrf_token


def init_app(app: Flask) -> None:
    app.jinja_env.globals["csrf_token"] = _token

    @app.before_request
    def pruefen():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        cookie = request.cookies.get(COOKIE, "")
        formular = request.form.get(FELD, "")
        if not cookie or not hmac.compare_digest(cookie, formular):
            return render_template("fehler_csrf.html"), 400
        return None

    @app.after_request
    def cookie_setzen(antwort):
        token = _token()
        if request.cookies.get(COOKIE) != token:
            antwort.set_cookie(
                COOKIE, token, max_age=60 * 60 * 24 * 365, samesite="Lax",
                httponly=True, path=request.script_root or "/",
            )
        return antwort
