"""Browser-Tests mit dem installierten Edge (Playwright). Werden übersprungen, wenn beides fehlt.

Prüfen vor allem, dass Formulare im Hintergrund (htmx) gesendet werden – sonst warnt Safari
auf dem iPhone bei jeder Einlagerung über http vor einer „nicht sicheren Verbindung“.
"""

import socket
import threading

import pytest

from app import db, repo
from app.config import Einstellungen
from app.factory import create_app

playwright = pytest.importorskip("playwright.sync_api")


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge")
        except Exception as fehler:  # kein Edge installiert
            pytest.skip(f"Edge nicht verfügbar: {fehler}")
        yield b
        b.close()


@pytest.fixture
def server(tmp_path):
    from waitress import create_server

    app = create_app("direkt", Einstellungen(daten_ordner=tmp_path, dev=False, basis_url=None))
    port = _freier_port()
    srv = create_server(app, host="127.0.0.1", port=port, ident=None)
    threading.Thread(target=srv.run, daemon=True).start()
    conn = db.verbinden(app.config["DB_PFAD"])
    yield f"http://127.0.0.1:{port}", conn
    conn.close()
    srv.close()


@pytest.fixture
def seite(browser, server):
    basis, _ = server
    kontext = browser.new_context(viewport={"width": 390, "height": 844})
    kontext.add_init_script("localStorage.setItem('bv_name', 'Testperson')")
    page = kontext.new_page()
    page.dokument_anfragen = []
    page.on("request", lambda r: r.method == "POST" and page.dokument_anfragen.append(r.resource_type))
    yield page
    kontext.close()


def test_einlagern_im_hintergrund_mit_name(seite, server):
    basis, conn = server
    code = repo.behaelter_anlegen(conn)[0]
    seite.goto(f"{basis}/b/{code}")
    seite.fill("#inhalt", "Akkuschrauber-Bits")
    seite.click("text=Einlagern")
    seite.wait_for_selector("text=Eingelagert.")

    assert seite.dokument_anfragen == ["xhr"], "Formular wurde nicht im Hintergrund gesendet"
    assert seite.url == f"{basis}/b/{code}?ok=eingelagert"
    assert "Wird gespeichert als Testperson" in seite.inner_text("body")
    assert repo.behaelter_holen(conn, code).einlagerung["eingelagert_von"] == "Testperson"


def test_ausbuchen_mit_rueckfrage(seite, server):
    basis, conn = server
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    fragen = []
    seite.on("dialog", lambda d: (fragen.append(d.message), d.accept()))

    seite.goto(f"{basis}/b/{code}")
    seite.click("text=Entnommen – Behälter leeren")
    seite.wait_for_selector("text=Ausgebucht.")

    assert fragen == ["„Kabel“ entnommen und Behälter leeren?"]
    assert seite.dokument_anfragen == ["xhr"]
    assert repo.behaelter_holen(conn, code).einlagerung is None
    assert repo.historie(conn, code)[0]["ausgelagert_von"] == "Testperson"


def test_ausbuchen_abgebrochen(seite, server):
    basis, conn = server
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    seite.on("dialog", lambda d: d.dismiss())

    seite.goto(f"{basis}/b/{code}")
    seite.click("text=Entnommen – Behälter leeren")
    seite.wait_for_timeout(500)

    assert seite.dokument_anfragen == []
    assert repo.behaelter_holen(conn, code).status == "belegt"


def test_fehlermeldung_wird_angezeigt(seite, server):
    """Jemand anderes hat zwischenzeitlich eingelagert: 409 muss sichtbar werden, nicht verschluckt."""
    basis, conn = server
    code = repo.behaelter_anlegen(conn)[0]
    seite.goto(f"{basis}/b/{code}")
    repo.einlagern(conn, code, "Kabel")  # „gleichzeitig“ von einem anderen Gerät

    seite.fill("#inhalt", "Handschuhe")
    seite.click("text=Einlagern")
    seite.wait_for_selector("text=In diesem Behälter liegt schon etwas")


def test_bezeichnung_aendern_mit_enter(browser, tmp_path):
    from waitress import create_server

    app = create_app("ingress", Einstellungen(daten_ordner=tmp_path, dev=True, basis_url=None))
    port = _freier_port()
    srv = create_server(app, host="127.0.0.1", port=port, ident=None)
    threading.Thread(target=srv.run, daemon=True).start()
    conn = db.verbinden(app.config["DB_PFAD"])
    a, b = repo.behaelter_anlegen(conn, 2, "Box grau")
    repo.einlagern(conn, a, "Gemüse")

    kontext = browser.new_context(viewport={"width": 1280, "height": 900})
    page = kontext.new_page()
    page.goto(f"http://127.0.0.1:{port}/verwaltung/behaelter")
    knopf = page.locator("button[value=bezeichnung]")
    assert knopf.is_disabled()                       # ohne Auswahl gesperrt

    page.check(f"input[name=codes][value='{a}']")
    assert knopf.is_enabled()
    page.fill("#neue-bezeichnung", "Box blau, groß")
    page.press("#neue-bezeichnung", "Enter")         # darf NICHT „Etiketten drucken“ auslösen
    page.wait_for_selector("text=Bezeichnung „Box blau, groß“ für 1 Behälter gesetzt.")

    assert "/verwaltung/behaelter" in page.url
    assert repo.behaelter_holen(conn, a).bezeichnung == "Box blau, groß"
    assert repo.behaelter_holen(conn, a).einlagerung["inhalt_name"] == "Gemüse"
    assert repo.behaelter_holen(conn, b).bezeichnung == "Box grau"
    kontext.close()
    conn.close()
    srv.close()


def test_startplatz_per_antippen_in_der_vorschau(browser, tmp_path):
    from waitress import create_server

    app = create_app("ingress", Einstellungen(daten_ordner=tmp_path, dev=True, basis_url="http://x:8099"))
    port = _freier_port()
    srv = create_server(app, host="127.0.0.1", port=port, ident=None)
    threading.Thread(target=srv.run, daemon=True).start()
    conn = db.verbinden(app.config["DB_PFAD"])
    repo.behaelter_anlegen(conn, 2)

    kontext = browser.new_context(viewport={"width": 1280, "height": 900})
    page = kontext.new_page()
    page.goto(f"http://127.0.0.1:{port}/verwaltung/etiketten")
    page.click("[data-startplatz='10']")
    page.wait_for_selector("text=ab Platz 10, 9 schon abgezogen")

    assert page.input_value("#start") == "10"
    assert page.locator(".vorschau-weg").count() == 9
    assert "start=10" in page.url
    assert page.input_value("input[type=hidden][name=start]") == "10"
    kontext.close()
    conn.close()
    srv.close()


def test_platzhalter_inhalt(seite, server):
    basis, conn = server
    code = repo.behaelter_anlegen(conn)[0]
    seite.goto(f"{basis}/b/{code}")
    assert seite.get_attribute("#inhalt", "placeholder") == "z. B. Gemüse, Fleisch"


def test_name_festlegen(browser, server):
    basis, conn = server
    code = repo.behaelter_anlegen(conn)[0]
    kontext = browser.new_context(viewport={"width": 390, "height": 844})
    page = kontext.new_page()
    page.goto(f"{basis}/b/{code}")
    assert "Ohne Namen" in page.inner_text("footer")

    page.click("text=Name festlegen")
    page.fill("#name-eingabe", "Anna")
    page.click("#name-dialog >> text=Speichern")
    page.wait_for_selector("footer >> text=Wird gespeichert als Anna")  # Dialog schließt asynchron
    kontext.close()
