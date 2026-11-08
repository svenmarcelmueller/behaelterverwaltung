import pytest

from app import etiketten

A4 = {"blatt_b_mm": 210, "blatt_h_mm": 297, "rand_mm": 5, "abstand_mm": 0}


def fmt(b, h, **mehr):
    return {**A4, "etikett_b_mm": b, "etikett_h_mm": h, **mehr}


@pytest.mark.parametrize("b, h, spalten, zeilen", [
    (50, 50, 4, 5),   # 200 mm genau nutzbar
    (40, 40, 5, 7),
    (60, 40, 3, 7),
    (200, 287, 1, 1),
    (201, 50, 0, 5),
])
def test_raster_herma_vorlagen(b, h, spalten, zeilen):
    r = etiketten.raster(fmt(b, h))
    assert (r.spalten, r.zeilen) == (spalten, zeilen)


def test_raster_mittig():
    r = etiketten.raster(fmt(60, 40))  # 180 × 280 mm
    assert r.links_mm == 15 and r.oben_mm == 8.5
    assert r.platz(0) == (15, 8.5)
    assert r.platz(4) == (75, 48.5)  # 2. Zeile, 2. Spalte


def test_raster_mit_abstand():
    r = etiketten.raster(fmt(50, 50, abstand_mm=3))  # 200 mm: 3 × 50 + 2 × 3 = 156, 4 × 50 + 3 × 3 = 209 > 200
    assert r.spalten == 3
    assert r.breite_mm == 156
    assert r.platz(1)[0] - r.platz(0)[0] == 53


def test_schnittlinien_ohne_abstand_eine_pro_grenze():
    r = etiketten.raster(fmt(50, 50))
    assert r.schnitt_x() == [5, 55, 105, 155, 205]
    assert len(r.schnitt_y()) == 6


def test_schnittlinien_mit_abstand_zwei_pro_luecke():
    r = etiketten.raster(fmt(50, 50, abstand_mm=3))
    assert len(r.schnitt_x()) == 6


def test_seiten_und_freie_plaetze():
    r = etiketten.raster(fmt(50, 50))  # 20 pro Blatt
    codes = [f"C{i:05d}" for i in range(23)]
    blaetter = etiketten.seiten(codes, r)
    assert [len(b) for b in blaetter] == [20, 3]
    assert blaetter[1][0] == {"code": "C00020", "x": 5, "y": 23.5}
    assert etiketten.freie_plaetze(23, r) == 17
    assert etiketten.freie_plaetze(20, r) == 0
    assert etiketten.freie_plaetze(0, r) == 0


def test_seiten_mit_startplatz_ueberspringt_abgezogene():
    r = etiketten.raster(fmt(50, 50))  # 4 × 5 = 20 pro Blatt
    codes = [f"C{i:05d}" for i in range(23)]
    blaetter = etiketten.seiten(codes, r, start=6)  # Platz 7 = 2. Zeile, 3. Spalte
    assert [len(b) for b in blaetter] == [14, 9]
    assert blaetter[0][0] == {"code": "C00000", "x": 105, "y": 73.5}
    assert blaetter[1][0] == {"code": "C00014", "x": 5, "y": 23.5}  # zweites Blatt wieder von vorn
    assert etiketten.blattzahl(23, r, 6) == 2
    assert etiketten.freie_plaetze(23, r, 6) == 11
    assert etiketten.freie_plaetze(14, r, 6) == 0


@pytest.mark.parametrize("eingabe, index", [
    ("7", 6), ("1", 0), ("20", 19), ("21", 0), ("0", 0), ("-3", 0), ("x", 0), (None, 0), ("", 0),
])
def test_startplatz_wird_begrenzt(eingabe, index):
    assert etiketten.startplatz(eingabe, etiketten.raster(fmt(50, 50))) == index


def test_aufteilung_quadratisch_qr_oben():
    a = etiketten.aufteilung(50, 50)
    assert not a.quer
    assert a.qr_mm <= 44 and not a.qr_zu_klein
    assert a.qr_y + a.qr_mm <= a.text_y + 0.01   # Text unter dem QR
    assert a.text_y + a.text_h <= 50 - 3 + 0.01  # nichts ragt in den Rand


