import shutil

from app import db, repo


def test_migration_legt_startdaten_an(conn):
    assert [f["name"] for f in repo.faecher(conn)] == ["Oben", "Mitte", "Unten"]
    formate = repo.etikettenformate(conn)
    assert len(formate) == 1
    f = formate[0]
    assert f["name"] == "HERMA 9531 · 45,7 × 21,2 mm"
    assert (f["etikett_b_mm"], f["etikett_h_mm"], f["spalten"], f["zeilen"]) == (45.7, 21.2, 4, 12)
    assert (f["links_mm"], f["oben_mm"], f["abstand_mm"], f["abstand_y_mm"]) == (9.85, 21.3, 2.5, 0)
    assert (f["blatt_b_mm"], f["blatt_h_mm"], f["schnittlinien"]) == (210, 297, 0)


def test_update_von_0_4_behaelt_eigene_formate(tmp_path, monkeypatch):
    """Bestehende Installation: Vorlagen für HERMA 9500 weg, selbst angelegte Größe bleibt."""
    nur_001 = tmp_path / "alt"
    nur_001.mkdir()
    shutil.copy(db.MIGRATIONS_ORDNER / "001_init.sql", nur_001)
    pfad = tmp_path / "behaelter.db"

    with monkeypatch.context() as m:
        m.setattr(db, "MIGRATIONS_ORDNER", nur_001)
        assert db.migrieren(pfad) == [1]
    conn = db.verbinden(pfad)
    with conn:
        conn.execute("INSERT INTO etikettenformat (name, etikett_b_mm, etikett_h_mm) VALUES ('Meine 45er', 45, 45)")
        conn.execute("INSERT INTO einstellung VALUES ('etikettenformat', '1')")  # zeigte auf 50 × 50
    conn.close()

    assert db.migrieren(pfad) == [2]
    conn = db.verbinden(pfad)
    assert [f["name"] for f in repo.etikettenformate(conn)] == ["Meine 45er", "HERMA 9531 · 45,7 × 21,2 mm"]
    assert repo.einstellung(conn, "etikettenformat") is None
    conn.close()


def test_migration_laeuft_nur_einmal(tmp_path):
    pfad = tmp_path / "behaelter.db"
    assert db.migrieren(pfad) == [1, 2]
    assert db.migrieren(pfad) == []
    conn = db.verbinden(pfad)
    assert len(repo.faecher(conn)) == 3  # Startdaten nicht doppelt
    conn.close()


def test_daten_bleiben_nach_neuem_start_erhalten(tmp_path):
    pfad = tmp_path / "behaelter.db"
    db.migrieren(pfad)
    conn = db.verbinden(pfad)
    code = repo.behaelter_anlegen(conn)[0]
    repo.einlagern(conn, code, "Akkuschrauber-Bits")
    conn.close()

    db.migrieren(pfad)  # wie beim nächsten Start der App
    conn = db.verbinden(pfad)
    assert repo.behaelter_holen(conn, code).einlagerung["inhalt_name"] == "Akkuschrauber-Bits"
    conn.close()
