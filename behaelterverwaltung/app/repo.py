"""Alle Datenbankzugriffe: Behälter, Einlagerungen, Fächer, Einstellungen.

Jede Funktion bekommt die Verbindung als erstes Argument, damit sie sich ohne
Flask testen lässt. Fachliche Fehler sind Unterklassen von Fehler und tragen
eine Meldung, die direkt angezeigt werden kann.
"""

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime

# Ohne 0/O und 1/I, damit sich Codes auf dem Aufkleber nicht verwechseln lassen.
CODE_ZEICHEN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LAENGE = 6

SORTIERUNGEN = {
    "neu": "e.eingelagert_am IS NULL, e.eingelagert_am DESC, e.id DESC",
    "alt": "e.eingelagert_am IS NULL, e.eingelagert_am ASC, e.id ASC",
    "name": "e.inhalt_name IS NULL, sortiert(e.inhalt_name), b.code",
    "fach": "f.sortierung IS NULL, f.sortierung, sortiert(e.inhalt_name), b.code",
}


class Fehler(Exception):
    meldung = "Das hat nicht geklappt."

    def __init__(self, meldung: str | None = None):
        super().__init__(meldung or self.meldung)
        self.meldung = meldung or self.meldung


class UnbekannterCode(Fehler):
    meldung = "Diesen Behälter gibt es nicht."


class Stillgelegt(Fehler):
    meldung = "Dieser Behälter ist stillgelegt."


class BehaelterBelegt(Fehler):
    meldung = "In diesem Behälter liegt schon etwas. Bitte erst ausbuchen."


class BehaelterLeer(Fehler):
    meldung = "Dieser Behälter ist bereits leer."


class UngueltigeEingabe(Fehler):
    meldung = "Bitte die Eingaben prüfen."


@dataclass(frozen=True)
class Behaelter:
    id: int
    code: str
    bezeichnung: str | None
    erstellt_am: str
    gedruckt_am: str | None
    entfernt_am: str | None
    einlagerung: dict | None  # aktiver Inhalt oder None

    @property
    def status(self) -> str:
        if self.entfernt_am:
            return "stillgelegt"
        return "belegt" if self.einlagerung else "leer"


def jetzt() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def code_normalisieren(code: str) -> str:
    return (code or "").strip().upper()


def _text(wert: str | None) -> str | None:
    wert = (wert or "").strip()
    return wert or None


# --- Behälter -------------------------------------------------------------


def neuer_code(conn: sqlite3.Connection) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ZEICHEN) for _ in range(CODE_LAENGE))
        if not conn.execute("SELECT 1 FROM behaelter WHERE code = ?", (code,)).fetchone():
            return code


def behaelter_anlegen(conn: sqlite3.Connection, anzahl: int = 1, bezeichnung: str | None = None) -> list[str]:
    if not 1 <= anzahl <= 500:
        raise UngueltigeEingabe("Bitte zwischen 1 und 500 Behälter anlegen.")
    codes = []
    with conn:
        for _ in range(anzahl):
            code = neuer_code(conn)
            conn.execute(
                "INSERT INTO behaelter (code, bezeichnung, erstellt_am) VALUES (?, ?, ?)",
                (code, _text(bezeichnung), jetzt()),
            )
            codes.append(code)
    return codes


def _aktive_einlagerung(conn: sqlite3.Connection, behaelter_id: int) -> dict | None:
    row = conn.execute(
        """SELECT e.*, f.name AS fach_name
           FROM einlagerung e LEFT JOIN fach f ON f.id = e.fach_id
           WHERE e.behaelter_id = ? AND e.ausgelagert_am IS NULL""",
        (behaelter_id,),
    ).fetchone()
    return dict(row) if row else None


def behaelter_holen(conn: sqlite3.Connection, code: str) -> Behaelter | None:
    row = conn.execute("SELECT * FROM behaelter WHERE code = ?", (code_normalisieren(code),)).fetchone()
    if not row:
        return None
    return Behaelter(**dict(row), einlagerung=_aktive_einlagerung(conn, row["id"]))


def _nutzbarer_behaelter(conn: sqlite3.Connection, code: str) -> Behaelter:
    behaelter = behaelter_holen(conn, code)
    if behaelter is None:
        raise UnbekannterCode()
    if behaelter.status == "stillgelegt":
        raise Stillgelegt()
    return behaelter


