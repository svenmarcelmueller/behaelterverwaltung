"""Etikettenblatt berechnen: Raster, Position jedes Aufklebers, Aufteilung von QR-Code und Text.

Alle Maße in Millimetern. Zwei Arten von Bögen:
- vorgestanzt (z. B. HERMA 9531): Spalten, Zeilen und Position stehen fest im Format.
- ungestanzte Folie (z. B. HERMA 9500): das Raster wird aus der Aufklebergröße berechnet und
  mittig gesetzt, die Schnittlinien laufen über das ganze Blatt.
"""

import math
from dataclasses import dataclass

GRENZEN = {
    "etikett_b_mm": (15, 200),
    "etikett_h_mm": (15, 280),
    "rand_mm": (0, 30),
    "abstand_mm": (0, 30),
}
QR_MINDESTENS_MM = 15  # darunter wird das Scannen aus normaler Entfernung unzuverlässig


@dataclass(frozen=True)
class Raster:
    spalten: int
    zeilen: int
    links_mm: float   # x des ersten Aufklebers
    oben_mm: float    # y des ersten Aufklebers
    etikett_b: float
    etikett_h: float
    abstand_x: float
    abstand_y: float
    blatt_b: float
    blatt_h: float
    vorgestanzt: bool = False

    @property
    def pro_blatt(self) -> int:
        return self.spalten * self.zeilen

    @property
    def passt(self) -> bool:
        return self.pro_blatt > 0

    @property
    def breite_mm(self) -> float:
        return self.spalten * self.etikett_b + max(self.spalten - 1, 0) * self.abstand_x

    @property
    def hoehe_mm(self) -> float:
        return self.zeilen * self.etikett_h + max(self.zeilen - 1, 0) * self.abstand_y

    def platz(self, index: int) -> tuple[float, float]:
        """Obere linke Ecke des Aufklebers Nr. index (zeilenweise von links oben)."""
        spalte, zeile = index % self.spalten, index // self.spalten
        return (
            round(self.links_mm + spalte * (self.etikett_b + self.abstand_x), 3),
            round(self.oben_mm + zeile * (self.etikett_h + self.abstand_y), 3),
        )

    def schnitt_x(self) -> list[float]:
        """Senkrechte Schnittlinien (x in mm), bei Abstand 0 genau eine Linie zwischen zwei Aufklebern."""
        werte = set()
        for s in range(self.spalten):
            x = self.links_mm + s * (self.etikett_b + self.abstand_x)
            werte.update((round(x, 3), round(x + self.etikett_b, 3)))
        return sorted(werte)

    def schnitt_y(self) -> list[float]:
        werte = set()
        for z in range(self.zeilen):
            y = self.oben_mm + z * (self.etikett_h + self.abstand_y)
            werte.update((round(y, 3), round(y + self.etikett_h, 3)))
        return sorted(werte)


def _anzahl(verfuegbar: float, groesse: float, abstand: float) -> int:
    if groesse <= 0 or verfuegbar < groesse:
        return 0
    # kleine Toleranz gegen Rundungsfehler (4 × 50 mm auf genau 200 mm)
    return math.floor((verfuegbar + abstand + 1e-6) / (groesse + abstand))


def raster(fmt: dict) -> Raster:
    b, h = float(fmt["etikett_b_mm"]), float(fmt["etikett_h_mm"])
    blatt_b, blatt_h = float(fmt["blatt_b_mm"]), float(fmt["blatt_h_mm"])
    abstand_x = float(fmt["abstand_mm"])
    abstand_y = float(fmt["abstand_y_mm"]) if fmt.get("abstand_y_mm") is not None else abstand_x
    gemeinsam = dict(etikett_b=b, etikett_h=h, abstand_x=abstand_x, abstand_y=abstand_y,
                     blatt_b=blatt_b, blatt_h=blatt_h)

    if fmt.get("spalten") and fmt.get("zeilen"):
        # Vorgestanzter Bogen: alles steht im Format
        return Raster(spalten=int(fmt["spalten"]), zeilen=int(fmt["zeilen"]),
                      links_mm=float(fmt["links_mm"] or 0), oben_mm=float(fmt["oben_mm"] or 0),
                      vorgestanzt=True, **gemeinsam)

    rand = float(fmt["rand_mm"])
    spalten = _anzahl(blatt_b - 2 * rand, b, abstand_x)
    zeilen = _anzahl(blatt_h - 2 * rand, h, abstand_y)
    breite = spalten * b + max(spalten - 1, 0) * abstand_x
    hoehe = zeilen * h + max(zeilen - 1, 0) * abstand_y
    return Raster(spalten=spalten, zeilen=zeilen,
                  links_mm=round((blatt_b - breite) / 2, 3), oben_mm=round((blatt_h - hoehe) / 2, 3),
                  **gemeinsam)


