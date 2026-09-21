# FP Mailer – Windows Desktop

Windows-App für die Betreuung des Heidelberger Fortgeschrittenenpraktikums.

Sie liest die FP-Testatseite aus, sucht den **nächsten dir zugeordneten Termin** für E01/E06/E07/E08/E09, gruppiert die Versuchspaare und bereitet eine gemeinsame Mail vor.

## Ablauf

1. Desktop-Icon **FP Mailer** öffnen.
2. Login auf die FP-Testatseite.
3. Es werden nur `Betreuer ...`-Felder ausgewertet, bei denen **Simon Groß-Bölting / Betreuer-ID 1370** ausgewählt ist.
4. Frühester Termin ab heute wird gewählt.
5. Teilnehmer und E-Mail-Adressen werden den vier Versuchspaaren zugeordnet.
6. Vorschaufenster öffnet sich.
7. Betreff und Mailtext können noch geändert werden.
8. Versand erfolgt **nur** nach Klick auf **E-Mail absenden** und einer zusätzlichen Bestätigung.

## Versand

SMTP-Einstellungen:

- Server: `mail.urz.uni-heidelberg.de`
- Port: `587`
- Sicherheit: `STARTTLS`
- Anmeldung: Uni-ID + Passwort

Die Studierenden werden als **BCC** versendet, damit sie die Adressen der anderen nicht sehen.

Der Absender wird nach Möglichkeit aus dem `reply=`-Parameter der FP-Seite erkannt.

## Schutz gegen Fehlversand

- Kein automatischer Versand beim Öffnen.
- Eigener Button **E-Mail absenden**.
- Zusätzliche Bestätigungsabfrage mit Datum, Paaren und Empfängerzahl.
- Nach erfolgreichem Versand wird der Button deaktiviert.
- Die App merkt sich lokal, ob genau diese Empfängerliste für diesen Termin schon versendet wurde.
- Bei erneutem Versand erscheint eine zusätzliche Warnung.
- In der Versandhistorie werden keine Klartext-E-Mail-Adressen gespeichert, sondern nur ein Hash.

## Update einer vorhandenen Installation

Normalerweise reicht es, diese beiden Dateien zu ersetzen:

- `fp_mailer_core.py`
- `fp_mailer_gui.py`

Die bestehende `.venv` und Desktop-Verknüpfung bleiben erhalten.

## Passwort

Das Uni-Passwort wird über Python `keyring` im **Windows Credential Manager** gespeichert. Es liegt nicht im Projektordner und nicht im GitHub-Repository.

## Lokale Dateien

- `%LOCALAPPDATA%\FP-Mailer\config.json` – Uni-ID / Absender, kein Passwort
- `%LOCALAPPDATA%\FP-Mailer\fp_mailer.log` – Log
- `%LOCALAPPDATA%\FP-Mailer\last_preview.txt` – letzte Vorschau
- `%LOCALAPPDATA%\FP-Mailer\sent_sessions.json` – Versandstatus, Empfänger nur als Hash

## VPN

Falls der Versand nicht funktioniert, Uni-VPN verbinden. Der Uni-SMTP-Server ist für Clients über Port 587 mit STARTTLS vorgesehen und der Zugriff ist aus Sicherheitsgründen netzabhängig.
