CREATE TABLE behaelter (
  id            INTEGER PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,      -- 6 Zeichen, ohne 0/O/1/I
  bezeichnung   TEXT,
  erstellt_am   TEXT NOT NULL,             -- ISO 8601
  gedruckt_am   TEXT,                      -- NULL = Etikett noch nicht gedruckt
  entfernt_am   TEXT                       -- NULL = aktiv, sonst stillgelegt
);

CREATE TABLE fach (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  sortierung  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE einlagerung (
  id               INTEGER PRIMARY KEY,
  behaelter_id     INTEGER NOT NULL REFERENCES behaelter(id),
  fach_id          INTEGER REFERENCES fach(id),
  inhalt_name      TEXT NOT NULL,
  beschreibung     TEXT,
  foto_pfad        TEXT,
  eingelagert_am   TEXT NOT NULL,
  eingelagert_von  TEXT,
  ausgelagert_am   TEXT,
  ausgelagert_von  TEXT
);
CREATE UNIQUE INDEX uq_ein_aktiver_inhalt
  ON einlagerung(behaelter_id) WHERE ausgelagert_am IS NULL;
CREATE INDEX ix_einlagerung_datum ON einlagerung(eingelagert_am);

CREATE TABLE etikettenformat (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  blatt_b_mm    REAL NOT NULL DEFAULT 210, blatt_h_mm REAL NOT NULL DEFAULT 297,
  etikett_b_mm  REAL NOT NULL,  etikett_h_mm  REAL NOT NULL,
  rand_mm       REAL NOT NULL DEFAULT 5,    -- nicht bedruckbarer Rand des Laserdruckers
  abstand_mm    REAL NOT NULL DEFAULT 0,    -- 0 = Aufkleber stoßen aneinander, ein Schnitt pro Linie
  schnittlinien INTEGER NOT NULL DEFAULT 1  -- dünne graue Linien zum Ausschneiden
);

CREATE TABLE einstellung (
  schluessel  TEXT PRIMARY KEY,
  wert        TEXT
);

INSERT INTO fach (name, sortierung) VALUES ('Oben', 1), ('Mitte', 2), ('Unten', 3);

INSERT INTO etikettenformat (name, etikett_b_mm, etikett_h_mm) VALUES
  ('HERMA 9500 · 50 × 50 mm', 50, 50),
  ('HERMA 9500 · 40 × 40 mm', 40, 40),
  ('HERMA 9500 · 60 × 40 mm', 60, 40);
