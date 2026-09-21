from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog

import keyring
import requests

from fp_mailer_core import (
    fetch_live_page, parse_participants, diagnostic_summary, group_participants,
    choose_next_session, recipients, build_mail,
)

APP_NAME = "FP Mailer"
KEYRING_SERVICE = "Heidelberg FP Mailer"
CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "FP-Mailer"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "fp_mailer.log"
DEBUG_FILE = CONFIG_DIR / "debug_parse.txt"

def log(msg: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")

def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def ask_credentials(root: tk.Tk, force: bool = False) -> tuple[str, str]:
    cfg = load_config()
    uni_id = cfg.get("uni_id", "")
    password = keyring.get_password(KEYRING_SERVICE, uni_id) if uni_id else None
    if uni_id and password and not force:
        return uni_id, password
    uni_id = simpledialog.askstring("FP Mailer – Einrichtung", "Uni-ID:", initialvalue=uni_id, parent=root)
    if not uni_id:
        raise RuntimeError("Einrichtung abgebrochen: keine Uni-ID angegeben.")
    password = simpledialog.askstring("FP Mailer – Einrichtung", "Uni-Passwort:", show="•", parent=root)
    if not password:
        raise RuntimeError("Einrichtung abgebrochen: kein Passwort angegeben.")
    save_config({"uni_id": uni_id.strip()})
    keyring.set_password(KEYRING_SERVICE, uni_id.strip(), password)
    return uni_id.strip(), password

def preview_text(session_date, groups, subject, body) -> str:
    recips = recipients(groups)
    lines = [
        "DRY RUN – ES WIRD KEINE E-MAIL VERSCHICKT", "",
        f"Nächster belegter Termin: {session_date.strftime('%d.%m.%Y')}",
        f"Gefundene Versuchspaare: {len(groups)}",
        f"Empfänger insgesamt: {len(recips)}", "",
    ]
    for g in groups:
        lines.append(f"{g.experiment} – {len(g.emails)} Empfänger")
        for n in g.names:
            lines.append(f"  • {n}")
        for e in g.emails:
            lines.append(f"    {e}")
        lines.append("")
    lines += ["BETREFF", subject, "", "MAILTEXT", body.rstrip(), "", "---", "Es wurde nichts versendet."]
    return "\n".join(lines)

def show_result(root: tk.Tk, text: str) -> None:
    root.deiconify()
    root.title("FP Mailer – Vorschau")
    root.geometry("820x720")
    frame = tk.Frame(root, padx=12, pady=12)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="FP Mailer – Dry Run", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    tk.Label(frame, text="Keine E-Mail wird versendet. Die aktuelle Betreuerseite wurde nur ausgewertet.", font=("Segoe UI", 10)).pack(anchor="w", pady=(2,10))
    textw = tk.Text(frame, wrap="word", font=("Consolas", 10))
    textw.pack(fill="both", expand=True)
    textw.insert("1.0", text)
    textw.configure(state="disabled")
    buttons = tk.Frame(frame)
    buttons.pack(fill="x", pady=(10,0))
    tk.Button(buttons, text="Zugangsdaten neu speichern", command=lambda: reset_credentials(root)).pack(side="left")
    tk.Button(buttons, text="Schließen", command=root.destroy, width=14).pack(side="right")

def reset_credentials(root: tk.Tk) -> None:
    cfg = load_config()
    old = cfg.get("uni_id", "")
    if old:
        try:
            keyring.delete_password(KEYRING_SERVICE, old)
        except Exception:
            pass
    try:
        ask_credentials(root, force=True)
        messagebox.showinfo(APP_NAME, "Zugangsdaten wurden aktualisiert. Beim nächsten Start werden sie verwendet.", parent=root)
    except Exception as e:
        messagebox.showwarning(APP_NAME, str(e), parent=root)

def save_diagnostics(html: str, participants_count: int | None = None) -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    summary = diagnostic_summary(html)
    if participants_count is not None:
        summary += f"\n\nParser-Ergebnis: {participants_count} eingeteilte Teilnehmerzeilen"
    DEBUG_FILE.write_text(summary, encoding="utf-8")
    log("Parser-Diagnose:\n" + summary)
    return summary

def main() -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        uni_id, password = ask_credentials(root)
        log("Start Dry-Run")
        html = fetch_live_page(uni_id, password)
        participants = parse_participants(html)
        groups = group_participants(participants)

        if not participants:
            save_diagnostics(html, 0)
            raise RuntimeError(
                "Die Betreuerseite wurde geladen, aber keine Zeile mit Status 'eingeteilt' erkannt.\n\n"
                f"Eine Diagnose ohne Passwörter wurde gespeichert unter:\n{DEBUG_FILE}"
            )

        try:
            session_date, selected = choose_next_session(groups)
        except RuntimeError:
            save_diagnostics(html, len(participants))
            raise RuntimeError(
                "Eingeteilte Gruppen wurden erkannt, aber keine davon liegt heute oder in der Zukunft.\n\n"
                f"Eine Diagnose wurde gespeichert unter:\n{DEBUG_FILE}"
            )

        subject, body = build_mail(session_date)
        out = preview_text(session_date, selected, subject, body)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "last_preview.txt").write_text(out, encoding="utf-8")
        log(f"Dry-Run OK: {session_date.isoformat()}, {len(selected)} Paare, {len(recipients(selected))} Empfänger")
        show_result(root, out)
        root.mainloop()
        return 0
    except requests.RequestException as e:
        log("Netzwerkfehler: " + repr(e))
        messagebox.showerror(APP_NAME, f"Netzwerkfehler:\n\n{e}\n\nFalls die Betreuerseite nur im Uni-Netz erreichbar ist, zuerst VPN verbinden.", parent=root)
    except Exception as e:
        log("Fehler: " + repr(e) + "\n" + traceback.format_exc())
        messagebox.showerror(APP_NAME, f"{e}\n\nLogdatei:\n{LOG_FILE}", parent=root)
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
