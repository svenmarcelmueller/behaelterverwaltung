import re

import pytest

from app import db, etiketten, repo
from app.config import Einstellungen
from app.csrf import COOKIE
from app.factory import create_app

BASIS = "http://192.168.1.10:8099"


@pytest.fixture
def app(tmp_path):
    return create_app("ingress", Einstellungen(daten_ordner=tmp_path, dev=True, basis_url=BASIS))


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conn(app):
    verbindung = db.verbinden(app.config["DB_PFAD"])
    yield verbindung
    verbindung.close()


def senden(client, pfad, daten=None, **mehr):
    client.get("/verwaltung/einstellungen")
    token = client.get_cookie(COOKIE).value
    return client.post(pfad, data={"csrf": token, **(daten or {}), **mehr})


def text(antwort):
    return antwort.get_data(as_text=True)


def folie(conn, b, h) -> int:
    """Eigene Größe auf ungestanzter Folie anlegen (wie über das Formular)."""
    fmt, fehler = etiketten.format_pruefen({"etikett_b_mm": b, "etikett_h_mm": h, "rand_mm": 5,
                                            "abstand_mm": 0, "schnittlinien": "1"})
    assert not fehler
    return repo.etikettenformat_anlegen(conn, fmt)


# --- Navigation -----------------------------------------------------------


def test_start_leitet_auf_behaelter(client):
    assert client.get("/verwaltung/").location.endswith("/verwaltung/behaelter")


@pytest.mark.parametrize("pfad", ["behaelter", "etiketten", "faecher", "einstellungen"])
def test_seiten_erreichbar(client, pfad):
    assert client.get(f"/verwaltung/{pfad}").status_code == 200


def test_direktzugang_hat_keine_verwaltung(tmp_path):
    direkt = create_app("direkt", Einstellungen(daten_ordner=tmp_path, dev=True, basis_url=BASIS)).test_client()
    for pfad in ("behaelter", "etiketten", "etiketten/blatt", "faecher", "einstellungen"):
        assert direkt.get(f"/verwaltung/{pfad}").status_code == 404


# --- Behälter -------------------------------------------------------------


def test_behaelter_anlegen(client, conn):
    antwort = senden(client, "/verwaltung/behaelter/anlegen", anzahl="3", bezeichnung="Box blau")
    assert antwort.status_code == 303
    neu = re.search(r"neu=([A-Z0-9%,C]+)", antwort.location).group(1).replace("%2C", ",").split(",")
    assert len(neu) == 3

    seite = text(client.get(antwort.location))
    assert "3 Behälter angelegt." in seite
    assert "Etiketten für die 3 neuen drucken" in seite
    assert seite.count("<td>Box blau</td>") == 3
    assert repo.behaelter_anzahl_je_filter(conn)["offen"] == 3


@pytest.mark.parametrize("anzahl", ["0", "501", "abc"])
def test_behaelter_anlegen_ungueltig(client, conn, anzahl):
    antwort = senden(client, "/verwaltung/behaelter/anlegen", anzahl=anzahl)
    assert "fehler" in text(client.get(antwort.location)) or "Bitte" in text(client.get(antwort.location))
    assert repo.behaelter_anzahl_je_filter(conn)["alle"] == 0


def test_filter(client, conn):
    a, b, c = repo.behaelter_anlegen(conn, 3)
    repo.einlagern(conn, a, "Kabel")
    repo.behaelter_stilllegen(conn, c)
    repo.als_gedruckt_markieren(conn, [a])

    assert repo.behaelter_anzahl_je_filter(conn) == {"alle": 2, "leer": 1, "belegt": 1, "offen": 1, "stillgelegt": 1}
    seite = text(client.get("/verwaltung/behaelter?filter=stillgelegt"))
    assert c in seite and a not in seite
    assert "Kabel" in text(client.get("/verwaltung/behaelter?filter=belegt"))