def behaelter_stilllegen(conn: sqlite3.Connection, code: str) -> None:
    behaelter = _nutzbarer_behaelter(conn, code)
    if behaelter.status == "belegt":
        raise BehaelterBelegt("Nur leere Behälter können stillgelegt werden.")
    with conn:
        conn.execute("UPDATE behaelter SET entfernt_am = ? WHERE id = ?", (jetzt(), behaelter.id))


def als_gedruckt_markieren(conn: sqlite3.Connection, codes: list[str]) -> None:
    with conn:
        conn.executemany(
            "UPDATE behaelter SET gedruckt_am = ? WHERE code = ?",
            [(jetzt(), code_normalisieren(c)) for c in codes],
        )


# --- Einlagern, Ausbuchen, Korrigieren -----------------------------------


def _fach_pruefen(conn: sqlite3.Connection, fach_id: int | None) -> int | None:
    if fach_id in (None, ""):
        return None
    try:
        fach_id = int(fach_id)
    except (TypeError, ValueError):
        raise UngueltigeEingabe("Unbekanntes Fach.") from None
    if not conn.execute("SELECT 1 FROM fach WHERE id = ?", (fach_id,)).fetchone():
        raise UngueltigeEingabe("Unbekanntes Fach.")
    return fach_id


def einlagern(
    conn: sqlite3.Connection,
    code: str,
    inhalt_name: str,
    beschreibung: str | None = None,
    fach_id: int | None = None,
    von: str | None = None,
    foto_pfad: str | None = None,
) -> int:
    behaelter = _nutzbarer_behaelter(conn, code)
    inhalt_name = _text(inhalt_name)
    if not inhalt_name:
        raise UngueltigeEingabe("Bitte angeben, was hineinkommt.")
    fach_id = _fach_pruefen(conn, fach_id)
    if behaelter.status == "belegt":
        raise BehaelterBelegt()

    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO einlagerung
                   (behaelter_id, fach_id, inhalt_name, beschreibung, foto_pfad, eingelagert_am, eingelagert_von)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (behaelter.id, fach_id, inhalt_name, _text(beschreibung), foto_pfad, jetzt(), _text(von)),
            )
            if fach_id is not None:
                _einstellung_setzen(conn, "letztes_fach", str(fach_id))
    except sqlite3.IntegrityError:
        # Zwei gleichzeitige Einlagerungen (z. B. Doppel-Tap): der UNIQUE-Index lässt nur eine zu.
        raise BehaelterBelegt() from None
    return cur.lastrowid


def ausbuchen(conn: sqlite3.Connection, code: str, von: str | None = None) -> None:
    behaelter = _nutzbarer_behaelter(conn, code)
    if behaelter.status != "belegt":
        raise BehaelterLeer()
    with conn:
        cur = conn.execute(
            "UPDATE einlagerung SET ausgelagert_am = ?, ausgelagert_von = ? WHERE id = ? AND ausgelagert_am IS NULL",
            (jetzt(), _text(von), behaelter.einlagerung["id"]),
        )
    if cur.rowcount == 0:
        raise BehaelterLeer()


def korrigieren(
    conn: sqlite3.Connection,
    code: str,
    inhalt_name: str,
    beschreibung: str | None = None,
    fach_id: int | None = None,
) -> None:
    behaelter = _nutzbarer_behaelter(conn, code)
    if behaelter.status != "belegt":
        raise BehaelterLeer("Der Behälter ist leer, es gibt nichts zu korrigieren.")
    inhalt_name = _text(inhalt_name)
    if not inhalt_name:
        raise UngueltigeEingabe("Der Inhalt darf nicht leer sein.")
    fach_id = _fach_pruefen(conn, fach_id)
    with conn:
        conn.execute(
            "UPDATE einlagerung SET inhalt_name = ?, beschreibung = ?, fach_id = ? WHERE id = ?",
            (inhalt_name, _text(beschreibung), fach_id, behaelter.einlagerung["id"]),
        )


def historie(conn: sqlite3.Connection, code: str) -> list[dict]:
    """Alle Einlagerungen eines Behälters, neueste zuerst (auch die aktive)."""
    behaelter = behaelter_holen(conn, code)
    if behaelter is None:
        raise UnbekannterCode()
    rows = conn.execute(
        """SELECT e.*, f.name AS fach_name
           FROM einlagerung e LEFT JOIN fach f ON f.id = e.fach_id
           WHERE e.behaelter_id = ?
           ORDER BY e.eingelagert_am DESC, e.id DESC""",
        (behaelter.id,),
    )
    return [dict(r) for r in rows]


