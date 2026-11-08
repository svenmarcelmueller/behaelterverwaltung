// Kleine Helfer für die Nutzung: Name pro Gerät, Formulare im Hintergrund (htmx).
(function () {
  "use strict";

  var SCHLUESSEL = "bv_name";

  function nameLesen() {
    try { return (localStorage.getItem(SCHLUESSEL) || "").trim(); } catch (e) { return ""; }
  }

  function nameSpeichern(name) {
    try {
      if (name) localStorage.setItem(SCHLUESSEL, name);
      else localStorage.removeItem(SCHLUESSEL);
    } catch (e) { /* privater Modus: dann eben ohne Namen */ }
  }

  function nameAnzeigen() {
    var name = nameLesen();
    document.querySelectorAll("[data-name-feld]").forEach(function (feld) { feld.value = name; });
    document.querySelectorAll("[data-name-text]").forEach(function (el) {
      el.textContent = name ? "Wird gespeichert als " + name : "Ohne Namen";
    });
    document.querySelectorAll("[data-name-aendern]").forEach(function (knopf) {
      knopf.textContent = name ? "ändern" : "Name festlegen";
    });
  }

  function dialogOeffnen() {
    var dialog = document.getElementById("name-dialog");
    var eingabe = document.getElementById("name-eingabe");
    if (!dialog || typeof dialog.showModal !== "function") {
      var antwort = window.prompt("Dein Name (nur auf diesem Gerät gespeichert):", nameLesen());
      if (antwort !== null) { nameSpeichern(antwort.trim().slice(0, 40)); nameAnzeigen(); }
      return;
    }
    eingabe.value = nameLesen();
    dialog.returnValue = "";
    dialog.showModal();
    eingabe.focus();
  }

  // Nach dem ersten Laden und nach jedem Austausch des Seiteninhalts durch htmx
  function einrichten() {
    nameAnzeigen();
    var dialog = document.getElementById("name-dialog");
    if (dialog && !dialog.dataset.eingerichtet) {
      dialog.dataset.eingerichtet = "1";
      dialog.addEventListener("close", function () {
        if (dialog.returnValue === "speichern") {
          nameSpeichern(document.getElementById("name-eingabe").value.trim().slice(0, 40));
          nameAnzeigen();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", einrichten);
  document.addEventListener("htmx:afterSettle", einrichten);

  // Mehrfachauswahl in der Behälterliste: Zähler, Knöpfe, „Alle auswählen“
  function auswahlAktualisieren() {
    document.querySelectorAll("form[data-auswahl]").forEach(function (form) {
      var kaestchen = form.querySelectorAll("input[name=codes]");
      var gewaehlt = form.querySelectorAll("input[name=codes]:checked").length;
      var zahl = form.querySelector("[data-auswahl-zahl]");
      if (zahl) zahl.textContent = gewaehlt + " ausgewählt";
      form.querySelectorAll("[data-auswahl-knopf]").forEach(function (k) { k.disabled = gewaehlt === 0; });
      var alle = form.querySelector("[data-alle]");
      if (alle) {
        alle.checked = gewaehlt > 0 && gewaehlt === kaestchen.length;
        alle.indeterminate = gewaehlt > 0 && gewaehlt < kaestchen.length;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", auswahlAktualisieren);
  document.addEventListener("htmx:afterSettle", auswahlAktualisieren);

  document.addEventListener("change", function (ereignis) {
    var ziel = ereignis.target;
    if (ziel.matches("[data-alle]")) {
      ziel.form.querySelectorAll("input[name=codes]").forEach(function (k) { k.checked = ziel.checked; });
    }
    if (ziel.closest("form[data-auswahl]")) auswahlAktualisieren();
  });

  document.addEventListener("click", function (ereignis) {
    if (ereignis.target.closest("[data-name-aendern]")) dialogOeffnen();

    // Etikettenvorschau: Antippen eines Platzes setzt den Beginn auf dem angebrochenen Bogen
    var platz = ereignis.target.closest("[data-startplatz]");
    var start = document.getElementById("start");
    if (platz && start) {
      start.value = platz.getAttribute("data-startplatz");
      start.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // Rückfrage vor gefährlichen Knöpfen (funktioniert mit und ohne htmx)
    var knopf = ereignis.target.closest("[data-frage]");
    if (knopf && !window.confirm(knopf.getAttribute("data-frage"))) {
      ereignis.preventDefault();
      ereignis.stopPropagation();
    }
  }, true);

  // Enter in einem Feld mit data-enter-aktion löst genau diesen Knopf aus, nicht den ersten im Formular
  document.addEventListener("keydown", function (ereignis) {
    var feld = ereignis.target;
    if (ereignis.key !== "Enter" || !feld.matches || !feld.matches("[data-enter-aktion]")) return;
    ereignis.preventDefault();
    var knopf = feld.form.querySelector("button[value='" + feld.getAttribute("data-enter-aktion") + "']");
    if (knopf && !knopf.disabled) knopf.click();
  });

  // Name an jede Anfrage aus einem Formular mit data-name-senden anhängen
  document.addEventListener("htmx:configRequest", function (ereignis) {
    var quelle = ereignis.detail.elt;
    if (quelle && quelle.closest && quelle.closest("[data-name-senden]")) {
      ereignis.detail.parameters.von = nameLesen();
    }
  });

  // Ist der Server nicht erreichbar, nicht stumm bleiben
  document.addEventListener("htmx:sendError", function () {
    window.alert("Keine Verbindung zur Behälterverwaltung. Bist du im Heimnetz?");
  });

  // Zurück-Taste auf dem iPhone zeigt die Seite aus dem Cache: Anzeige auffrischen
  window.addEventListener("pageshow", function (ereignis) {
    if (ereignis.persisted) nameAnzeigen();
  });
})();