def test_mehrere_stilllegen_ueberspringt_belegte(client, conn):
    a, b = repo.behaelter_anlegen(conn, 2)
    repo.einlagern(conn, a, "Kabel")
    antwort = client.post("/verwaltung/behaelter/auswahl", data={})  # ohne Token
    assert antwort.status_code == 400

    antwort = senden(client, "/verwaltung/behaelter/auswahl", {"codes": [a, b], "aktion": "stilllegen"})
    seite = text(client.get(antwort.location))
    assert "1 Behälter stillgelegt." in seite
    assert f"1 übersprungen, weil belegt oder schon stillgelegt: {a}." in seite
    assert repo.behaelter_holen(conn, b).status == "stillgelegt"
    assert repo.behaelter_holen(conn, a).status == "belegt"


def _alles_ausser_bezeichnung(conn):
    """Kompletter Datenbankinhalt ohne die Spalte bezeichnung – zum Vergleich vorher/nachher."""
    return {
        "behaelter": conn.execute(
            "SELECT id, code, erstellt_am, gedruckt_am, entfernt_am FROM behaelter ORDER BY id").fetchall(),
        "einlagerung": conn.execute("SELECT * FROM einlagerung ORDER BY id").fetchall(),
        "fach": conn.execute("SELECT * FROM fach ORDER BY id").fetchall(),
        "etikettenformat": conn.execute("SELECT * FROM etikettenformat ORDER BY id").fetchall(),
        "einstellung": conn.execute("SELECT * FROM einstellung ORDER BY schluessel").fetchall(),
    }


def test_bezeichnung_aendern_laesst_alles_andere_unberuehrt(client, conn):
    a, b, c, d = repo.behaelter_anlegen(conn, 4, "Box grau")
    repo.einlagern(conn, a, "Gemüse", "Karotten", repo.faecher(conn)[0]["id"], "Anna")
    repo.einlagern(conn, b, "Fleisch")
    repo.ausbuchen(conn, b)
    repo.als_gedruckt_markieren(conn, [a, b])
    repo.behaelter_stilllegen(conn, d)
    vorher = _alles_ausser_bezeichnung(conn)

    antwort = senden(client, "/verwaltung/behaelter/auswahl",
                     {"codes": [a, b, d], "aktion": "bezeichnung", "neue_bezeichnung": "  Box blau, groß "})
    assert "Bezeichnung „Box blau, groß“ für 2 Behälter gesetzt." in text(client.get(antwort.location))

    assert repo.behaelter_holen(conn, a).bezeichnung == "Box blau, groß"
    assert repo.behaelter_holen(conn, b).bezeichnung == "Box blau, groß"
    assert repo.behaelter_holen(conn, c).bezeichnung == "Box grau"   # nicht ausgewählt
    assert repo.behaelter_holen(conn, d).bezeichnung == "Box grau"   # stillgelegt: bleibt
    assert _alles_ausser_bezeichnung(conn) == vorher                  # Inhalt, Historie, Druckstatus unverändert
    assert repo.behaelter_holen(conn, a).einlagerung["inhalt_name"] == "Gemüse"


def test_bezeichnung_entfernen(client, conn):
    a = repo.behaelter_anlegen(conn, 1, "Box grau")[0]
    antwort = senden(client, "/verwaltung/behaelter/auswahl",
                     {"codes": [a], "aktion": "bezeichnung", "neue_bezeichnung": ""})
    assert "Bezeichnung bei 1 Behältern entfernt." in text(client.get(antwort.location))
    assert repo.behaelter_holen(conn, a).bezeichnung is None


def test_bezeichnung_ohne_auswahl(client, conn):
    repo.behaelter_anlegen(conn, 1, "Box grau")
    antwort = senden(client, "/verwaltung/behaelter/auswahl", aktion="bezeichnung", neue_bezeichnung="Neu")
    assert "Bitte zuerst Behälter auswählen." in text(client.get(antwort.location))


def test_bezeichnung_feld_auf_der_seite(client, conn):
    repo.behaelter_anlegen(conn, 1)
    seite = text(client.get("/verwaltung/behaelter"))
    assert "Bezeichnung der ausgewählten Behälter ändern" in seite
    assert 'data-enter-aktion="bezeichnung"' in seite
    assert "Bezeichnung der ausgewählten" not in text(client.get("/verwaltung/behaelter?filter=stillgelegt"))


def test_keine_neue_migration():
    """Diese Version darf das Datenbankschema nicht ändern."""
    from app import db as app_db
    assert sorted(p.name for p in app_db.MIGRATIONS_ORDNER.glob("*.sql")) == [
        "001_init.sql", "002_vorgestanzte_boegen.sql"]


