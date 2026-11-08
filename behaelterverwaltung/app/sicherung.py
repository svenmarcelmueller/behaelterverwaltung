"""Alle Daten als JSON-Datei herunterladen und in eine leere App wieder einspielen.

Gedacht für den Umzug (z. B. von der lokal kopierten App zur Installation aus dem
GitHub-Repository) und als zusätzliche Sicherung. Eingespielt wird nur in eine App ohne
Behälter, damit nie etwas überschrieben wird; entweder kommt alles an oder gar nichts.
"""

import sqlite3

from . import __version__
from .repo import Fehler, jetzt

FORMAT = "behaelterverwaltung-export"
# Reihenfolge = Einfüge-Reihenfolge (Fremdschlüssel: Einlagerung → Behälter, Fach)
TABELLEN = ("fach", "etikettenformat", "behaelter", "einlagerung", "einstellung")
NICHT_EXPORTIEREN = {"secret_key"}  # jede App behält ihren eigenen Schlüssel


class ImportFehler(Fehler):
    meldung = "Die Datei konnte nicht eingespielt werden."


def _schema(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT nummer FROM schema_version ORDER BY nummer")]


def _spalten(conn: sqlite3.Connection, tabelle: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})")}


def exportieren(conn: sqlite3.Connection) -> dict:
    tabellen = {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in TABELLEN}
    tabellen["einstellung"] = [e for e in tabellen["einstellung"] if e["schluessel"] not in NICHT_EXPORTIEREN]
    return {
        "format": FORMAT,
        "version": __version__,
        "schema": _schema(conn),
        "exportiert_am": jetzt(),
        "tabellen": tabellen,
    }


def ist_leer(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM behaelter").fetchone()[0] == 0


def importieren(conn: sqlite3.Connection, daten) -> dict[str, int]:
    """Spielt einen Export ein. Ersetzt Fächer, Aufklebergrößen und Einstellungen der leeren App.
    Gibt die Anzahl eingespielter Zeilen je Tabelle zurück."""
    if not isinstance(daten, dict) or daten.get("format") != FORMAT:
        raise ImportFehler("Das ist keine Exportdatei der Behälterverwaltung.")
    if daten.get("schema") != _schema(conn):
        raise ImportFehler(
            f"Die Datei stammt aus Version {daten.get('version', '?')} mit anderem Datenbankaufbau. "
            f"Bitte beide Apps auf dieselbe Version bringen (hier: {__version__}) und neu exportieren.")
    tabellen = daten.get("tabellen")
    if not isinstance(tabellen, dict) or not all(isinstance(tabellen.get(t), list) for t in TABELLEN):
        raise ImportFehler("Die Datei ist unvollständig.")
    if not ist_leer(conn):
        raise ImportFehler("Einspielen geht nur, solange hier noch keine Behälter angelegt sind.")

    for tabelle in TABELLEN:
        erlaubt = _spalten(conn, tabelle)
        for zeile in tabellen[tabelle]:
            # Spaltennamen landen im SQL – deshalb nur bekannte zulassen
            if not isinstance(zeile, dict) or not zeile or not set(zeile) <= erlaubt:
                raise ImportFehler(f"Die Datei enthält ungültige Einträge ({tabelle}).")

    try:
        with conn:
            conn.execute("DELETE FROM fach")
            conn.execute("DELETE FROM etikettenformat")
            conn.execute("DELETE FROM einstellung WHERE schluessel NOT IN ('secret_key')")
            for tabelle in TABELLEN:
                for zeile in tabellen[tabelle]:
                    if tabelle == "einstellung" and zeile.get("schluessel") in NICHT_EXPORTIEREN:
                        continue
                    spalten = list(zeile)
                    conn.execute(
                        f"INSERT INTO {tabelle} ({', '.join(spalten)}) VALUES ({', '.join('?' * len(spalten))})",
                        [zeile[s] for s in spalten],
                    )
    except sqlite3.Error as fehler:
        raise ImportFehler(f"Die Datei passt nicht zusammen, es wurde nichts eingespielt ({fehler}).") from fehler

    return {t: len(tabellen[t]) for t in TABELLEN}
