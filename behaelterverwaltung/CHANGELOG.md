# Changelog

## 0.9.0

- Verwaltung → Einstellungen: **Daten herunterladen** als JSON-Datei (Behälter, Einlagerungen samt Historie, Fächer, Aufklebergrößen, Einstellungen) und **Daten einspielen** in eine neu installierte App. Einspielen geht nur, solange noch keine Behälter angelegt sind, und gelingt ganz oder gar nicht. Anleitung zum Umzug in der Dokumentation.
- Keine Änderung am Datenbankschema.

## 0.8.0

- Etiketten: **angebrochene Bögen weiterverwenden.** Unter „Angebrochener Bogen: beginnen bei“ den ersten noch vorhandenen Aufkleber wählen (oder in der Vorschau antippen). Die Plätze davor bleiben auf dem ersten Bogen frei, weitere Bögen beginnen wieder oben links. „Auffüllen“ füllt nur den Rest des Bogens.
- Übersicht: Die Bezeichnung des Behälters (z. B. „Box blau, groß“) steht in einer eigenen Zeile mit Behälter-Symbol, auch bei belegten Behältern, und die Suche findet sie. Das Einlagerungsdatum steht jetzt direkt hinter dem Inhalt („Brot – 07.11.2026“), darunter Fach und Name.
- Keine Änderung am Datenbankschema.

## 0.7.1

- Der Eintrag „Behälter“ in der Home-Assistant-Seitenleiste ist jetzt für alle Benutzer sichtbar, nicht nur für Administratoren (`panel_admin: false`).
- Keine Änderung am Datenbankschema.

## 0.7.0

- Verwaltung → Behälter: Bezeichnung der ausgewählten Behälter nachträglich ändern oder entfernen. Inhalt, Historie und Druckstatus bleiben unverändert.
- Beispieltext im Feld „Inhalt“ beim Einlagern: „z. B. Gemüse, Fleisch“.
- Keine Änderung am Datenbankschema.

## 0.6.0

- Neue Etikettenvorlage **HERMA 9531** (Outdoor-Folienetiketten, 45,7 × 21,2 mm, 4 × 12 = 48 pro A4-Bogen, vorgestanzt): QR-Code links über die volle Höhe, Nummer rechts daneben, keine Schnittlinien.
- Die drei Vorlagen für HERMA 9500 wurden entfernt; eigene Größen auf ungestanzter Folie lassen sich weiterhin anlegen (bereits angelegte bleiben erhalten).
- Bei kleinen Etiketten wird die Ruhezone um den QR-Code verkleinert (mindestens 1,5 mm), damit der QR-Code größer wird; zwischen QR-Code und Nummer bleiben mindestens 2,5 mm frei.

## 0.5.0

- Sensoren in Home Assistant: `sensor.behaelter_frei`, `sensor.behaelter_belegt` (mit Anzahl je Fach), `sensor.behaelter_letzte_einlagerung` (mit Code, Fach, Person, Zeitpunkt).
- Aktualisierung nach jeder Änderung und alle 5 Minuten (überbrückt Neustarts von Home Assistant).
- Verwaltung → Einstellungen zeigt, wann zuletzt gesendet wurde, und kann sofort senden.
- Dokumentation mit Beispielkarte fürs Dashboard und Beispiel-Automation.

## 0.4.0

- Verwaltung mit Unterseiten Behälter, Etiketten, Fächer, Einstellungen (nur über die Seitenleiste).
- Behälter: mehrere auf einmal anlegen, Filter (leer, belegt, Etikett nicht gedruckt, stillgelegt), Mehrfachauswahl zum Drucken oder Stilllegen.
- Etiketten für HERMA 9500: Aufklebergröße frei wählbar, Raster wird berechnet und mittig gesetzt, Schnittlinien, QR-Code passt sich der Größe an; Vorschau; freie Plätze optional mit neuen Behältern auffüllen; Druckseite in Millimetern; „Als gedruckt markieren“.
- Fächer anlegen, umbenennen, sortieren, löschen (nur unbenutzte).
- Einstellungen: Druckversatz, alle Behälter löschen (z. B. nach der Testphase).
- Der vorläufige Knopf „Testbehälter anlegen“ ist entfallen.

## 0.3.3

- Formulare (Einlagern, Ausbuchen, Korrigieren) werden im Hintergrund gesendet: keine Safari-Warnung „nicht sichere Verbindung“ mehr auf dem iPhone.
- Fehlermeldungen (z. B. Behälter inzwischen belegt) werden dabei weiterhin angezeigt.
- Hinweis, wenn die Behälterverwaltung nicht erreichbar ist.

## 0.3.2

- Keine inhaltlichen Änderungen; Neubau, weil 0.3.1 aus einer unvollständigen Kopie gebaut worden war.

## 0.3.1

- Feld „Basis-URL“ ist in der Konfiguration jetzt immer sichtbar; ungültige Eingaben werden im Protokoll gemeldet.

## 0.3.0

- Scan-Seite `/b/<code>`: Einlagern (Fach-Kacheln, zuletzt genutztes Fach), Inhalt anzeigen, Ausbuchen mit Rückfrage, Korrigieren, Historie; eigene Seiten für unbekannte und stillgelegte Codes.
- Übersicht mit Live-Suche, Fach-, Status- und Zeitraumfilter, Sortierung; Kennzahlen auf breiten Bildschirmen.
- Hilfe-Seite „So scannst du“ mit Code-Eingabe von Hand.
- Name pro Gerät (nur lokal gespeichert), CSRF-Schutz, Schutz vor Doppel-Tap.
- Gestaltung nach Entwurf mit hellem und dunklem Design; Schriften und htmx werden lokal mitgeliefert.

## 0.2.0

- Datenbank (SQLite in `/data/behaelter.db`) mit Migrationen; Startdaten: Fächer Oben/Mitte/Unten, drei Etikettengrößen für HERMA 9500.
- Kernlogik: Behälter anlegen und stilllegen, einlagern, ausbuchen, korrigieren, Historie, Suche mit Filtern und Sortierung.
- Platzhalterseiten zeigen belegte und freie Behälter; vorübergehend Knopf „Testbehälter anlegen“ in der Verwaltung.

## 0.1.0

- Grundgerüst: App startet Ingress-Zugang (Seitenleiste) und Direktzugang auf Port 8099 mit Platzhalterseite.