def test_auswahl_etiketten_leitet_weiter(client, conn):
    a, b = repo.behaelter_anlegen(conn, 2)
    antwort = senden(client, "/verwaltung/behaelter/auswahl", {"codes": [a, b], "aktion": "etiketten"})
    assert f"codes={a},{b}" in antwort.location.replace("%2C", ",")


def test_auswahl_leer(client):
    antwort = senden(client, "/verwaltung/behaelter/auswahl", aktion="etiketten")
    assert "Bitte zuerst Behälter auswählen." in text(client.get(antwort.location))


# --- Etiketten ------------------------------------------------------------


def test_etiketten_standard_herma_9531_und_nicht_gedruckte(client, conn):
    codes = repo.behaelter_anlegen(conn, 3)
    repo.als_gedruckt_markieren(conn, codes[:1])
    seite = text(client.get("/verwaltung/etiketten"))
    assert "Alle noch nicht gedruckten (2)" in seite
    assert "HERMA 9531 · 45,7 × 21,2 mm" in seite
    assert "4 × 12 = 48 Aufkleber" in seite
    assert "vorgestanzt · 4 × 12 = 48 pro Bogen" in seite
    assert codes[1] in seite and codes[2] in seite


def test_etiketten_auswahl_und_eigene_folie(client, conn):
    codes = repo.behaelter_anlegen(conn, 2)
    format_40 = folie(conn, 40, 40)
    seite = text(client.get(f"/verwaltung/etiketten?codes={codes[0]}&format={format_40}"))
    assert "Auswahl aus der Liste (1)" in seite
    assert "5 × 7 = 35 Aufkleber" in seite
    assert "1 Etiketten auf 1 Blatt" in seite


def test_etiketten_auffuellen_vorschau(client, conn):
    repo.behaelter_anlegen(conn, 3)
    seite = text(client.get("/verwaltung/etiketten?auffuellen=1"))
    assert "(+45)" in seite
    assert "48 Etiketten auf 1 Blatt" in seite
    assert seite.count("vorschau-neu") == 45


def test_drucken_mit_auffuellen_legt_behaelter_an(client, conn):
    codes = repo.behaelter_anlegen(conn, 3)
    fmt = repo.etikettenformate(conn)[0]
    antwort = senden(client, "/verwaltung/etiketten/drucken",
                     format=fmt["id"], codes=",".join(codes), auffuellen="1")
    assert antwort.status_code == 303
    assert "/verwaltung/etiketten/blatt" in antwort.location
    assert repo.behaelter_anzahl_je_filter(conn)["alle"] == 48
    assert repo.einstellung(conn, "etikettenformat") == str(fmt["id"])


def test_etiketten_angebrochener_bogen_vorschau(client, conn):
    repo.behaelter_anlegen(conn, 3)
    seite = text(client.get("/verwaltung/etiketten?start=41&auffuellen=1"))
    assert '<option value="41" selected>Platz 41 · Zeile 11, Spalte 1</option>' in seite
    assert "ab Platz 41, 40 schon abgezogen" in seite
    assert seite.count("vorschau-weg") == 40
    assert seite.count("vorschau-druck") == 3
    assert "(+5)" in seite and seite.count("vorschau-neu") == 5
    assert "8 Etiketten auf 1 Blatt" in seite
    assert '<input type="hidden" name="start" value="41">' in seite


def test_etiketten_startplatz_ausserhalb_heisst_voller_bogen(client, conn):
    repo.behaelter_anlegen(conn, 1)
    seite = text(client.get("/verwaltung/etiketten?start=99"))
    assert '<option value="1" selected>Platz 1 · voller Bogen</option>' in seite
    assert "vorschau-weg" not in seite