# --- Übersicht und Suche --------------------------------------------------


def _like_muster(text: str) -> str:
    text = text.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{text}%"


def suchen(
    conn: sqlite3.Connection,
    text: str | None = None,
    fach_id: int | None = None,
    status: str | None = None,  # None = alle, "belegt", "leer"
    von_datum: str | None = None,  # JJJJ-MM-TT, bezieht sich auf das Einlagerungsdatum
    bis_datum: str | None = None,
    sortierung: str = "neu",
) -> list[dict]:
    """Aktive (nicht stillgelegte) Behälter mit ihrem aktuellen Inhalt."""
    if sortierung not in SORTIERUNGEN:
        raise UngueltigeEingabe("Unbekannte Sortierung.")
    if status not in (None, "belegt", "leer"):
        raise UngueltigeEingabe("Unbekannter Status.")

    bedingungen = ["b.entfernt_am IS NULL"]
    werte: list = []

    if _text(text):
        muster = _like_muster(text.strip())
        bedingungen.append(
            "(norm(e.inhalt_name) LIKE ? ESCAPE '\\' OR norm(e.beschreibung) LIKE ? ESCAPE '\\'"
            " OR norm(b.code) LIKE ? ESCAPE '\\' OR norm(b.bezeichnung) LIKE ? ESCAPE '\\')"
        )
        werte += [muster, muster, muster, muster]
    if status == "belegt":
        bedingungen.append("e.id IS NOT NULL")
    elif status == "leer":
        bedingungen.append("e.id IS NULL")
    if fach_id not in (None, ""):
        bedingungen.append("e.fach_id = ?")
        werte.append(int(fach_id))
    if von_datum:
        bedingungen.append("substr(e.eingelagert_am, 1, 10) >= ?")
        werte.append(von_datum)
    if bis_datum:
        bedingungen.append("substr(e.eingelagert_am, 1, 10) <= ?")
        werte.append(bis_datum)

    rows = conn.execute(
        f"""SELECT b.code, b.bezeichnung,
                   e.id AS einlagerung_id, e.inhalt_name, e.beschreibung, e.foto_pfad,
                   e.eingelagert_am, e.eingelagert_von, e.fach_id, f.name AS fach_name
            FROM behaelter b
            LEFT JOIN einlagerung e ON e.behaelter_id = b.id AND e.ausgelagert_am IS NULL
            LEFT JOIN fach f ON f.id = e.fach_id
            WHERE {" AND ".join(bedingungen)}
            ORDER BY {SORTIERUNGEN[sortierung]}, b.code""",
        werte,
    )
    return [dict(r) | {"status": "belegt" if r["einlagerung_id"] else "leer"} for r in rows]


def zaehlen(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """SELECT COUNT(e.id) AS belegt, COUNT(*) - COUNT(e.id) AS frei
           FROM behaelter b
           LEFT JOIN einlagerung e ON e.behaelter_id = b.id AND e.ausgelagert_am IS NULL
           WHERE b.entfernt_am IS NULL"""
    ).fetchone()
    return {"belegt": row["belegt"], "frei": row["frei"]}


def letzte_einlagerung(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        """SELECT e.*, b.code, f.name AS fach_name
           FROM einlagerung e
           JOIN behaelter b ON b.id = e.behaelter_id
           LEFT JOIN fach f ON f.id = e.fach_id
           WHERE e.ausgelagert_am IS NULL AND b.entfernt_am IS NULL
           ORDER BY e.eingelagert_am DESC, e.id DESC LIMIT 1"""
    ).fetchone()
    return dict(row) if row else None


# --- Verwaltung: Behälterliste --------------------------------------------

VERWALTUNG_FILTER = {
    "alle": "b.entfernt_am IS NULL",
    "leer": "b.entfernt_am IS NULL AND e.id IS NULL",
    "belegt": "b.entfernt_am IS NULL AND e.id IS NOT NULL",
    "offen": "b.entfernt_am IS NULL AND b.gedruckt_am IS NULL",
    "stillgelegt": "b.entfernt_am IS NOT NULL",
}


