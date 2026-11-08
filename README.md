# Behälterverwaltung für Home Assistant

Behälter im Schrank oder in der Gefriertruhe bekommen einen Aufkleber mit QR-Code. Wer ihn mit dem Handy scannt, sieht sofort, was drin ist, oder lagert etwas ein. Ohne App auf dem Handy und ohne Login, nur im Heimnetz.

- Einlagern und entnehmen per QR-Code, mit Fach, Datum und Name
- Übersicht mit Suche, Filter nach Fach, Status und Zeitraum
- Etiketten selbst drucken (z. B. HERMA 9531 oder eigene Größen), auch angebrochene Bögen
- Sensoren in Home Assistant: freie und belegte Behälter, letzte Einlagerung

Die Oberfläche ist auf Deutsch.

## Installation

[![Repository in Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsvenmarcelmueller%2Fbehaelterverwaltung)

Oder von Hand:

1. In Home Assistant **Einstellungen → Apps → App installieren** öffnen.
2. Oben rechts im Menü **Repositories** wählen und `https://github.com/svenmarcelmueller/behaelterverwaltung` hinzufügen.
3. **Behälterverwaltung** in der Liste suchen und installieren. Beim ersten Mal baut Home Assistant die App selbst, das dauert ein paar Minuten.
4. Weiter geht's im Reiter **Dokumentation** der App.

Neue Versionen erscheinen danach wie bei jeder anderen App als Update.

## Entwicklung

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

## Lizenz

[MIT](LICENSE). Enthält [htmx](https://htmx.org) (0BSD) und die Schriften IBM Plex Sans/Mono ([SIL Open Font License](behaelterverwaltung/app/static/vendor/fonts/OFL.txt)).
