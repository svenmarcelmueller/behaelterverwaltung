import re
from pathlib import Path

import pytest

from app import __version__
from app.config import Einstellungen
from app.factory import create_app

PROJEKT = Path(__file__).resolve().parent.parent / "behaelterverwaltung"


@pytest.fixture
def einstellungen(tmp_path):
    return Einstellungen(daten_ordner=tmp_path, dev=False, basis_url=None)


def test_version_passt_zu_config_yaml():
    text = (PROJEKT / "config.yaml").read_text(encoding="utf-8")
    assert re.search(r'^version:\s*"([^"]+)"', text, re.M).group(1) == __version__


def test_direktzugang_zeigt_uebersicht_ohne_verwaltung(einstellungen):
    client = create_app("direkt", einstellungen).test_client()
    antwort = client.get("/")
    assert antwort.status_code == 200
    text = antwort.get_data(as_text=True)
    assert "Schrank" in text
    assert "/verwaltung/" not in text


def test_direktzugang_kennt_keine_verwaltung(einstellungen):
    client = create_app("direkt", einstellungen).test_client()
    assert client.get("/verwaltung/").status_code == 404


def test_ingress_nur_vom_supervisor(einstellungen):
    client = create_app("ingress", einstellungen).test_client()
    assert client.get("/", environ_base={"REMOTE_ADDR": "192.168.1.50"}).status_code == 403
    assert client.get("/", environ_base={"REMOTE_ADDR": "172.30.32.2"}).status_code == 200


def test_ingress_links_mit_ingress_pfad(einstellungen):
    client = create_app("ingress", einstellungen).test_client()
    antwort = client.get(
        "/",
        headers={"X-Ingress-Path": "/api/hassio_ingress/abc123"},
        environ_base={"REMOTE_ADDR": "172.30.32.2"},
    )
    text = antwort.get_data(as_text=True)
    assert 'href="/api/hassio_ingress/abc123/verwaltung/"' in text
    assert "/api/hassio_ingress/abc123/static/app.css" in text
    assert "/api/hassio_ingress/abc123/static/vendor/htmx.min.js" in text


def test_ingress_im_dev_modus_ohne_ip_pruefung(tmp_path):
    dev = Einstellungen(daten_ordner=tmp_path, dev=True, basis_url=None)
    client = create_app("ingress", dev).test_client()
    assert client.get("/verwaltung/behaelter", environ_base={"REMOTE_ADDR": "192.168.1.50"}).status_code == 200


def test_statische_dateien_vorhanden(einstellungen):
    client = create_app("direkt", einstellungen).test_client()
    for pfad in ("app.css", "app.js", "vendor/htmx.min.js", "vendor/fonts/ibm-plex-sans-400.woff2"):
        antwort = client.get(f"/static/{pfad}")
        assert antwort.status_code == 200, pfad
        antwort.close()


def test_unbekannter_modus(einstellungen):
    with pytest.raises(ValueError):
        create_app("falsch", einstellungen)
