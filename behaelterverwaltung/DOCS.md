# Behälterverwaltung

Behälter bekommen einen Aufkleber mit QR-Code. Wer ihn mit dem iPhone scannt, sieht den Inhalt oder lagert etwas ein.

## Zugänge

- **Seitenleiste „Behälter“** (mit Home-Assistant-Login): Nutzung und Verwaltung.
- **Port 8099** (ohne Login, nur im Heimnetz): nur Nutzung. Diese Adresse steht in den QR-Codes.

## Einrichten

1. Unter **Konfiguration** die **Basis-URL** eintragen: `http://<IP von Home Assistant>:8099`, z. B. `http://192.168.1.10:8099`. Diese Adresse wird in die QR-Codes gedruckt. Die IP von Home Assistant sollte deshalb im Router fest reserviert sein.
2. App starten und **In Seitenleiste anzeigen** einschalten.
3. In der Seitenleiste unter **Behälter → Verwaltung** Fächer anpassen, Behälter anlegen und Etiketten drucken.
4. Etikett auf den Behälter kleben, mit der iPhone-Kamera scannen und einlagern.

Die Daten liegen im App-eigenen Speicher und bleiben bei Updates erhalten. Sie sind in den Home-Assistant-Sicherungen enthalten.

## Daten sichern und umziehen

Unter **Verwaltung → Einstellungen → Daten herunterladen** gibt es eine Datei mit allen Daten. Die Daten sind außerdem in jeder Home-Assistant-Sicherung enthalten.

Umzug in eine neu installierte App, z. B. von einer selbst kopierten Version zur Installation aus diesem Repository:

1. Beide Apps auf **dieselbe Version** bringen.
2. Zur Sicherheit eine Home-Assistant-Teilsicherung der alten App anlegen.
3. In der alten App **Daten herunterladen**.
4. Die alte App **stoppen**, denn beide nutzen Port 8099. Danach die neue App starten und dieselbe Basis-URL eintragen.
5. In der neuen App unter Einstellungen die Datei **einspielen**. Das geht nur, solange dort noch keine Behälter angelegt sind.
6. Prüfen, ob alles da ist, und ein Etikett scannen. Die gedruckten QR-Codes gelten weiter.
7. Erst dann die alte App deinstallieren.

## Einstellungen

- **Basis-URL:** Adresse für die QR-Codes, z. B. `http://192.168.1.10:8099`.

## Sensoren

Die App setzt nach jeder Änderung und alle 5 Minuten:

| Sensor | Zustand | Attribute |
|---|---|---|
| `sensor.behaelter_frei` | Anzahl leerer Behälter | – |
| `sensor.behaelter_belegt` | Anzahl belegter Behälter | `je_fach` (z. B. `{"Oben": 3, "Mitte": 5}`) |
| `sensor.behaelter_letzte_einlagerung` | Name des zuletzt eingelagerten Inhalts | `code`, `fach`, `von`, `zeitpunkt` |

Hinweis: Die Sensoren haben keine eindeutige ID und lassen sich daher in der Oberfläche nicht umbenennen. Nach einem Neustart von Home Assistant sind sie bis zu 5 Minuten lang „nicht verfügbar“, bis die App sie erneut setzt.

### Beispielkarte fürs Dashboard

Dashboard bearbeiten → Karte hinzufügen → „Manuell“ und einfügen:

```yaml
type: vertical-stack
cards:
  - type: glance
    title: Schrank
    entities:
      - entity: sensor.behaelter_belegt
        name: Belegt
      - entity: sensor.behaelter_frei
        name: Frei
  - type: markdown
    content: >
      **Zuletzt eingelagert:** {{ states('sensor.behaelter_letzte_einlagerung') }}
      {%- set a = states.sensor.behaelter_letzte_einlagerung.attributes %}
      {%- if a.code %} – Fach {{ a.fach or '–' }}, Behälter `{{ a.code }}`
      {%- if a.von %}, von {{ a.von }}{% endif %}
      ({{ as_timestamp(a.zeitpunkt) | timestamp_custom('%d.%m. %H:%M') }}){% endif %}
```

### Beispiel-Automation: Bescheid geben, wenn die Behälter knapp werden

```yaml
alias: Behälter werden knapp
triggers:
  - trigger: numeric_state
    entity_id: sensor.behaelter_frei
    below: 3
actions:
  - action: notify.notify
    data:
      message: "Nur noch {{ states('sensor.behaelter_frei') }} freie Behälter – neue Etiketten drucken?"
```
