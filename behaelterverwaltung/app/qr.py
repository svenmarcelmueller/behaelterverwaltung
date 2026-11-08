"""QR-Codes als SVG (ohne Bildbibliothek)."""

import io

import segno


def behaelter_url(basis_url: str, code: str) -> str:
    return f"{basis_url.rstrip('/')}/b/{code}"


def svg(text: str, groesse_mm: float | None = None) -> str:
    """SVG ohne XML-Kopf zum Einbetten ins HTML; mit groesse_mm in Millimetern für den Druck."""
    qr = segno.make(text, error="m", micro=False)
    puffer = io.BytesIO()
    if groesse_mm:
        # Ohne Ruhezone: die liefert beim Druck der Rand des Aufklebers
        qr.save(puffer, kind="svg", xmldecl=False, svgns=True, nl=False, border=0, omitsize=True, dark="#000")
        bild = puffer.getvalue().decode("utf-8")
        return bild.replace("<svg ", f'<svg width="{groesse_mm:g}mm" height="{groesse_mm:g}mm" ', 1)
    qr.save(puffer, kind="svg", xmldecl=False, svgns=True, nl=False, border=2,
            omitsize=True, dark="#000", light="#fff")
    return puffer.getvalue().decode("utf-8")
