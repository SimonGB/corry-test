# FP Mailer – Windows Desktop v9

Der FP Mailer liest die Heidelberger FP-Betreuerseite aus, findet den nächsten einem ausgewählten Betreuer zugeordneten Termin für E01/E06/E07/E08/E09 und öffnet anschließend eine vorbereitete Nachricht in der Windows-Standard-Mail-App.

## Neu in v9

### Benutzerprofil beim ersten Start

Nach dem ersten erfolgreichen Login fragt die App einmal **„Wer bist du?“**.

Die Liste der Betreuer wird direkt aus der FP-Seite gelesen. Man wählt nur den eigenen Namen aus; die interne Betreuer-ID wird automatisch gespeichert.

Zusätzlich kann festgelegt werden, welcher Name in der Grußformel verwendet wird, zum Beispiel `Simon`.

Gespeichert wird lokal in:

`%LOCALAPPDATA%\FP-Mailer\config.json`

Das Passwort bleibt wie bisher im Windows Credential Manager und steht nicht in dieser Datei.

Über **Profil ändern** kann die Auswahl später geändert werden.

### Kompaktere Oberfläche

Die Oberfläche ist jetzt responsiv:

- kompakte Tabelle mit Versuch und Teilnehmenden,
- Empfängeradressen nur bei Klick auf **Empfänger anzeigen**,
- editierbarer Betreff,
- editierbarer Mailtext mit Scrollbar,
- feste Aktionsleiste am unteren Fensterrand.

Damit bleiben **Schließen** und **In Mail-App öffnen** auch bei kleineren Fenstern sichtbar.

## Versand

FP Mailer verschickt selbst keine Nachricht.

**In Mail-App öffnen** erzeugt einen `mailto:`-Entwurf mit:

- allen Teilnehmenden als BCC,
- Betreff,
- Mailtext.

Das tatsächliche Senden passiert anschließend manuell in Outlook, Thunderbird oder der konfigurierten Standard-Mail-App.

## Bestehende Installation aktualisieren

Nur diese beiden Dateien ersetzen:

- `fp_mailer_core.py`
- `fp_mailer_gui.py`

Die `.venv`, Desktop-Verknüpfung und gespeicherten Login-Daten bleiben erhalten.

Beim ersten Start von v9 wird einmal das Benutzerprofil abgefragt.

## Neue Installation

1. ZIP entpacken.
2. `INSTALLIEREN.bat` doppelklicken.
3. Nach erfolgreicher Installation das Desktop-Icon **FP Mailer** öffnen.
4. Uni-ID + Passwort eingeben.
5. Eigenen Namen aus der Betreuerliste auswählen.

## Falls keine Mail-App aufgeht

Unter Windows unter **Einstellungen → Apps → Standard-Apps** für `MAILTO` eine Mail-App festlegen, z. B. Outlook.