def test_drucken_angebrochener_bogen_fuellt_nur_den_rest(client, conn):
    codes = repo.behaelter_anlegen(conn, 3)
    fmt = repo.etikettenformate(conn)[0]
    antwort = senden(client, "/verwaltung/etiketten/drucken",
                     format=fmt["id"], codes=",".join(codes), auffuellen="1", start="41")
    assert "start=41" in antwort.location
    assert repo.behaelter_anzahl_je_filter(conn)["alle"] == 8  # 48 − 40 abgezogene
    seite = text(client.get(antwort.location))
    assert seite.count('class="blatt"') == 1
    assert seite.count('class="etikett"') == 8
    assert "left: 9.85mm; top: 233.3mm" in seite  # Platz 41: Zeile 11, Spalte 1 (21,3 + 10 × 21,2)
    assert "left: 9.85mm; top: 21.3mm" not in seite
    assert "erster Bogen ab Platz 41" in seite


def test_druckblatt_angebrochener_bogen_ueber_zwei_blatt(client, conn):
    codes = repo.behaelter_anlegen(conn, 10)
    seite = text(client.get(f"/verwaltung/etiketten/blatt?codes={','.join(codes)}&start=45"))
    assert seite.count('class="blatt"') == 2
    assert seite.count('class="etikett"') == 10
    assert "left: 9.85mm; top: 21.3mm" in seite  # zweites Blatt beginnt wieder oben links


def test_drucken_ohne_basis_url(tmp_path):
    app = create_app("ingress", Einstellungen(daten_ordner=tmp_path, dev=True, basis_url=None))
    client = app.test_client()
    conn = db.verbinden(app.config["DB_PFAD"])
    codes = repo.behaelter_anlegen(conn, 1)
    antwort = senden(client, "/verwaltung/etiketten/drucken", format="1", codes=codes[0])
    assert "Ohne Basis-URL" in text(client.get(antwort.location))
    conn.close()


def test_druckblatt_herma_9531(client, conn):
    codes = repo.behaelter_anlegen(conn, 50)
    fmt = repo.etikettenformate(conn)[0]  # 9531, 48 pro Bogen
    seite = text(client.get(f"/verwaltung/etiketten/blatt?format={fmt['id']}&codes={','.join(codes)}"))
    assert seite.count('class="blatt"') == 2
    assert seite.count('class="etikett"') == 50
    assert seite.count("<svg") == 50
    assert "@page { size: 210.0mm 297.0mm; margin: 0; }" in seite
    assert "left: 9.85mm; top: 21.3mm" in seite      # erstes Etikett laut Bogen
    assert "left: 58.05mm; top: 21.3mm" in seite     # zweites Etikett in der Zeile
    assert "schnitt-" not in seite.split("<body")[1]  # vorgestanzt: keine Schnittlinien
    # QR links über die volle Höhe, Nummer daneben
    assert "width: 18.2mm; height: 18.2mm" in seite
    assert 'width="18.2mm"' in seite


def test_druckblatt_folie_mit_schnittlinien(client, conn):
    codes = repo.behaelter_anlegen(conn, 23)
    fmt = folie(conn, 50, 50)  # 20 pro Blatt
    seite = text(client.get(f"/verwaltung/etiketten/blatt?format={fmt}&codes={','.join(codes)}"))
    assert seite.count('class="blatt"') == 2
    assert 'left: 5.0mm; top: 23.5mm' in seite  # erster Aufkleber, mittig gesetzt
    assert seite.count("schnitt-senkrecht") == 2 * 5  # 5 Linien je Blatt


def test_druckblatt_versatz(client, conn):
    codes = repo.behaelter_anlegen(conn, 1)
    repo.einstellung_setzen(conn, "versatz_x_mm", "1.5")
    repo.einstellung_setzen(conn, "versatz_y_mm", "-2")
    seite = text(client.get(f"/verwaltung/etiketten/blatt?codes={codes[0]}"))
    assert "translate(1.5mm, -2.0mm)" in seite


def test_druckblatt_ignoriert_stillgelegte_und_unbekannte(client, conn):
    a, b = repo.behaelter_anlegen(conn, 2)
    repo.behaelter_stilllegen(conn, b)
    seite = text(client.get(f"/verwaltung/etiketten/blatt?codes={a},{b},ZZZZZZ,<script>"))
    assert seite.count('class="etikett"') == 1
    assert "<script>" not in seite.split("</head>")[1].replace('<script src', '')


