-- Vorgestanzte Etikettenbögen: feste Spalten/Zeilen und feste Position statt berechnetem, mittigem Raster.
-- NULL in den neuen Spalten = wie bisher (ungestanzte Folie, Raster wird berechnet).
ALTER TABLE etikettenformat ADD COLUMN spalten INTEGER;
ALTER TABLE etikettenformat ADD COLUMN zeilen INTEGER;
ALTER TABLE etikettenformat ADD COLUMN links_mm REAL;
ALTER TABLE etikettenformat ADD COLUMN oben_mm REAL;
ALTER TABLE etikettenformat ADD COLUMN abstand_y_mm REAL;  -- NULL = wie abstand_mm

-- Vorlagen für HERMA 9500 entfernen (selbst angelegte Größen bleiben)
DELETE FROM etikettenformat
 WHERE name IN ('HERMA 9500 · 50 × 50 mm', 'HERMA 9500 · 40 × 40 mm', 'HERMA 9500 · 60 × 40 mm');

-- HERMA 9531 Outdoor-Folienetiketten: 45,7 × 21,2 mm, 4 × 12 = 48 pro A4-Bogen
INSERT INTO etikettenformat
  (name, etikett_b_mm, etikett_h_mm, rand_mm, abstand_mm, schnittlinien, spalten, zeilen, links_mm, oben_mm, abstand_y_mm)
VALUES
  ('HERMA 9531 · 45,7 × 21,2 mm', 45.7, 21.2, 0, 2.5, 0, 4, 12, 9.85, 21.3, 0);

-- Gemerkte Auswahl zurücksetzen, falls sie auf eine entfernte Vorlage zeigte
DELETE FROM einstellung
 WHERE schluessel = 'etikettenformat'
   AND wert NOT IN (SELECT CAST(id AS TEXT) FROM etikettenformat);