def test_aufteilung_quer_qr_links():
    a = etiketten.aufteilung(60, 30)
    assert a.quer
    assert a.qr_mm == 25.8  # 30 mm minus 2 × 2,1 mm Ruhezone
    assert a.text_x >= a.qr_x + a.qr_mm


HERMA_9531 = {"blatt_b_mm": 210, "blatt_h_mm": 297, "etikett_b_mm": 45.7, "etikett_h_mm": 21.2,
              "rand_mm": 0, "abstand_mm": 2.5, "abstand_y_mm": 0, "spalten": 4, "zeilen": 12,
              "links_mm": 9.85, "oben_mm": 21.3}


def test_raster_herma_9531_vorgestanzt():
    r = etiketten.raster(HERMA_9531)
    assert r.vorgestanzt
    assert (r.spalten, r.zeilen, r.pro_blatt) == (4, 12, 48)
    assert r.platz(0) == (9.85, 21.3)
    assert r.platz(1) == (58.05, 21.3)     # 9,85 + 45,7 + 2,5
    assert r.platz(4) == (9.85, 42.5)      # zweite Zeile, ohne Abstand
    x, y = r.platz(47)
    assert round(x + 45.7, 2) == 200.15    # rechter Rand 9,85 mm
    assert round(y + 21.2, 2) == 275.7     # unterer Rand 21,3 mm


def test_aufteilung_herma_9531_qr_links_volle_hoehe():
    a = etiketten.aufteilung(45.7, 21.2)
    assert a.quer
    assert a.qr_x == 1.5 and a.qr_y == 1.5
    assert a.qr_mm == 18.2                  # 21,2 mm minus 2 × 1,5 mm
    assert not a.qr_zu_klein
    assert a.text_x == 22.2                 # Nummer rechts neben dem QR-Code, 2,5 mm frei dazwischen
    assert a.text_x + a.text_b <= 45.7 - 1.5 + 0.01
    assert a.schrift_mm >= 4.5              # gut lesbar (≈ 13 pt)
    assert a.schrift_mm * 4.1 <= a.text_b   # sechs Zeichen passen in den Platz


def test_aufteilung_klein_warnt():
    assert etiketten.aufteilung(20, 20).qr_zu_klein


@pytest.mark.parametrize("b, h", [(15, 15), (40, 40), (50, 50), (60, 40), (70, 37), (105, 74), (200, 280)])
def test_aufteilung_passt_immer_in_den_aufkleber(b, h):
    a = etiketten.aufteilung(b, h)
    assert a.qr_x + a.qr_mm <= b + 0.01 and a.qr_y + a.qr_mm <= h + 0.01
    assert a.text_x + a.text_b <= b + 0.01 and a.text_y + a.text_h <= h + 0.01
    assert a.qr_mm > 0 and a.schrift_mm > 0


def test_format_pruefen_ok_mit_komma_und_standardname():
    f, fehler = etiketten.format_pruefen({"etikett_b_mm": "45,5", "etikett_h_mm": "45", "rand_mm": "5", "abstand_mm": "0"})
    assert fehler == []
    assert f["etikett_b_mm"] == 45.5
    assert f["name"] == "HERMA 9500 · 45.5 × 45 mm"
    assert f["schnittlinien"] == 0


def test_format_pruefen_fehler():
    _, fehler = etiketten.format_pruefen({"etikett_b_mm": "abc", "etikett_h_mm": "5", "rand_mm": "5", "abstand_mm": "0"})
    assert any("Breite" in f for f in fehler)
    assert any("Höhe" in f for f in fehler)


def test_format_pruefen_passt_nicht():
    _, fehler = etiketten.format_pruefen({"etikett_b_mm": "200", "etikett_h_mm": "200", "rand_mm": "30", "abstand_mm": "0"})
    assert fehler == ["Mit diesem Rand passt kein einziger Aufkleber auf das Blatt."]
