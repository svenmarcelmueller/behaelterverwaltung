import threading

import pytest

from app import db, repo


def fach_id(conn, name):
    return next(f["id"] for f in repo.faecher(conn) if f["name"] == name)


# --- Codes ----------------------------------------------------------------


def test_codes_ohne_verwechselbare_zeichen(conn):
    codes = repo.behaelter_anlegen(conn, anzahl=200)
    assert len(set(codes)) == 200
    for code in codes:
        assert len(code) == 6
        assert not set(code) & set("0O1I")
        assert set(code) <= set(repo.CODE_ZEICHEN)


def test_anzahl_wird_begrenzt(conn):
    with pytest.raises(repo.UngueltigeEingabe):
        repo.behaelter_anlegen(conn, anzahl=0)
    with pytest.raises(repo.UngueltigeEingabe):
        repo.behaelter_anlegen(conn, anzahl=501)


def test_code_gross_klein_und_leerzeichen_egal(conn):
    code = repo.behaelter_anlegen(conn)[0]
    assert repo.behaelter_holen(conn, f"  {code.lower()} ").code == code


# --- Einlagern ------------------------------------------------------------


def test_neuer_behaelter_ist_leer(conn):
    code = repo.behaelter_anlegen(conn)[0]
    assert repo.behaelter_holen(conn, code).status == "leer"


def test_einlagern(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "  Akkuschrauber-Bits ", "Bit-Set 32-teilig", fach_id(conn, "Mitte"), "Anna")
    b = repo.behaelter_holen(conn, code)
    assert b.status == "belegt"
    assert b.einlagerung["inhalt_name"] == "Akkuschrauber-Bits"
    assert b.einlagerung["beschreibung"] == "Bit-Set 32-teilig"
    assert b.einlagerung["fach_name"] == "Mitte"
    assert b.einlagerung["eingelagert_von"] == "Anna"
    assert repo.letztes_fach(conn) == fach_id(conn, "Mitte")


