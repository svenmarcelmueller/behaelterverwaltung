"""Verwaltung: Behälter, Etiketten, Fächer, Einstellungen. Nur über Ingress registriert."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from markupsafe import Markup

from .. import etiketten, qr, repo
from ..db import hole_db

bp = Blueprint("verwaltung", __name__, template_folder="templates")

FILTER_NAMEN = {"alle": "Alle", "leer": "Leer", "belegt": "Belegt", "offen": "Etikett nicht gedruckt",
                "stillgelegt": "Stillgelegt"}
MAX_ETIKETTEN = 500


def _codes_aus(text: str | None) -> list[str]:
    return [c for c in (text or "").replace(" ", ",").split(",") if c][:MAX_ETIKETTEN]


def _zahl(text, standard: float = 0.0, minimum: float = -20, maximum: float = 20) -> float:
    try:
        wert = float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return standard
    return max(minimum, min(maximum, wert))


@bp.get("/")
def start():
    return redirect(url_for(".behaelter"))


# --- Behälter -------------------------------------------------------------


@bp.get("/behaelter")
def behaelter():
    conn = hole_db()
    filter = request.args.get("filter") if request.args.get("filter") in FILTER_NAMEN else "alle"
    return render_template(
        "verwaltung/behaelter.html",
        filter=filter,
        filter_namen=FILTER_NAMEN,
        anzahl=repo.behaelter_anzahl_je_filter(conn),
        liste=repo.behaelter_liste(conn, filter),
        neu=_codes_aus(request.args.get("neu")),
    )


@bp.post("/behaelter/anlegen")
def behaelter_anlegen():
    try:
        anzahl = int(request.form.get("anzahl", "1"))
        codes = repo.behaelter_anlegen(hole_db(), anzahl, request.form.get("bezeichnung"))
    except ValueError:
        flash("Bitte eine Anzahl zwischen 1 und 500 angeben.", "fehler")
        return redirect(url_for(".behaelter"), 303)
    except repo.Fehler as f:
        flash(f.meldung, "fehler")
        return redirect(url_for(".behaelter"), 303)
    flash(f"{len(codes)} Behälter angelegt.", "ok")
    return redirect(url_for(".behaelter", neu=",".join(codes)), 303)


@bp.post("/behaelter/auswahl")
def behaelter_auswahl():
    codes = request.form.getlist("codes")[:MAX_ETIKETTEN]
    if not codes:
        flash("Bitte zuerst Behälter auswählen.", "fehler")
        return redirect(url_for(".behaelter", filter=request.form.get("filter")), 303)

    if request.form.get("aktion") == "bezeichnung":
        neu = request.form.get("neue_bezeichnung", "").strip()
        anzahl = repo.bezeichnung_setzen(hole_db(), codes, neu)
        if neu:
            flash(f"Bezeichnung „{neu[:60]}“ für {anzahl} Behälter gesetzt.", "ok")
        else:
            flash(f"Bezeichnung bei {anzahl} Behältern entfernt.", "ok")
        return redirect(url_for(".behaelter", filter=request.form.get("filter")), 303)

    if request.form.get("aktion") == "stilllegen":
        erledigt, uebersprungen = repo.mehrere_stilllegen(hole_db(), codes)
        if erledigt:
            flash(f"{len(erledigt)} Behälter stillgelegt.", "ok")
        if uebersprungen:
            flash(f"{len(uebersprungen)} übersprungen, weil belegt oder schon stillgelegt: "
                  f"{', '.join(uebersprungen)}.", "fehler")
        return redirect(url_for(".behaelter", filter=request.form.get("filter")), 303)

    return redirect(url_for(".etiketten_seite", codes=",".join(codes)), 303)


# --- Etiketten ------------------------------------------------------------


def _gewaehltes_format(conn, format_id=None) -> dict:
    formate = repo.etikettenformate(conn)
    gesucht = format_id or repo.einstellung(conn, "etikettenformat")
    return next((f for f in formate if str(f["id"]) == str(gesucht)), formate[0])


@bp.get("/etiketten")
def etiketten_seite():
    conn = hole_db()
    fmt = _gewaehltes_format(conn, request.args.get("format"))
    r = etiketten.raster(fmt)

    auswahl = repo.aktive_codes(conn, _codes_aus(request.args.get("codes")))
    offen = repo.nicht_gedruckte_codes(conn)
    quelle = request.args.get("quelle") or ("auswahl" if auswahl else "offen")
    codes = auswahl if quelle == "auswahl" else offen
    auffuellen = request.args.get("auffuellen") == "1"
    start = etiketten.startplatz(request.args.get("start"), r)
    frei = etiketten.freie_plaetze(len(codes), r, start) if codes else r.pro_blatt - start

    # Vorschau: erstes Blatt mit schon abgezogenen, gedruckten, aufgefüllten und frei bleibenden Plätzen
    vorschau = []
    for i in range(r.pro_blatt):
        if i < start:
            art, code = "weg", ""
        elif i - start < len(codes):
            art, code = "druck", codes[i - start]
        else:
            art, code = ("neu" if auffuellen else "frei"), ""
        vorschau.append({"nummer": i + 1, "art": art, "code": code, "x": r.platz(i)[0], "y": r.platz(i)[1]})

    return render_template(
        "verwaltung/etiketten.html",
        formate=repo.etikettenformate(conn),
        fmt=fmt,
        r=r,
        a=etiketten.aufteilung(r.etikett_b, r.etikett_h),
        quelle=quelle,
        auswahl=auswahl,
        offen=offen,
        codes=codes,
        auffuellen=auffuellen,
        frei=frei,
        start=start,
        blaetter=max(1, etiketten.blattzahl(len(codes) + (frei if auffuellen else 0), r, start)) if r.passt else 0,
        vorschau=vorschau,
        basis_url=current_app.config["EINSTELLUNGEN"].basis_url,
    )


@bp.post("/etiketten/drucken")
def etiketten_drucken():
    """Füllt bei Bedarf das letzte Blatt mit neuen Behältern auf und öffnet die Druckseite."""
    conn = hole_db()
    fmt = _gewaehltes_format(conn, request.form.get("format"))
    codes = repo.aktive_codes(conn, _codes_aus(request.form.get("codes")))
    if not current_app.config["EINSTELLUNGEN"].basis_url:
        flash("Ohne Basis-URL können keine QR-Codes erzeugt werden.", "fehler")
        return redirect(url_for(".etiketten_seite", format=fmt["id"]), 303)

    r = etiketten.raster(fmt)
    start = etiketten.startplatz(request.form.get("start"), r)
    frei = etiketten.freie_plaetze(len(codes), r, start)
    if request.form.get("auffuellen") == "1":
        frei = frei if codes else r.pro_blatt - start
        if frei:
            codes += repo.behaelter_anlegen(conn, frei, request.form.get("bezeichnung") or None)
            flash(f"{frei} neue Behälter angelegt, um das Blatt zu füllen.", "ok")
    if not codes:
        flash("Keine Behälter zum Drucken ausgewählt.", "fehler")
        return redirect(url_for(".etiketten_seite", format=fmt["id"]), 303)

    repo.einstellung_setzen(conn, "etikettenformat", str(fmt["id"]))
    return redirect(url_for(".etiketten_blatt", format=fmt["id"], codes=",".join(codes),
                            start=start + 1 if start else None), 303)


@bp.get("/etiketten/blatt")
def etiketten_blatt():
    conn = hole_db()
    basis_url = current_app.config["EINSTELLUNGEN"].basis_url
    fmt = _gewaehltes_format(conn, request.args.get("format"))
    codes = repo.aktive_codes(conn, _codes_aus(request.args.get("codes")))
    r = etiketten.raster(fmt)
    a = etiketten.aufteilung(r.etikett_b, r.etikett_h)
    start = etiketten.startplatz(request.args.get("start"), r)

    blaetter = etiketten.seiten(codes, r, start)
    if basis_url:
        for blatt in blaetter:
            for platz in blatt:
                platz["qr"] = Markup(qr.svg(qr.behaelter_url(basis_url, platz["code"]), groesse_mm=a.qr_mm))

    return render_template(
        "verwaltung/blatt.html",
        fmt=fmt, r=r, a=a, blaetter=blaetter, codes=codes, basis_url=basis_url, start=start,
        versatz_x=_zahl(repo.einstellung(conn, "versatz_x_mm")),
        versatz_y=_zahl(repo.einstellung(conn, "versatz_y_mm")),
    )


@bp.post("/etiketten/gedruckt")
def etiketten_gedruckt():
    codes = repo.aktive_codes(hole_db(), _codes_aus(request.form.get("codes")))
    repo.als_gedruckt_markieren(hole_db(), codes)
    flash(f"{len(codes)} Etiketten als gedruckt markiert.", "ok")
    return redirect(url_for(".behaelter"), 303)


@bp.post("/etiketten/format")
def format_anlegen():
    fmt, fehler = etiketten.format_pruefen(request.form)
    if fehler:
        for f in fehler:
            flash(f, "fehler")
        return redirect(url_for(".etiketten_seite"), 303)
    neu = repo.etikettenformat_anlegen(hole_db(), fmt)
    flash(f"Etikettengröße „{fmt['name']}“ gespeichert.", "ok")
    return redirect(url_for(".etiketten_seite", format=neu), 303)


@bp.post("/etiketten/format/<int:format_id>/loeschen")
def format_loeschen(format_id):
    try:
        repo.etikettenformat_loeschen(hole_db(), format_id)
        flash("Etikettengröße gelöscht.", "ok")
    except repo.Fehler as f:
        flash(f.meldung, "fehler")
    return redirect(url_for(".etiketten_seite"), 303)


# --- Fächer ---------------------------------------------------------------


@bp.get("/faecher")
def faecher():
    return render_template("verwaltung/faecher.html", faecher=repo.faecher(hole_db()))


@bp.post("/faecher")
def fach_anlegen():
    try:
        repo.fach_anlegen(hole_db(), request.form.get("name", ""))
        flash("Fach angelegt.", "ok")
    except repo.Fehler as f:
        flash(f.meldung, "fehler")
    return redirect(url_for(".faecher"), 303)


@bp.post("/faecher/<int:fach_id>")
def fach_aendern(fach_id):
    conn = hole_db()
    aktion = request.form.get("aktion")
    try:
        if aktion == "hoch":
            repo.fach_verschieben(conn, fach_id, -1)
        elif aktion == "runter":
            repo.fach_verschieben(conn, fach_id, 1)
        elif aktion == "loeschen":
            repo.fach_loeschen(conn, fach_id)
            flash("Fach gelöscht.", "ok")
        else:
            repo.fach_umbenennen(conn, fach_id, request.form.get("name", ""))
            flash("Fach umbenannt.", "ok")
    except repo.Fehler as f:
        flash(f.meldung, "fehler")
    return redirect(url_for(".faecher"), 303)


# --- Einstellungen --------------------------------------------------------


@bp.get("/einstellungen")
def einstellungen():
    conn = hole_db()
    return render_template(
        "verwaltung/einstellungen.html",
        basis_url=current_app.config["EINSTELLUNGEN"].basis_url,
        versatz_x=_zahl(repo.einstellung(conn, "versatz_x_mm")),
        versatz_y=_zahl(repo.einstellung(conn, "versatz_y_mm")),
        anzahl=repo.behaelter_anzahl_je_filter(conn),
        ha=current_app.config["HA"],
    )


@bp.post("/einstellungen/sensoren")
def sensoren_senden():
    ha = current_app.config["HA"]
    if ha is None:
        flash("Keine Verbindung zu Home Assistant eingerichtet.", "fehler")
    elif ha.jetzt_senden():
        flash("Sensoren an Home Assistant gesendet.", "ok")
    else:
        flash(f"Senden fehlgeschlagen: {ha.letzter_fehler}", "fehler")
    return redirect(url_for(".einstellungen"), 303)


@bp.post("/einstellungen")
def einstellungen_speichern():
    conn = hole_db()
    repo.einstellung_setzen(conn, "versatz_x_mm", str(_zahl(request.form.get("versatz_x_mm"))))
    repo.einstellung_setzen(conn, "versatz_y_mm", str(_zahl(request.form.get("versatz_y_mm"))))
    flash("Druckversatz gespeichert.", "ok")
    return redirect(url_for(".einstellungen"), 303)


@bp.post("/einstellungen/zuruecksetzen")
def zuruecksetzen():
    if request.form.get("bestaetigung", "").strip().upper() != "LÖSCHEN":
        flash("Zum Zurücksetzen bitte LÖSCHEN eintippen.", "fehler")
        return redirect(url_for(".einstellungen"), 303)
    repo.daten_zuruecksetzen(hole_db())
    flash("Alle Behälter und Einlagerungen wurden gelöscht.", "ok")
    return redirect(url_for(".einstellungen"), 303)
