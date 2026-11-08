"""SQLite-Verbindung und Migrationen.

Migrationen liegen als app/migrations/NNN_name.sql vor und werden beim Start
in Nummernfolge genau einmal ausgeführt (Tabelle schema_version).
"""

import re
import secrets
import sqlite3
import unicodedata
from pathlib import Path

from flask import Flask, current_app, g

MIGRATIONS_ORDNER = Path(__file__).resolve().parent / "migrations"


def _norm(text):
    """Für die Suche: Groß/Klein egal, auch bei Umlauten (SQLite-LIKE kann das nur für ASCII)."""
    return text.casefold() if isinstance(text, str) else text


def _sortierschluessel(text):
    """Für die Sortierung: Ä wie A, ß wie ss – so wie man es im Deutschen erwartet."""
    if not isinstance(text, str):
        return text
    zerlegt = unicodedata.normalize("NFKD", text.casefold())
    return "".join(z for z in zerlegt if not unicodedata.combining(z))


def verbinden(pfad: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(pfad, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.create_function("norm", 1, _norm, deterministic=True)
    conn.create_function("sortiert", 1, _sortierschluessel, deterministic=True)
    return conn


def migrieren(pfad: Path) -> list[int]:
    """Führt fehlende Migrationen aus und gibt deren Nummern zurück."""
    conn = verbinden(pfad)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (nummer INTEGER PRIMARY KEY)")
        vorhanden = {r[0] for r in conn.execute("SELECT nummer FROM schema_version")}

        ausgefuehrt = []
        for datei in sorted(MIGRATIONS_ORDNER.glob("*.sql")):
            treffer = re.match(r"(\d+)_", datei.name)
            if not treffer:
                continue
            nummer = int(treffer.group(1))
            if nummer in vorhanden:
                continue
            sql = datei.read_text(encoding="utf-8")
            # executescript arbeitet außerhalb der Python-Transaktion, daher explizit klammern
            conn.executescript(
                f"BEGIN;\n{sql}\nINSERT INTO schema_version (nummer) VALUES ({nummer});\nCOMMIT;"
            )
            ausgefuehrt.append(nummer)
        return ausgefuehrt
    finally:
        conn.close()


def geheimer_schluessel(pfad: Path) -> str:
    """Zufälliger Schlüssel, beim ersten Start erzeugt und danach aus der Datenbank gelesen."""
    conn = verbinden(pfad)
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO einstellung (schluessel, wert) VALUES ('secret_key', ?)",
                (secrets.token_hex(32),),
            )
        return conn.execute("SELECT wert FROM einstellung WHERE schluessel = 'secret_key'").fetchone()[0]
    finally:
        conn.close()


def init_app(app: Flask, pfad: Path) -> None:
    app.config["DB_PFAD"] = pfad
    migrieren(pfad)
    app.teardown_appcontext(_schliessen)


def hole_db() -> sqlite3.Connection:
    """Eine Verbindung pro Anfrage."""
    if "db" not in g:
        g.db = verbinden(current_app.config["DB_PFAD"])
    return g.db


def _schliessen(_fehler=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