def test_als_gedruckt_markieren(client, conn):
    codes = repo.behaelter_anlegen(conn, 2)
    antwort = senden(client, "/verwaltung/etiketten/gedruckt", codes=",".join(codes))
    assert "2 Etiketten als gedruckt markiert." in text(client.get(antwort.location))
    assert repo.behaelter_anzahl_je_filter(conn)["offen"] == 0


def test_format_anlegen_und_loeschen(client, conn):
    antwort = senden(client, "/verwaltung/etiketten/format",
                     etikett_b_mm="45", etikett_h_mm="45", rand_mm="5", abstand_mm="0", schnittlinien="1")
    seite = text(client.get(antwort.location))
    assert "HERMA 9500 · 45 × 45 mm" in seite
    assert "4 × 6 = 24 Aufkleber" in seite
    neu = max(f["id"] for f in repo.etikettenformate(conn))

    antwort = senden(client, f"/verwaltung/etiketten/format/{neu}/loeschen")
    assert "Etikettengröße gelöscht." in text(client.get(antwort.location))
    assert len(repo.etikettenformate(conn)) == 1


def test_format_ungueltig(client, conn):
    antwort = senden(client, "/verwaltung/etiketten/format",
                     etikett_b_mm="5", etikett_h_mm="45", rand_mm="5", abstand_mm="0")
    assert "Breite: erlaubt sind 15 bis 200 mm." in text(client.get(antwort.location))
    assert len(repo.etikettenformate(conn)) == 1


def test_letztes_format_bleibt(client, conn):
    ids = [f["id"] for f in repo.etikettenformate(conn)]
    for i in ids[:-1]:
        repo.etikettenformat_loeschen(conn, i)
    with pytest.raises(repo.UngueltigeEingabe):
        repo.etikettenformat_loeschen(conn, ids[-1])


# --- Fächer ---------------------------------------------------------------


def test_faecher_anlegen_umbenennen_verschieben_loeschen(client, conn):
    senden(client, "/verwaltung/faecher", name="Boden")
    boden = next(f["id"] for f in repo.faecher(conn) if f["name"] == "Boden")
    senden(client, f"/verwaltung/faecher/{boden}", aktion="umbenennen", name="Ganz unten")
    senden(client, f"/verwaltung/faecher/{boden}", aktion="hoch", name="Ganz unten")
    assert [f["name"] for f in repo.faecher(conn)] == ["Oben", "Mitte", "Ganz unten", "Unten"]

    senden(client, f"/verwaltung/faecher/{boden}", aktion="loeschen")
    assert [f["name"] for f in repo.faecher(conn)] == ["Oben", "Mitte", "Unten"]


def test_verwendetes_fach_nicht_loeschbar(client, conn):
    oben = repo.faecher(conn)[0]["id"]
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel", fach_id=oben)
    antwort = senden(client, f"/verwaltung/faecher/{oben}", aktion="loeschen")
    assert "kann nur umbenannt werden" in text(client.get(antwort.location))


def test_fach_verschieben_an_den_raendern(conn):
    ids = [f["id"] for f in repo.faecher(conn)]
    repo.fach_verschieben(conn, ids[0], -1)
    repo.fach_verschieben(conn, ids[-1], 1)
    assert [f["id"] for f in repo.faecher(conn)] == ids


# --- Einstellungen --------------------------------------------------------


def test_druckversatz_speichern_und_begrenzen(client, conn):
    senden(client, "/verwaltung/einstellungen", versatz_x_mm="1,5", versatz_y_mm="99")
    assert repo.einstellung(conn, "versatz_x_mm") == "1.5"
    assert repo.einstellung(conn, "versatz_y_mm") == "20"


def test_zuruecksetzen_braucht_bestaetigung(client, conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")

    senden(client, "/verwaltung/einstellungen/zuruecksetzen", bestaetigung="ja")
    assert repo.behaelter_anzahl_je_filter(conn)["alle"] == 1

    antwort = senden(client, "/verwaltung/einstellungen/zuruecksetzen", bestaetigung="löschen")
    assert "Alle Behälter und Einlagerungen wurden gelöscht." in text(client.get(antwort.location))
    assert repo.behaelter_anzahl_je_filter(conn)["alle"] == 0
    assert len(repo.faecher(conn)) == 3
    assert repo.einstellung(conn, "secret_key")  # Schlüssel für Meldungen bleibt