def behaelter_liste(conn: sqlite3.Connection, filter: str = "alle") -> list[dict]:
    """Alle Behälter für die Verwaltung, neueste zuerst, mit aktuellem Inhalt."""
    if filter not in VERWALTUNG_FILTER:
        raise UngueltigeEingabe("Unbekannter Filter.")
    rows = conn.execute(
        f"""SELECT b.*, e.inhalt_name, f.name AS fach_name
            FROM behaelter b
            LEFT JOIN einlagerung e ON e.behaelter_id = b.id AND e.ausgelagert_am IS NULL
            LEFT JOIN fach f ON f.id = e.fach_id
            WHERE {VERWALTUNG_FILTER[filter]}
            ORDER BY b.erstellt_am DESC, b.id DESC"""
    )
    ergebnis = []
    for r in rows:
        status = "stillgelegt" if r["entfernt_am"] else ("belegt" if r["inhalt_name"] else "leer")
        ergebnis.append(dict(r) | {"status": status})
    return ergebnis


def behaelter_anzahl_je_filter(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        name: conn.execute(
            f"""SELECT COUNT(*) FROM behaelter b
                LEFT JOIN einlagerung e ON e.behaelter_id = b.id AND e.ausgelagert_am IS NULL
                WHERE {bedingung}"""
        ).fetchone()[0]
        for name, bedingung in VERWALTUNG_FILTER.items()
    }


def mehrere_stilllegen(conn: sqlite3.Connection, codes: list[str]) -> tuple[list[str], list[str]]:
    """Legt die leeren Behälter still. Gibt (stillgelegt, übersprungen) zurück."""
    erledigt, uebersprungen = [], []
    for code in codes:
        try:
            behaelter_stilllegen(conn, code)
            erledigt.append(code_normalisieren(code))
        except Fehler:
            uebersprungen.append(code_normalisieren(code))
    return erledigt, uebersprungen


def bezeichnung_setzen(conn: sqlite3.Connection, codes: list[str], bezeichnung: str | None) -> int:
    """Ändert nur die Bezeichnung (z. B. „Box blau, groß“) der aktiven Behälter. Inhalt und Historie bleiben
    unberührt. Leere Bezeichnung entfernt sie. Gibt die Anzahl geänderter Behälter zurück."""
    codes = aktive_codes(conn, codes)
    if not codes:
        return 0
    wert = _text(bezeichnung)
    with conn:
        conn.executemany(
            "UPDATE behaelter SET bezeichnung = ? WHERE code = ? AND entfernt_am IS NULL",
            [(wert[:60] if wert else None, code) for code in codes],
        )
    return len(codes)


def aktive_codes(conn: sqlite3.Connection, codes: list[str]) -> list[str]:
    """Filtert auf existierende, nicht stillgelegte Behälter; behält die Reihenfolge."""
    gesucht = [code_normalisieren(c) for c in codes if c and c.strip()]
    if not gesucht:
        return []
    platzhalter = ",".join("?" * len(gesucht))
    vorhanden = {
        r[0] for r in conn.execute(
            f"SELECT code FROM behaelter WHERE entfernt_am IS NULL AND code IN ({platzhalter})", gesucht
        )
    }
    gesehen = set()
    return [c for c in gesucht if c in vorhanden and not (c in gesehen or gesehen.add(c))]


def nicht_gedruckte_codes(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT code FROM behaelter WHERE entfernt_am IS NULL AND gedruckt_am IS NULL ORDER BY erstellt_am, id"
    )]


def daten_zuruecksetzen(conn: sqlite3.Connection) -> None:
    """Löscht alle Behälter und Einlagerungen. Fächer, Etikettengrößen und Einstellungen bleiben."""
    with conn:
        conn.execute("DELETE FROM einlagerung")
        conn.execute("DELETE FROM behaelter")
        conn.execute("DELETE FROM einstellung WHERE schluessel = 'letztes_fach'")


# --- Etikettengrößen ------------------------------------------------------


def etikettenformat(conn: sqlite3.Connection, format_id) -> dict | None:
    try:
        format_id = int(format_id)
    except (TypeError, ValueError):
        return None
    row = conn.execute("SELECT * FROM etikettenformat WHERE id = ?", (format_id,)).fetchone()
    return dict(row) if row else None


