import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

import pytest

from app import db, repo
from app.config import Einstellungen
from app.csrf import COOKIE
from app.factory import create_app
from app.ha import HaSensoren, http_sender, sensoren


@pytest.fixture
def pfad(tmp_path):
    p = tmp_path / "behaelter.db"
    db.migrieren(p)
    return p


@pytest.fixture
def conn(pfad):
    c = db.verbinden(pfad)
    yield c
    c.close()


class Aufzeichner:
    def __init__(self):
        self.gesendet = {}
        self.fehler = None

    def __call__(self, entity_id, daten):
        if self.fehler:
            raise self.fehler
        self.gesendet[entity_id] = daten


def test_sensoren_leer(conn):
    s = sensoren(conn)
    assert s["sensor.behaelter_frei"]["state"] == 0
    assert s["sensor.behaelter_belegt"]["state"] == 0
    assert s["sensor.behaelter_letzte_einlagerung"]["state"] == "–"
    assert s["sensor.behaelter_letzte_einlagerung"]["attributes"]["code"] is None


def test_sensoren_mit_bestand(conn):
    mitte = next(f["id"] for f in repo.faecher(conn) if f["name"] == "Mitte")
    a, b, c = repo.behaelter_anlegen(conn, 3)
    repo.einlagern(conn, a, "Kabel", fach_id=mitte)
    repo.einlagern(conn, b, "Akkuschrauber-Bits", fach_id=mitte, von="Anna")

    s = sensoren(conn)
    assert s["sensor.behaelter_frei"]["state"] == 1
    assert s["sensor.behaelter_belegt"]["state"] == 2
    assert s["sensor.behaelter_belegt"]["attributes"]["je_fach"] == {"Oben": 0, "Mitte": 2, "Unten": 0}
    letzte = s["sensor.behaelter_letzte_einlagerung"]
    assert letzte["state"] == "Akkuschrauber-Bits"
    assert letzte["attributes"]["code"] == b
    assert letzte["attributes"]["von"] == "Anna"
    assert letzte["attributes"]["fach"] == "Mitte"
    assert s["sensor.behaelter_frei"]["attributes"]["unit_of_measurement"] == "Behälter"


def test_jetzt_senden_erfolg_und_fehler(pfad):
    aufzeichner = Aufzeichner()
    ha = HaSensoren(pfad, aufzeichner)
    assert ha.jetzt_senden()
    assert set(aufzeichner.gesendet) == {"sensor.behaelter_frei", "sensor.behaelter_belegt",
                                         "sensor.behaelter_letzte_einlagerung"}
    assert ha.letzter_erfolg and ha.letzter_fehler is None

    aufzeichner.fehler = ConnectionError("HA nicht erreichbar")
    assert not ha.jetzt_senden()
    assert "HA nicht erreichbar" in ha.letzter_fehler

    aufzeichner.fehler = None
    assert ha.jetzt_senden()
    assert ha.letzter_fehler is None


def test_hintergrund_thread_sendet_nach_anstoss(pfad, conn):
    aufzeichner = Aufzeichner()
    ha = HaSensoren(pfad, aufzeichner)
    ha.starten()  # sendet einmal beim Start
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    ha.anstossen()
    for _ in range(50):
        if aufzeichner.gesendet.get("sensor.behaelter_belegt", {}).get("state") == 1:
            break
        threading.Event().wait(0.1)
    assert aufzeichner.gesendet["sensor.behaelter_belegt"]["state"] == 1


def test_post_stoesst_an_get_nicht(tmp_path):
    class Zaehler:
        anstoesse = 0

        def anstossen(self):
            self.anstoesse += 1

    zaehler = Zaehler()
    app = create_app("direkt", Einstellungen(daten_ordner=tmp_path, dev=False, basis_url=None), ha=zaehler)
    client = app.test_client()
    c = db.verbinden(app.config["DB_PFAD"])
    code = repo.behaelter_anlegen(c)[0]
    c.close()

    client.get("/")
    client.get(f"/b/{code}")
    assert zaehler.anstoesse == 0

    token = client.get_cookie(COOKIE).value
    client.post(f"/b/{code}/einlagern", data={"csrf": token, "inhalt": "Kabel"})
    assert zaehler.anstoesse == 1

    client.post(f"/b/{code}/einlagern", data={"csrf": token, "inhalt": "Kabel"})  # 409: nichts geändert
    assert zaehler.anstoesse == 1


def test_http_sender_spricht_ha_rest_api():
    """Echter HTTP-Aufruf gegen einen Mini-Server, der sich wie Home Assistant verhält."""
    empfangen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            laenge = int(self.headers["Content-Length"])
            empfangen.append((self.path, self.headers["Authorization"], json.loads(self.rfile.read(laenge))))
            self.send_response(201)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    senden = http_sender(f"http://127.0.0.1:{server.server_port}/api", "geheim")
    senden("sensor.behaelter_frei", {"state": 3, "attributes": {"friendly_name": "Behälter frei"}})
    server.server_close()

    assert empfangen == [("/api/states/sensor.behaelter_frei", "Bearer geheim",
                          {"state": 3, "attributes": {"friendly_name": "Behälter frei"}})]


def test_einstellungen_zeigt_status(tmp_path, pfad):
    ha = HaSensoren(pfad, Aufzeichner())
    app = create_app("ingress", Einstellungen(daten_ordner=tmp_path, dev=True, basis_url=None), ha=ha)
    client = app.test_client()
    assert "Zuletzt gesendet" in client.get("/verwaltung/einstellungen").get_data(as_text=True)

    token = client.get_cookie(COOKIE).value
    antwort = client.post("/verwaltung/einstellungen/sensoren", data={"csrf": token})
    assert "Sensoren an Home Assistant gesendet." in client.get(antwort.location).get_data(as_text=True)


def test_aus_umgebung(monkeypatch, pfad):
    for name in ("HA_URL", "HA_TOKEN", "SUPERVISOR_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert HaSensoren.aus_umgebung(pfad, dev=False) is None
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    assert HaSensoren.aus_umgebung(pfad, dev=False) is not None
    assert HaSensoren.aus_umgebung(pfad, dev=True) is None  # lokal nie den Supervisor ansprechen
    monkeypatch.setenv("HA_URL", "http://192.168.1.10:8123/api")
    monkeypatch.setenv("HA_TOKEN", "y")
    assert HaSensoren.aus_umgebung(pfad, dev=True) is not None
