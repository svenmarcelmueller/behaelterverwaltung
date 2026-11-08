import pytest

from app import db, repo
from app.config import Einstellungen
from app.csrf import COOKIE
from app.factory import create_app


@pytest.fixture
def app(tmp_path):
    return create_app("direkt", Einstellungen(daten_ordner=tmp_path, dev=False, basis_url=None))


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conn(app):
    verbindung = db.verbinden(app.config["DB_PFAD"])
    yield verbindung
    verbindung.close()


def token(client) -> str:
    client.get("/hilfe")
    return client.get_cookie(COOKIE).value


def senden(client, pfad, **daten):
    return client.post(pfad, data={"csrf": token(client), **daten})


def fach_id(conn, name):
    return next(f["id"] for f in repo.faecher(conn) if f["name"] == name)


# --- Scan-Seite -----------------------------------------------------------


def test_leerer_behaelter_zeigt_einlagern(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    text = client.get(f"/b/{code}").get_data(as_text=True)
    assert "Was legst du hinein?" in text
    assert code in text
    assert 'value="' + str(fach_id(conn, "Oben")) + '" checked' in text  # ohne Vorgeschichte: erstes Fach


def test_code_klein_geschrieben_wird_umgeleitet(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    antwort = client.get(f"/b/{code.lower()}")
    assert antwort.status_code == 302
    assert antwort.location.endswith(f"/b/{code}")


def test_unbekannter_code(client):
    antwort = client.get("/b/ZZZZZZ")
    assert antwort.status_code == 404
    assert "Diesen Behälter gibt es nicht" in antwort.get_data(as_text=True)


def test_stillgelegter_code(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.behaelter_stilllegen(conn, code)
    antwort = client.get(f"/b/{code}")
    assert antwort.status_code == 410
    assert "stillgelegt" in antwort.get_data(as_text=True)


def test_code_eingeben(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    antwort = client.get(f"/b?code=+{code.lower()}+")
    assert antwort.location.endswith(f"/b/{code}")


# --- Einlagern, Ausbuchen, Korrigieren -----------------------------------


def test_einlagern_ablauf(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    antwort = senden(client, f"/b/{code}/einlagern",
                     inhalt="Akkuschrauber-Bits", beschreibung="32-teilig", fach=fach_id(conn, "Mitte"), von="Anna")
    assert antwort.status_code == 303

    text = client.get(antwort.location).get_data(as_text=True)
    assert "Eingelagert." in text
    assert "Akkuschrauber-Bits" in text
    assert "Mitte" in text and "Anna" in text

    # nächster leerer Behälter schlägt das zuletzt genutzte Fach vor
    code2 = repo.behaelter_anlegen(conn)[0]
    text = client.get(f"/b/{code2}").get_data(as_text=True)
    assert 'value="' + str(fach_id(conn, "Mitte")) + '" checked' in text
    assert "Zuletzt genutzt: Mitte" in text


def test_einlagern_ohne_inhalt_zeigt_fehler_und_behaelt_eingaben(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    antwort = senden(client, f"/b/{code}/einlagern", inhalt=" ", beschreibung="nur Text")
    assert antwort.status_code == 409
    text = antwort.get_data(as_text=True)
    assert "Bitte angeben, was hineinkommt." in text
    assert "nur Text" in text


def test_doppel_tap_zeigt_verstaendliche_meldung(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    senden(client, f"/b/{code}/einlagern", inhalt="Kabel")
    antwort = senden(client, f"/b/{code}/einlagern", inhalt="Kabel")
    assert antwort.status_code == 409
    assert "In diesem Behälter liegt schon etwas" in antwort.get_data(as_text=True)


def test_ausbuchen(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    antwort = senden(client, f"/b/{code}/ausbuchen", von="Tom")
    assert antwort.status_code == 303
    text = client.get(antwort.location).get_data(as_text=True)
    assert "Ausgebucht." in text
    assert "Was legst du hinein?" in text
    assert repo.historie(conn, code)[0]["ausgelagert_von"] == "Tom"


def test_ausbuchen_leerer_behaelter(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    antwort = senden(client, f"/b/{code}/ausbuchen")
    assert antwort.status_code == 409
    assert "bereits leer" in antwort.get_data(as_text=True)


def test_korrigieren(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabl")
    assert "Eintrag korrigieren" in client.get(f"/b/{code}/korrigieren").get_data(as_text=True)
    antwort = senden(client, f"/b/{code}/korrigieren", inhalt="Kabel", beschreibung="", fach=fach_id(conn, "Unten"))
    assert antwort.status_code == 303
    e = repo.behaelter_holen(conn, code).einlagerung
    assert (e["inhalt_name"], e["fach_name"]) == ("Kabel", "Unten")


def test_korrigieren_mit_kaputtem_fach(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    antwort = senden(client, f"/b/{code}/korrigieren", inhalt="Kabel", fach="abc")
    assert antwort.status_code == 409


def test_historie(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel", von="Anna")
    repo.ausbuchen(conn, code, von="Tom")
    repo.einlagern(conn, code, "Handschuhe")
    text = client.get(f"/b/{code}/historie").get_data(as_text=True)
    assert text.index("Handschuhe") < text.index("Kabel")
    assert "von Tom" in text


def test_benutzereingaben_werden_escaped(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "<script>alert(1)</script>")
    text = client.get(f"/b/{code}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


# --- CSRF -----------------------------------------------------------------


def test_post_ohne_token_wird_abgelehnt(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    antwort = client.post(f"/b/{code}/einlagern", data={"inhalt": "Kabel"})
    assert antwort.status_code == 400
    assert repo.behaelter_holen(conn, code).status == "leer"


def test_post_mit_falschem_token_wird_abgelehnt(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    token(client)
    antwort = client.post(f"/b/{code}/einlagern", data={"inhalt": "Kabel", "csrf": "x" * 43})
    assert antwort.status_code == 400


# --- Übersicht ------------------------------------------------------------


@pytest.fixture
def bestand(conn):
    codes = repo.behaelter_anlegen(conn, anzahl=3)
    repo.einlagern(conn, codes[0], "Akkuschrauber-Bits", fach_id=fach_id(conn, "Mitte"))
    repo.einlagern(conn, codes[1], "Lichterketten", fach_id=fach_id(conn, "Oben"))
    return codes


def test_uebersicht(client, bestand):
    text = client.get("/").get_data(as_text=True)
    assert "Akkuschrauber-Bits" in text and "Lichterketten" in text
    assert "<strong>2</strong> belegt · <strong>1</strong> frei" in text


def test_uebersicht_ohne_behaelter(client):
    assert "Noch keine Behälter angelegt" in client.get("/").get_data(as_text=True)


def test_live_suche_liefert_nur_liste(client, bestand):
    antwort = client.get("/liste?q=akku", headers={"HX-Request": "true"})
    text = antwort.get_data(as_text=True)
    assert "<html" not in text
    assert "Akkuschrauber-Bits" in text
    assert "Lichterketten" not in text
    assert antwort.headers["HX-Push-Url"] == "/?q=akku"


def test_filter_fach_und_status(client, conn, bestand):
    text = client.get(f"/?fach={fach_id(conn, 'Oben')}").get_data(as_text=True)
    assert "Lichterketten" in text and "Akkuschrauber-Bits" not in text
    text = client.get("/liste?status=leer").get_data(as_text=True)
    assert bestand[2] in text and "Lichterketten" not in text


def test_filter_unsinnige_werte_werden_ignoriert(client, bestand):
    assert client.get("/?sort=DROP&status=x&fach=abc&von=kaputt").status_code == 200


def test_nichts_gefunden(client, bestand):
    assert "Nichts gefunden" in client.get("/liste?q=gibtsnicht").get_data(as_text=True)


def test_uebersicht_zeigt_bezeichnung_auch_bei_belegten(client, conn, bestand):
    repo.bezeichnung_setzen(conn, bestand[:1], "Box blau, groß")
    text = client.get("/").get_data(as_text=True)
    assert text.count('class="eintrag-behaelter"') == 1  # Lichterketten ohne Bezeichnung bleibt ohne
    assert "<span>Box blau, groß</span>" in text


def test_suche_findet_bezeichnung(client, conn, bestand):
    repo.bezeichnung_setzen(conn, bestand[1:2], "Eimer Grün")
    text = client.get("/liste?q=grün").get_data(as_text=True)
    assert "Lichterketten" in text and "Akkuschrauber-Bits" not in text


def test_hilfe(client):
    text = client.get("/hilfe").get_data(as_text=True)
    assert "Code-Scanner im Kontrollzentrum" in text