def test_doppelt_einlagern_geht_nicht(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    with pytest.raises(repo.BehaelterBelegt):
        repo.einlagern(conn, code, "Handschuhe")
    assert repo.behaelter_holen(conn, code).einlagerung["inhalt_name"] == "Kabel"


def test_doppel_tap_gleichzeitig_nur_eine_einlagerung(tmp_path):
    """Zwei Anfragen gleichzeitig: der UNIQUE-Index lässt nur eine durch."""
    pfad = tmp_path / "behaelter.db"
    db.migrieren(pfad)
    vorbereitung = db.verbinden(pfad)
    code = repo.behaelter_anlegen(vorbereitung)[0]
    vorbereitung.close()

    ergebnisse = []
    start = threading.Barrier(5)

    def tippen():
        conn = db.verbinden(pfad)
        start.wait()
        try:
            repo.einlagern(conn, code, "Kabel")
            ergebnisse.append("ok")
        except repo.BehaelterBelegt:
            ergebnisse.append("belegt")
        finally:
            conn.close()

    threads = [threading.Thread(target=tippen) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert ergebnisse.count("ok") == 1
    assert ergebnisse.count("belegt") == 4


def test_einlagern_ohne_inhalt(conn):
    code = repo.behaelter_anlegen(conn)[0]
    with pytest.raises(repo.UngueltigeEingabe):
        repo.einlagern(conn, code, "   ")


def test_einlagern_unbekanntes_fach(conn):
    code = repo.behaelter_anlegen(conn)[0]
    with pytest.raises(repo.UngueltigeEingabe):
        repo.einlagern(conn, code, "Kabel", fach_id=999)


def test_einlagern_unbekannter_code(conn):
    with pytest.raises(repo.UnbekannterCode):
        repo.einlagern(conn, "ZZZZZZ", "Kabel")


# --- Ausbuchen ------------------------------------------------------------


def test_ausbuchen(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel", von="Anna")
    repo.ausbuchen(conn, code, von="Tom")
    assert repo.behaelter_holen(conn, code).status == "leer"
    eintrag = repo.historie(conn, code)[0]
    assert eintrag["ausgelagert_von"] == "Tom"
    assert eintrag["ausgelagert_am"]


def test_leeren_behaelter_ausbuchen_geht_nicht(conn):
    code = repo.behaelter_anlegen(conn)[0]
    with pytest.raises(repo.BehaelterLeer):
        repo.ausbuchen(conn, code)


def test_nach_ausbuchen_wieder_einlagern(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    repo.ausbuchen(conn, code)
    repo.einlagern(conn, code, "Handschuhe")
    assert [e["inhalt_name"] for e in repo.historie(conn, code)] == ["Handschuhe", "Kabel"]


# --- Korrigieren ----------------------------------------------------------


def test_korrigieren(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabl", fach_id=fach_id(conn, "Oben"))
    repo.korrigieren(conn, code, "Kabel", "HDMI und USB", fach_id(conn, "Unten"))
    e = repo.behaelter_holen(conn, code).einlagerung
    assert (e["inhalt_name"], e["beschreibung"], e["fach_name"]) == ("Kabel", "HDMI und USB", "Unten")


def test_leeren_behaelter_korrigieren_geht_nicht(conn):
    code = repo.behaelter_anlegen(conn)[0]
    with pytest.raises(repo.BehaelterLeer):
        repo.korrigieren(conn, code, "Kabel")


# --- Stilllegen -----------------------------------------------------------


def test_stillgelegter_code(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.behaelter_stilllegen(conn, code)
    assert repo.behaelter_holen(conn, code).status == "stillgelegt"
    with pytest.raises(repo.Stillgelegt):
        repo.einlagern(conn, code, "Kabel")
    with pytest.raises(repo.Stillgelegt):
        repo.ausbuchen(conn, code)
    with pytest.raises(repo.Stillgelegt):
        repo.behaelter_stilllegen(conn, code)


def test_belegten_behaelter_stilllegen_geht_nicht(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    with pytest.raises(repo.BehaelterBelegt):
        repo.behaelter_stilllegen(conn, code)


def test_stilllegen_behaelt_historie(conn):
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Kabel")
    repo.ausbuchen(conn, code)
    repo.behaelter_stilllegen(conn, code)
    assert [e["inhalt_name"] for e in repo.historie(conn, code)] == ["Kabel"]


# --- Suche, Zähler --------------------------------------------------------


@pytest.fixture
def bestand(conn):
    codes = repo.behaelter_anlegen(conn, anzahl=5)
    repo.einlagern(conn, codes[0], "Akkuschrauber-Bits", "Torx und Kreuz", fach_id(conn, "Mitte"))
    repo.einlagern(conn, codes[1], "Lichterketten Weihnachten", None, fach_id(conn, "Oben"))
    repo.einlagern(conn, codes[2], "Ärmelschoner", "100% Baumwolle", fach_id(conn, "Unten"))
    repo.behaelter_stilllegen(conn, codes[4])
    conn.execute("UPDATE einlagerung SET eingelagert_am = '2026-09-01T10:00:00+02:00' WHERE inhalt_name LIKE 'Licht%'")
    conn.commit()
    return codes


def namen(treffer):
    return [t["inhalt_name"] for t in treffer]


def test_suche_text_in_name_und_beschreibung(conn, bestand):
    assert namen(repo.suchen(conn, "bits")) == ["Akkuschrauber-Bits"]
    assert namen(repo.suchen(conn, "TORX")) == ["Akkuschrauber-Bits"]


def test_suche_umlaute_gross_klein(conn, bestand):
    assert namen(repo.suchen(conn, "ärmel")) == ["Ärmelschoner"]


def test_suche_prozent_und_unterstrich_sind_keine_platzhalter(conn, bestand):
    assert namen(repo.suchen(conn, "100%")) == ["Ärmelschoner"]
    assert namen(repo.suchen(conn, "%")) == ["Ärmelschoner"]  # nur der Eintrag mit echtem %
    assert repo.suchen(conn, "_") == []


def test_suche_nach_code(conn, bestand):
    assert namen(repo.suchen(conn, bestand[0].lower())) == ["Akkuschrauber-Bits"]


def test_suche_ohne_stillgelegte(conn, bestand):
    alle = repo.suchen(conn)
    assert len(alle) == 4
    assert bestand[4] not in [t["code"] for t in alle]


def test_suche_status_und_fach(conn, bestand):
    assert [t["code"] for t in repo.suchen(conn, status="leer")] == [bestand[3]]
    assert namen(repo.suchen(conn, fach_id=fach_id(conn, "Oben"))) == ["Lichterketten Weihnachten"]


def test_suche_datum(conn, bestand):
    assert namen(repo.suchen(conn, bis_datum="2026-09-30")) == ["Lichterketten Weihnachten"]
    assert "Lichterketten Weihnachten" not in namen(repo.suchen(conn, von_datum="2026-10-01"))


def test_sortierung(conn, bestand):
    assert namen(repo.suchen(conn, status="belegt", sortierung="name")) == [
        "Akkuschrauber-Bits", "Ärmelschoner", "Lichterketten Weihnachten",
    ]
    assert namen(repo.suchen(conn, status="belegt", sortierung="fach")) == [
        "Lichterketten Weihnachten", "Akkuschrauber-Bits", "Ärmelschoner",
    ]
    assert namen(repo.suchen(conn, status="belegt", sortierung="alt"))[0] == "Lichterketten Weihnachten"
    assert repo.suchen(conn, sortierung="neu")[-1]["status"] == "leer"  # leere ans Ende


def test_unbekannte_sortierung(conn):
    with pytest.raises(repo.UngueltigeEingabe):
        repo.suchen(conn, sortierung="DROP TABLE")


def test_zaehlen(conn, bestand):
    assert repo.zaehlen(conn) == {"belegt": 3, "frei": 1}


def test_letzte_einlagerung(conn, bestand):
    assert repo.letzte_einlagerung(conn)["inhalt_name"] in ("Akkuschrauber-Bits", "Ärmelschoner")