@dataclass(frozen=True)
class Aufteilung:
    """Wie QR-Code und Code-Text auf einem Aufkleber liegen (relativ zum Aufkleber)."""
    quer: bool        # True: QR links, Text rechts · False: QR oben, Text darunter
    qr_mm: float
    qr_x: float
    qr_y: float
    text_x: float
    text_y: float
    text_b: float
    text_h: float
    schrift_mm: float

    @property
    def qr_zu_klein(self) -> bool:
        return self.qr_mm < QR_MINDESTENS_MM


def innenabstand(b: float, h: float) -> float:
    """Ruhezone um den QR-Code: 3 mm bei großen Aufklebern, bei kleinen weniger (mindestens 1,5 mm),
    damit der QR-Code so groß wie möglich wird."""
    return round(min(3.0, max(1.5, min(b, h) * 0.07)), 2)


def aufteilung(b: float, h: float) -> Aufteilung:
    p = innenabstand(b, h)
    if b >= h * 1.4:
        # Querformat: QR-Code links über die volle Höhe, Code rechts daneben
        qr = h - 2 * p
        luecke = max(p, 2.5)  # rechts vom QR-Code frei lassen, sonst stört die Nummer beim Scannen
        text_x = p + qr + luecke
        text_b = b - text_x - p
        # 6 Zeichen Mono mit Sperrung ≈ 4,1 × Schriftgröße breit; Nummer wird im Rest zentriert
        schrift = min(qr * 0.28, text_b / 4.4, 9.0)
        return Aufteilung(True, round(qr, 2), p, p, round(text_x, 2), p, round(text_b, 2), round(qr, 2),
                          round(schrift, 2))

    schrift = min(max(h * 0.09, 3.0), (b - 2 * p) / 4.2, 7.0)
    text_h = schrift * 1.4
    qr = min(b - 2 * p, h - 2 * p - text_h)
    qr_x = (b - qr) / 2
    return Aufteilung(False, round(qr, 2), round(qr_x, 2), p, p, round(p + qr, 2), round(b - 2 * p, 2),
                      round(h - p - (p + qr), 2), round(schrift, 2))


def startplatz(wert, r: Raster) -> int:
    """Index des ersten freien Platzes auf einem angebrochenen Bogen. Eingabe zählt ab 1 wie auf dem Bogen;
    alles Ungültige oder außerhalb des Bogens heißt: von vorn beginnen."""
    try:
        nummer = int(wert)
    except (TypeError, ValueError):
        return 0
    return nummer - 1 if r.passt and 1 <= nummer <= r.pro_blatt else 0


def seiten(codes: list[str], r: Raster, start: int = 0) -> list[list[dict]]:
    """Verteilt Codes zeilenweise auf Blätter; jedes Blatt eine Liste {code, x, y}.
    Auf dem ersten Blatt werden die Plätze vor `start` übersprungen (schon abgezogene Aufkleber)."""
    if not r.passt:
        return []
    blaetter = []
    for erster in range(0, start + len(codes), r.pro_blatt):
        plaetze = range(max(erster, start), min(erster + r.pro_blatt, start + len(codes)))
        blaetter.append([{"code": codes[p - start], **dict(zip(("x", "y"), r.platz(p - erster)))}
                         for p in plaetze])
    return blaetter


def blattzahl(anzahl_codes: int, r: Raster, start: int = 0) -> int:
    if not r.passt or anzahl_codes == 0:
        return 0
    return -(-(start + anzahl_codes) // r.pro_blatt)


def freie_plaetze(anzahl_codes: int, r: Raster, start: int = 0) -> int:
    """Wie viele Plätze auf dem letzten Blatt leer bleiben."""
    if not r.passt or anzahl_codes == 0:
        return 0
    rest = (start + anzahl_codes) % r.pro_blatt
    return 0 if rest == 0 else r.pro_blatt - rest


def format_pruefen(werte: dict) -> tuple[dict, list[str]]:
    """Eingaben aus dem Formular in Zahlen umwandeln und prüfen. Gibt (format, fehler) zurück."""
    fehler = []
    fmt = {"name": (werte.get("name") or "").strip()[:60], "blatt_b_mm": 210.0, "blatt_h_mm": 297.0}
    for feld, (minimum, maximum) in GRENZEN.items():
        roh = str(werte.get(feld, "")).strip().replace(",", ".")
        try:
            zahl = float(roh)
        except ValueError:
            fehler.append(f"{_feldname(feld)}: bitte eine Zahl eingeben.")
            continue
        if not minimum <= zahl <= maximum:
            fehler.append(f"{_feldname(feld)}: erlaubt sind {minimum} bis {maximum} mm.")
        fmt[feld] = zahl
    fmt["schnittlinien"] = 1 if werte.get("schnittlinien") else 0
    if not fehler:
        if not fmt["name"]:
            fmt["name"] = f"HERMA 9500 · {fmt['etikett_b_mm']:g} × {fmt['etikett_h_mm']:g} mm"
        if not raster(fmt).passt:
            fehler.append("Mit diesem Rand passt kein einziger Aufkleber auf das Blatt.")
    return fmt, fehler


def _feldname(feld: str) -> str:
    return {"etikett_b_mm": "Breite", "etikett_h_mm": "Höhe", "rand_mm": "Rand", "abstand_mm": "Abstand"}[feld]
