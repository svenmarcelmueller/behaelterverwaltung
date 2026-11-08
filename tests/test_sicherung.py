import io
import json

import pytest

from app import db, repo, sicherung
from app.config import Einstellungen
from app.csrf import COOKIE
from app.factory import create_app


def neue_app(ordner):
    ordner.mkdir()
    return create_app("ingress", Einstellungen(daten_ordner=ordner, dev=True, basis_url="http://192.168.1.10:8099"))


@pytest.fixture
def alt(tmp_path):
    """Eine benutzte App: eigene Fächer, Behälter mit Historie, eigene Größe, Druckversatz."""
    app = neue_app(tmp_path / "alt")
    conn = db.verbinden(app.config["DB_PFAD"])
    oben = repo.faecher(conn)[0]["id"]
    repo.fach_umbenennen(conn, oben, "Gefriertruhe oben")
    keller = repo.fach_anlegen(conn, "Keller")
    a, b, c = repo.behaelter_anlegen(conn, 3, "Box blau, groß")
    repo.einlagern(conn, a, "Erbsen", fach_id=oben, von="Sven")
    repo.ausbuchen(conn, a, von="Anna")
    repo.einlagern(conn, a, "Gulasch", beschreibung="2 Portionen", fach_id=keller)
    repo.als_gedruckt_markieren(conn, [a, b])
    repo.mehrere_stilllegen(conn, [c])
    repo.einstellung_setzen(conn, "versatz_x_mm", "1.5")
    repo.einstellung_setzen(conn, "letztes_fach", str(keller))
    yield app, conn, [a, b, c]
    conn.close()


@pytest.fixture
def neu(tmp_path):
    app = neue_app(tmp_path / "neu")
    conn = db.verbinden(app.config["DB_PFAD"])
    yield app, conn
    conn.close()


def alles(conn):
    """Kompletter Inhalt ohne den App-eigenen Schlüssel – zum Vergleichen."""
    return {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
            for t in sicherung.TABELLEN if t != "einstellung"} | {
        "einstellung": [dict(r) for r in conn.execute(
            "SELECT * FROM einstellung WHERE schluessel != 'secret_key' ORDER BY schluessel")]}


def test_umzug_uebernimmt_alles_unveraendert(alt, neu):
    _, conn_alt, (a, b, c) = alt
    _, conn_neu = neu
    daten = json.loads(json.dumps(sicherung.exportieren(conn_alt)))  # wie über die Datei

    anzahl = sicherung.importieren(conn_neu, daten)

    assert anzahl["behaelter"] == 3 and anzahl["einlagerung"] == 2
    assert alles(conn_neu) == alles(conn_alt)
    assert repo.behaelter_holen(conn_neu, a).einlagerung["inhalt_name"] == "Gulasch"
    assert [h["inhalt_name"] for h in repo.historie(conn_neu, a)] == ["Gulasch", "Erbsen"]
    assert repo.behaelter_holen(conn_neu, c).status == "stillgelegt"
    assert repo.einstellung(conn_neu, "versatz_x_mm") == "1.5"


def test_eigener_schluessel_wird_weder_exportiert_noch_ueberschrieben(alt, neu):
    _, conn_alt, _ = alt
    _, conn_neu = neu
    schluessel_neu = repo.einstellung(conn_neu, "secret_key")
    daten = sicherung.exportieren(conn_alt)
    assert "secret_key" not in json.dumps(daten)

    daten["tabellen"]["einstellung"].append({"schluessel": "secret_key", "wert": "von außen"})
    sicherung.importieren(conn_neu, daten)
    assert repo.einstellung(conn_neu, "secret_key") == schluessel_neu


def test_einspielen_nur_in_leere_app(alt, neu):
    _, conn_alt, _ = alt
    _, conn_neu = neu
    repo.behaelter_anlegen(conn_neu, 1)
    vorher = alles(conn_neu)
    with pytest.raises(sicherung.ImportFehler, match="noch keine Behälter"):
        sicherung.importieren(conn_neu, sicherung.exportieren(conn_alt))
    assert alles(conn_neu) == vorher


@pytest.mark.parametrize("kaputt, meldung", [
    (lambda d: {"irgendwas": 1}, "keine Exportdatei"),
    (lambda d: d | {"schema": [1]}, "anderem Datenbankaufbau"),
    (lambda d: d | {"tabellen": {"fach": []}}, "unvollständig"),
    (lambda d: _mit(d, "fach", {"name": "x", "id); DROP TABLE behaelter; --": 1}), "ungültige Einträge"),
    (lambda d: _mit(d, "einlagerung", {"behaelter_id": 999, "inhalt_name": "x", "eingelagert_am": "2026"}),
     "nichts eingespielt"),
])
def test_kaputte_datei_aendert_nichts(alt, neu, kaputt, meldung):
    _, conn_alt, _ = alt
    _, conn_neu = neu
    vorher = alles(conn_neu)
    with pytest.raises(sicherung.ImportFehler, match=meldung):
        sicherung.importieren(conn_neu, kaputt(sicherung.exportieren(conn_alt)))
    assert alles(conn_neu) == vorher  # auch Fächer und Größen noch wie neu installiert


def _mit(daten, tabelle, zeile):
    daten["tabellen"][tabelle].append(zeile)
    return daten


# --- über die Oberfläche --------------------------------------------------


def test_herunterladen_und_einspielen_ueber_die_seite(alt, neu):
    app_alt, conn_alt, (a, _, _) = alt
    app_neu, conn_neu = neu

    antwort = app_alt.test_client().get("/verwaltung/export")
    assert antwort.status_code == 200
    assert antwort.headers["Content-Disposition"].startswith('attachment; filename="behaelterverwaltung-')
    assert "Gulasch" in antwort.get_data(as_text=True)  # Umlaute lesbar, nicht als ä

    client = app_neu.test_client()
    seite = client.get("/verwaltung/einstellungen").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in seite
    token = client.get_cookie(COOKIE).value
    ergebnis = client.post("/verwaltung/import", data={
        "csrf": token, "datei": (io.BytesIO(antwort.get_data()), "export.json")})
    assert ergebnis.status_code == 303
    assert "Eingespielt: 3 Behälter, 2 Einlagerungen" in client.get(ergebnis.location).get_data(as_text=True)
    assert alles(conn_neu) == alles(conn_alt)

    # Danach ist Einspielen gesperrt
    seite = client.get("/verwaltung/einstellungen").get_data(as_text=True)
    assert "Nicht möglich, weil hier schon Behälter angelegt sind" in seite
    assert 'name="datei"' not in seite


def test_einspielen_falsche_datei_zeigt_meldung(neu):
    app_neu, conn_neu = neu
    client = app_neu.test_client()
    client.get("/verwaltung/einstellungen")
    token = client.get_cookie(COOKIE).value
    ergebnis = client.post("/verwaltung/import", data={"csrf": token, "datei": (io.BytesIO(b"\x89PNG"), "bild.png")})
    assert "keine Exportdatei" in client.get(ergebnis.location).get_data(as_text=True)


def test_einspielen_braucht_csrf(neu):
    app_neu, _ = neu
    antwort = app_neu.test_client().post("/verwaltung/import", data={"datei": (io.BytesIO(b"{}"), "x.json")})
    assert antwort.status_code == 400


def test_direktzugang_kennt_keinen_export(tmp_path):
    app = create_app("direkt", Einstellungen(daten_ordner=tmp_path, dev=False, basis_url=None))
    assert app.test_client().get("/verwaltung/export").status_code == 404
