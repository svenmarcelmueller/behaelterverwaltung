import pytest

from app import qr
from app.config import basis_url_pruefen


@pytest.mark.parametrize("eingabe, erwartet", [
    ("", None),
    (None, None),
    ("  http://192.168.1.10:8099/ ", "http://192.168.1.10:8099"),
    ("https://behaelter.example.de", "https://behaelter.example.de"),
    ("192.168.1.10:8099", None),
    ("http://192.168.1.10 :8099", None),
])
def test_basis_url_pruefen(eingabe, erwartet):
    assert basis_url_pruefen(eingabe) == erwartet


def test_behaelter_url():
    assert qr.behaelter_url("http://192.168.1.10:8099/", "K7F3QX") == "http://192.168.1.10:8099/b/K7F3QX"


def test_svg_bildschirm():
    bild = qr.svg("http://192.168.1.10:8099/b/K7F3QX")
    assert bild.startswith("<svg") and "<?xml" not in bild
    assert 'width="' not in bild.split(">")[0]  # skaliert per CSS


def test_svg_druck_in_millimetern():
    bild = qr.svg("http://192.168.1.10:8099/b/K7F3QX", groesse_mm=30)
    kopf = bild.split(">")[0]
    assert 'width="30mm"' in kopf and 'height="30mm"' in kopf


def test_svg_druck_krumme_groesse():
    kopf = qr.svg("http://192.168.1.10:8099/b/K7F3QX", groesse_mm=44.0).split(">")[0]
    assert 'width="44mm"' in kopf
