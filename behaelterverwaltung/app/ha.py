"""Sensoren in Home Assistant setzen (über die Supervisor-API bzw. die REST-API von HA).

Ein Hintergrund-Thread schickt die Werte nach jeder Änderung (kurz gebündelt) und
zusätzlich alle paar Minuten – Zustände, die per API gesetzt werden, überstehen
einen Neustart von Home Assistant nicht und würden sonst bis zur nächsten
Einlagerung fehlen.
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests

from . import db, repo

log = logging.getLogger("behaelterverwaltung.ha")

SUPERVISOR_URL = "http://supervisor/core/api"
INTERVALL_S = 300       # regelmäßig neu senden
BUENDELN_S = 0.5        # mehrere Änderungen kurz hintereinander zu einem Senden zusammenfassen
NACH_FEHLER_S = 30      # nach einem Fehler früher erneut versuchen

Sender = Callable[[str, dict], None]


def sensoren(conn) -> dict[str, dict]:
    """Zustand und Attribute aller Sensoren, berechnet aus der Datenbank."""
    zahlen = repo.zaehlen(conn)
    je_fach = {
        r["name"]: r["anzahl"]
        for r in conn.execute(
            """SELECT f.name, COUNT(e.id) AS anzahl
               FROM fach f
               LEFT JOIN einlagerung e ON e.fach_id = f.id AND e.ausgelagert_am IS NULL
               GROUP BY f.id ORDER BY f.sortierung, f.id"""
        )
    }
    letzte = repo.letzte_einlagerung(conn)

    gemeinsam = {"unit_of_measurement": "Behälter", "state_class": "measurement"}
    return {
        "sensor.behaelter_frei": {
            "state": zahlen["frei"],
            "attributes": {**gemeinsam, "friendly_name": "Behälter frei", "icon": "mdi:package-variant"},
        },
        "sensor.behaelter_belegt": {
            "state": zahlen["belegt"],
            "attributes": {**gemeinsam, "friendly_name": "Behälter belegt", "icon": "mdi:package-variant-closed",
                           "je_fach": je_fach},
        },
        "sensor.behaelter_letzte_einlagerung": {
            "state": (letzte["inhalt_name"][:250] if letzte else "–"),
            "attributes": {
                "friendly_name": "Letzte Einlagerung",
                "icon": "mdi:tray-arrow-down",
                "code": letzte["code"] if letzte else None,
                "fach": letzte["fach_name"] if letzte else None,
                "von": letzte["eingelagert_von"] if letzte else None,
                "zeitpunkt": letzte["eingelagert_am"] if letzte else None,
            },
        },
    }


def http_sender(basis_url: str, token: str) -> Sender:
    sitzung = requests.Session()
    sitzung.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def senden(entity_id: str, daten: dict) -> None:
        antwort = sitzung.post(f"{basis_url.rstrip('/')}/states/{entity_id}", json=daten, timeout=10)
        antwort.raise_for_status()

    return senden


class HaSensoren:
    def __init__(self, db_pfad: Path, sender: Sender):
        self.db_pfad = db_pfad
        self.sender = sender
        self.letzter_erfolg: str | None = None
        self.letzter_fehler: str | None = None
        self._anstoss = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def aus_umgebung(cls, db_pfad: Path, dev: bool) -> "HaSensoren | None":
        """Im Container: Supervisor-Token. Lokal (dev) optional HA_URL und HA_TOKEN (Langzeit-Token)."""
        if os.environ.get("HA_URL") and os.environ.get("HA_TOKEN"):
            return cls(db_pfad, http_sender(os.environ["HA_URL"], os.environ["HA_TOKEN"]))
        if not dev and os.environ.get("SUPERVISOR_TOKEN"):
            return cls(db_pfad, http_sender(SUPERVISOR_URL, os.environ["SUPERVISOR_TOKEN"]))
        log.info("Keine Verbindung zu Home Assistant eingerichtet – Sensoren werden nicht gesetzt.")
        return None

    def anstossen(self) -> None:
        self._anstoss.set()

    def jetzt_senden(self) -> bool:
        conn = db.verbinden(self.db_pfad)
        try:
            werte = sensoren(conn)
        finally:
            conn.close()
        try:
            for entity_id, daten in werte.items():
                self.sender(entity_id, daten)
        except Exception as fehler:  # Netzwerk, HA nicht erreichbar, falscher Token …
            meldung = f"{datetime.now():%d.%m.%Y %H:%M}: {fehler}"
            if meldung.split(": ", 1)[1] != (self.letzter_fehler or "").split(": ", 1)[-1]:
                log.warning("Sensoren konnten nicht gesetzt werden: %s", fehler)
            self.letzter_fehler = meldung
            return False
        if self.letzter_fehler:
            log.info("Sensoren werden wieder gesetzt.")
        self.letzter_fehler = None
        self.letzter_erfolg = f"{datetime.now():%d.%m.%Y %H:%M:%S}"
        return True

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._schleife, daemon=True, name="ha-sensoren")
        self._thread.start()
        self.anstossen()

    def _schleife(self) -> None:
        warten = INTERVALL_S
        while True:
            self._anstoss.wait(timeout=warten)
            time.sleep(BUENDELN_S)
            self._anstoss.clear()
            warten = INTERVALL_S if self.jetzt_senden() else NACH_FEHLER_S
