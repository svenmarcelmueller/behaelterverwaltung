# Behälterverwaltung (Home-Assistant-App)

Lokale HA-App in Python (Flask, Jinja, htmx, SQLite), mit der Behälter per QR-Code ein- und ausgelagert werden.

- Aufbau als HA-App-Repository: `repository.yaml` im Hauptordner, die App selbst in `behaelterverwaltung/` (config.yaml, Dockerfile, run.sh, app/ …). Tests, Skripte und Konzept liegen im Hauptordner.
- Konzept, Datenmodell, Routen und Etappen: [konzept/UMSETZUNGSPLAN.md](konzept/UMSETZUNGSPLAN.md) (nur lokal, nicht im Git-Repository)
- UI-Entwurf (HTML-Mockups): [konzept/entwurf/](konzept/entwurf/)
  - `Main.dc.html` Scan, Behälter leer (Einlagern) · `Belegt.dc.html` Scan, Behälter belegt
  - `Uebersicht.dc.html` Übersicht iPhone · `Uebersicht-Desktop.dc.html` Übersicht breit / HA-Seitenleiste
  - `Scannen-Hilfe.dc.html` Hilfe · `Verwaltung-Behaelter.dc.html` · `Verwaltung-Etiketten.dc.html`
- Gestaltung laut Entwurf: IBM Plex Sans / IBM Plex Mono, Hintergrund `#F3F4F1`, Text `#1B1F23`, Akzent `#1D5FA8`, Status belegt `#FBE9D7`/`#8A3B00`, leer `#E2F0EA`/`#1E5C3F`.
- Sprache der Oberfläche und des Codes (Bezeichner): Deutsch.
- Umsetzung strikt nach Etappen; eine Etappe erst abschließen, wenn ihr „Fertig, wenn“ erfüllt ist.
- Lokal (im Hauptordner): `.venv\Scripts\python.exe -m pytest` · Start: `cd behaelterverwaltung; ..\.venv\Scripts\python.exe -m app --dev --ingress-port 8097` (8098 ist auf dem PC belegt; Daten in `behaelterverwaltung/dev-data`).
- Version steht in `behaelterverwaltung/config.yaml` und `behaelterverwaltung/app/__init__.py`; beide gleich halten (Test prüft das). Ohne neue Version zeigt HA kein Update an – auch nicht bei Installation über das GitHub-Repository.
- `run.sh` muss LF-Zeilenenden haben (`.gitattributes`).
- Deploy auf das eigene HA: `powershell -ExecutionPolicy Bypass -File .\deploy.ps1 -Ziel <HA-IP>` (ersetzt den Ordner auf HA vollständig; braucht die SSH-App).
- Veröffentlichen: committen und `git push`; wer die App über das Repository installiert hat, bekommt dann das Update angeboten.
