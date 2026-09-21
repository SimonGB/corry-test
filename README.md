# FP Mailer – Windows Desktop Dry Run

Kleine Windows-Anwendung für Betreuer des Heidelberger Fortgeschrittenenpraktikums. Sie liest die FP-Testatseite aus, findet den **nächsten tatsächlich belegten Termin** für E01/E06/E07/E08/E09 und zeigt eine fertige Rundmail als Vorschau an.

> **Sicherheitszustand:** Diese Version kann **keine E-Mail verschicken**. Es gibt absichtlich keinen SMTP-/Send-Code.

## Installation

1. ZIP entpacken, z. B. nach `C:\Users\<Name>\Documents\fp-mailer-desktop`.
2. `INSTALLIEREN.bat` doppelklicken.
3. Der Installer sucht automatisch nach einer Python-Version mit funktionierendem **SSL**, **Tkinter** und **venv**.
4. Falls keine brauchbare Python-Version vorhanden ist, bietet er auf Windows mit `winget` an, die offizielle Python-3.12-Version zu installieren. Alternativ Python von python.org installieren und danach `INSTALLIEREN.bat` erneut starten.
5. **Nur wenn alle Tests erfolgreich waren**, wird das Desktop-Icon `FP Mailer` eingerichtet.

## Wenn der alte Installer schon einmal fehlgeschlagen ist

Einfach die neue Version verwenden und `INSTALLIEREN.bat` erneut starten. Der Installer löscht die fehlerhafte `.venv` automatisch und baut sie mit einer funktionierenden Python-Version neu auf.

## Start

Nach erfolgreicher Installation einfach auf dem Desktop **FP Mailer** doppelklicken.

Beim ersten Start werden Uni-ID und Uni-Passwort abgefragt. Das Passwort wird über `keyring` im **Windows Credential Manager** gespeichert.

Dann passiert automatisch:

1. Login auf die FP-Testatseite.
2. Nur Einträge mit Status `eingeteilt` werden ausgewertet.
3. Der früheste noch nicht vergangene Termin wird gewählt.
4. Nur tatsächlich belegte E01/E06/E07/E08/E09 werden übernommen.
5. E-Mail-Adressen werden aus den `mail.pl?email=...`-Links gelesen und dedupliziert.
6. Betreff und Mailtext werden erzeugt.
7. Eine Vorschau erscheint. **Nichts wird versendet.**

## Wenn das Desktop-Icon nichts macht

In dieser Version prüft ein vorgeschaltetes PowerShell-Skript zuerst die Installation. Fehlt etwas, erscheint eine Fehlermeldung statt eines lautlosen Abbruchs.

Zusätzlich kannst du `DIAGNOSE.bat` doppelklicken. Das zeigt verwendetes Python, Python-Version, OpenSSL-Version und ob die benötigten Pakete geladen werden können.

## Logs

- Letzte Vorschau: `%LOCALAPPDATA%\FP-Mailer\last_preview.txt`
- Logdatei: `%LOCALAPPDATA%\FP-Mailer\fp_mailer.log`

## VPN

Falls die Betreuerseite außerhalb des Uninetzes nicht erreichbar ist, vor dem Start den Heidelberg-VPN verbinden.

## Datenschutz

- Keine Uni-Passwörter im Repository.
- `.mht`-/`.mhtml`-Snapshots sind per `.gitignore` ausgeschlossen.
- Diese Dry-Run-Version versendet nichts.
