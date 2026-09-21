# FP Mailer – Windows Desktop v8

Die App liest die Heidelberger FP-Betreuerseite aus, findet den nächsten dir zugeordneten Termin für E01/E06/E07/E08/E09 und bereitet eine gemeinsame Mail vor.

## Kein direkter Versand mehr

Der Button **„In Mail-App öffnen“** erzeugt einen `mailto:`-Link und übergibt ihn an die in Windows konfigurierte Standard-Mail-App.

Übernommen werden:

- alle Studierenden als **BCC**,
- der editierbare Betreff,
- der editierbare Mailtext.

Das Absenderkonto wird von Outlook/Thunderbird/der jeweiligen Mail-App festgelegt. **Senden musst du anschließend selbst in der Mail-App anklicken.** FP Mailer enthält keinen SMTP-Sendecode mehr.

## Update

Bei einer bestehenden Installation nur ersetzen:

- `fp_mailer_core.py`
- `fp_mailer_gui.py`

Die bestehende `.venv`, das Desktop-Icon und die gespeicherten Login-Daten bleiben erhalten.

## Falls keine Mail-App aufgeht

Unter Windows:

**Einstellungen → Apps → Standard-Apps**

und für den Linktyp bzw. das Protokoll **MAILTO** eine Mail-App festlegen, z. B. Outlook.

## Passwort

Das Uni-Passwort wird weiterhin nur für den Login auf der FP-Betreuerseite benötigt und über Python `keyring` im **Windows Credential Manager** gespeichert.
