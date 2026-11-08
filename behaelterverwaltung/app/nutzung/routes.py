"""Nutzung: Scan-Seite, Einlagern, Ausbuchen, Korrigieren, Historie, Übersicht, Hilfe.

Auf beiden Zugängen verfügbar (Port 8099 und Ingress).
"""

from flask import Blueprint, abort, make_response, redirect, render_template, request, url_for

from .. import repo
from ..db import hole_db

bp = Blueprint("nutzung", __name__, template_folder="templates")

SORTIER_NAMEN = {"neu": "Neueste zuerst", "alt": "Älteste zuerst", "name": "Name A–Z", "fach": "Nach Fach"}

MELDUNGEN = {
    "eingelagert": "Eingelagert.",
    "ausgebucht": "Ausgebucht. Der Behälter ist jetzt leer.",
    "korrigiert": "Änderungen gespeichert.",
}


def _von() -> str | None:
    return request.form.get("von", "").strip()[:40] or None


def _als_zahl(wert) -> int | None:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None


# --- Scan-Seite -----------------------------------------------------------


@bp.get("/b")
def code_eingeben():
    """Ziel des Formulars „Code eingeben“ auf der Hilfe-Seite."""
    code = repo.code_normalisieren(request.args.get("code", ""))
    if not code:
        return redirect(url_for(".hilfe"))
    return redirect(url_for(".behaelter", code=code))


def _behaelter_seite(code: str, fehler: str | None = None, werte: dict | None = None, status: int = 200):
    conn = hole_db()
    behaelter = repo.behaelter_holen(conn, code)
    if behaelter is None:
        return render_template("nutzung/unbekannt.html", code=repo.code_normalisieren(code)), 404
    if behaelter.status == "stillgelegt":
        return render_template("nutzung/stillgelegt.html", behaelter=behaelter), 410

    meldung = MELDUNGEN.get(request.args.get("ok", ""))
    if behaelter.status == "belegt":
        return render_template(
            "nutzung/belegt.html", behaelter=behaelter, meldung=meldung, fehler=fehler
        ), status

    faecher = repo.faecher(conn)
    werte = werte or {}
    gewaehlt = _als_zahl(werte.get("fach")) or repo.letztes_fach(conn) or (faecher[0]["id"] if faecher else None)
    return render_template(
        "nutzung/leer.html",
        behaelter=behaelter,
        faecher=faecher,
        gewaehlt=gewaehlt,
        letztes_fach=repo.letztes_fach(conn),
        werte=werte,
        meldung=meldung,
        fehler=fehler,
    ), status


@bp.get("/b/<code>")
def behaelter(code):
    if code != repo.code_normalisieren(code):
        return redirect(url_for(".behaelter", code=repo.code_normalisieren(code)))
    return _behaelter_seite(code)


@bp.post("/b/<code>/einlagern")
def einlagern(code):
    werte = {
        "inhalt": request.form.get("inhalt", ""),
        "beschreibung": request.form.get("beschreibung", ""),
        "fach": request.form.get("fach") or None,
    }
    try:
        repo.einlagern(hole_db(), code, werte["inhalt"], werte["beschreibung"], werte["fach"], _von())
    except repo.UnbekannterCode:
        abort(404)
    except repo.Fehler as f:
        return _behaelter_seite(code, fehler=f.meldung, werte=werte, status=409)
    return redirect(url_for(".behaelter", code=repo.code_normalisieren(code), ok="eingelagert"), 303)


@bp.post("/b/<code>/ausbuchen")
def ausbuchen(code):
    try:
        repo.ausbuchen(hole_db(), code, _von())
    except repo.UnbekannterCode:
        abort(404)
    except repo.Fehler as f:
        return _behaelter_seite(code, fehler=f.meldung, status=409)
    return redirect(url_for(".behaelter", code=repo.code_normalisieren(code), ok="ausgebucht"), 303)


@bp.route("/b/<code>/korrigieren", methods=["GET", "POST"])
def korrigieren(code):
    conn = hole_db()
    behaelter = repo.behaelter_holen(conn, code)
    if behaelter is None:
        abort(404)
    if behaelter.status != "belegt":
        return redirect(url_for(".behaelter", code=behaelter.code))

    fehler = None
    werte = {
        "inhalt": behaelter.einlagerung["inhalt_name"],
        "beschreibung": behaelter.einlagerung["beschreibung"] or "",
        "fach": behaelter.einlagerung["fach_id"],
    }
    if request.method == "POST":
        werte = {
            "inhalt": request.form.get("inhalt", ""),
            "beschreibung": request.form.get("beschreibung", ""),
            "fach": request.form.get("fach") or None,
        }
        try:
            repo.korrigieren(conn, code, werte["inhalt"], werte["beschreibung"], werte["fach"])
            return redirect(url_for(".behaelter", code=behaelter.code, ok="korrigiert"), 303)
        except repo.Fehler as f:
            fehler = f.meldung

    return render_template(
        "nutzung/korrigieren.html",
        behaelter=behaelter,
        faecher=repo.faecher(conn),
        werte=werte,
        gewaehlt=_als_zahl(werte["fach"]),
        fehler=fehler,
    ), (409 if fehler else 200)


@bp.get("/b/<code>/historie")
def historie(code):
    conn = hole_db()
    behaelter = repo.behaelter_holen(conn, code)
    if behaelter is None:
        abort(404)
    return render_template("nutzung/historie.html", behaelter=behaelter, eintraege=repo.historie(conn, code))


# --- Übersicht ------------------------------------------------------------


def _filter_aus_anfrage() -> dict:
    a = request.args
    status = a.get("status") if a.get("status") in ("belegt", "leer") else None
    sortierung = a.get("sort") if a.get("sort") in SORTIER_NAMEN else "neu"
    fach = a.get("fach", "")
    return {
        "q": a.get("q", "").strip()[:100],
        "fach": int(fach) if fach.isdigit() else None,
        "status": status,
        "von": a.get("von", "")[:10],
        "bis": a.get("bis", "")[:10],
        "sort": sortierung,
    }


def _treffer(f: dict) -> list[dict]:
    return repo.suchen(
        hole_db(), text=f["q"], fach_id=f["fach"], status=f["status"],
        von_datum=f["von"] or None, bis_datum=f["bis"] or None, sortierung=f["sort"],
    )


@bp.get("/")
def uebersicht():
    conn = hole_db()
    f = _filter_aus_anfrage()
    return render_template(
        "nutzung/uebersicht.html",
        f=f,
        treffer=_treffer(f),
        faecher=repo.faecher(conn),
        zahlen=repo.zaehlen(conn),
        letzte=repo.letzte_einlagerung(conn),
        sortier_namen=SORTIER_NAMEN,
    )


@bp.get("/liste")
def liste():
    """Nur die Trefferliste – für die Live-Suche per htmx."""
    f = _filter_aus_anfrage()
    antwort = make_response(render_template("nutzung/_liste.html", f=f, treffer=_treffer(f)))
    # Adresszeile zeigt die Übersicht mit den aktuellen Filtern, nicht /liste
    parameter = {k: v for k, v in request.args.items() if v and k in ("q", "fach", "status", "von", "bis", "sort")}
    antwort.headers["HX-Push-Url"] = url_for(".uebersicht", **parameter)
    return antwort


@bp.get("/hilfe")
def hilfe():
    return render_template("nutzung/hilfe.html")