def etikettenformat_anlegen(conn: sqlite3.Connection, fmt: dict) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO etikettenformat
               (name, blatt_b_mm, blatt_h_mm, etikett_b_mm, etikett_h_mm, rand_mm, abstand_mm, schnittlinien)
               VALUES (:name, :blatt_b_mm, :blatt_h_mm, :etikett_b_mm, :etikett_h_mm, :rand_mm, :abstand_mm, :schnittlinien)""",
            fmt,
        )
    return cur.lastrowid


def etikettenformat_loeschen(conn: sqlite3.Connection, format_id: int) -> None:
    if conn.execute("SELECT COUNT(*) FROM etikettenformat").fetchone()[0] <= 1:
        raise UngueltigeEingabe("Die letzte Etikettengröße kann nicht gelöscht werden.")
    with conn:
        conn.execute("DELETE FROM etikettenformat WHERE id = ?", (int(format_id),))
        if einstellung(conn, "etikettenformat") == str(format_id):
            conn.execute("DELETE FROM einstellung WHERE schluessel = 'etikettenformat'")


# --- Fächer und Einstellungen --------------------------------------------


def faecher(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM fach ORDER BY sortierung, id")]


def fach_anlegen(conn: sqlite3.Connection, name: str) -> int:
    name = _text(name)
    if not name:
        raise UngueltigeEingabe("Bitte einen Namen für das Fach angeben.")
    with conn:
        naechste = conn.execute("SELECT COALESCE(MAX(sortierung), 0) + 1 FROM fach").fetchone()[0]
        return conn.execute("INSERT INTO fach (name, sortierung) VALUES (?, ?)", (name[:40], naechste)).lastrowid


def fach_umbenennen(conn: sqlite3.Connection, fach_id: int, name: str) -> None:
    name = _text(name)
    if not name:
        raise UngueltigeEingabe("Der Name des Fachs darf nicht leer sein.")
    fach_id = _fach_pruefen(conn, fach_id)
    with conn:
        conn.execute("UPDATE fach SET name = ? WHERE id = ?", (name[:40], fach_id))


def fach_verschieben(conn: sqlite3.Connection, fach_id: int, richtung: int) -> None:
    """richtung -1 = nach oben, +1 = nach unten. Vergibt die Sortierung danach lückenlos neu."""
    ids = [f["id"] for f in faecher(conn)]
    fach_id = _fach_pruefen(conn, fach_id)
    i = ids.index(fach_id)
    j = i + (1 if richtung > 0 else -1)
    if not 0 <= j < len(ids):
        return
    ids[i], ids[j] = ids[j], ids[i]
    with conn:
        conn.executemany("UPDATE fach SET sortierung = ? WHERE id = ?", [(n + 1, fid) for n, fid in enumerate(ids)])


def fach_loeschen(conn: sqlite3.Connection, fach_id: int) -> None:
    fach_id = _fach_pruefen(conn, fach_id)
    if conn.execute("SELECT 1 FROM einlagerung WHERE fach_id = ? LIMIT 1", (fach_id,)).fetchone():
        raise UngueltigeEingabe("Dieses Fach wurde schon verwendet und kann nur umbenannt werden.")
    with conn:
        conn.execute("DELETE FROM fach WHERE id = ?", (fach_id,))
        if einstellung(conn, "letztes_fach") == str(fach_id):
            conn.execute("DELETE FROM einstellung WHERE schluessel = 'letztes_fach'")


def letztes_fach(conn: sqlite3.Connection) -> int | None:
    wert = einstellung(conn, "letztes_fach")
    return int(wert) if wert else None


def einstellung(conn: sqlite3.Connection, schluessel: str, standard: str | None = None) -> str | None:
    row = conn.execute("SELECT wert FROM einstellung WHERE schluessel = ?", (schluessel,)).fetchone()
    return row["wert"] if row else standard


def _einstellung_setzen(conn: sqlite3.Connection, schluessel: str, wert: str | None) -> None:
    conn.execute(
        "INSERT INTO einstellung (schluessel, wert) VALUES (?, ?)"
        " ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
        (schluessel, wert),
    )


def einstellung_setzen(conn: sqlite3.Connection, schluessel: str, wert: str | None) -> None:
    with conn:
        _einstellung_setzen(conn, schluessel, wert)


def etikettenformate(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM etikettenformat ORDER BY id")]
