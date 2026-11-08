"""Startet beide Zugänge in einem Prozess.

    python -m app          im Container (Daten in /data)
    python -m app --dev    lokal auf dem PC (Daten in ./dev-data)
"""

import argparse
import logging
import threading

from waitress import create_server

from . import __version__, db
from .config import DIREKT_PORT, INGRESS_PORT, lade_einstellungen
from .factory import create_app
from .ha import HaSensoren


def main():
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("--dev", action="store_true", help="lokal entwickeln, Daten in ./dev-data")
    parser.add_argument("--ingress-port", type=int, default=INGRESS_PORT)
    parser.add_argument("--direkt-port", type=int, default=DIREKT_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("behaelterverwaltung")

    einstellungen = lade_einstellungen(dev=args.dev)
    db.migrieren(einstellungen.daten_ordner / "behaelter.db")
    ha = HaSensoren.aus_umgebung(einstellungen.daten_ordner / "behaelter.db", dev=args.dev)

    # create_server bindet den Port sofort: ist einer belegt, bricht der Start hier komplett ab.
    ingress = create_server(create_app("ingress", einstellungen, ha), host="0.0.0.0", port=args.ingress_port, ident=None)
    direkt = create_server(create_app("direkt", einstellungen, ha), host="0.0.0.0", port=args.direkt_port, ident=None)

    if ha:
        ha.starten()

    log.info("Version %s, Daten in %s", __version__, einstellungen.daten_ordner)
    log.info("Ingress-Zugang auf Port %s, Direktzugang auf Port %s", args.ingress_port, args.direkt_port)

    threading.Thread(target=ingress.run, daemon=True, name="ingress").start()
    direkt.run()


if __name__ == "__main__":
    main()
