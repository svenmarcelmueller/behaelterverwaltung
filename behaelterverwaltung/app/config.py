"""Einstellungen der App: Datenordner, Ports und Optionen aus Home Assistant."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("behaelterverwaltung")

PROJEKT_ORDNER = Path(__file__).resolve().parent.parent

INGRESS_PORT = 8098
DIREKT_PORT = 8099

# Unter Home Assistant kommen Ingress-Anfragen ausschließlich vom Supervisor.
SUPERVISOR_IP = "172.30.32.2"


@dataclass(frozen=True)
class Einstellungen:
    daten_ordner: Path
    dev: bool
    basis_url: str | None


def lade_einstellungen(dev: bool = False) -> Einstellungen:
    daten_ordner = PROJEKT_ORDNER / "dev-data" if dev else Path("/data")
    daten_ordner.mkdir(parents=True, exist_ok=True)

    optionen = {}
    optionen_datei = daten_ordner / "options.json"
    if optionen_datei.exists():
        optionen = json.loads(optionen_datei.read_text(encoding="utf-8"))

    return Einstellungen(
        daten_ordner=daten_ordner,
        dev=dev,
        basis_url=basis_url_pruefen(optionen.get("basis_url")),
    )


def basis_url_pruefen(wert: str | None) -> str | None:
    """Leer oder ungültig → None (dann gibt es keine QR-Codes, die App läuft trotzdem)."""
    wert = (wert or "").strip().rstrip("/")
    if not wert:
        return None
    if not re.fullmatch(r"https?://[^\s/]+(:\d+)?(/[^\s]*)?", wert):
        log.warning("Basis-URL %r ist ungültig, erwartet z. B. http://192.168.1.10:8099", wert)
        return None
    return wert
