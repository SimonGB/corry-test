from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode
import tkinter as tk
from tkinter import messagebox, simpledialog

import keyring
import requests

from fp_mailer_core import (
    fetch_live_page,
    parse_participants,
    diagnostic_summary,
    group_participants,
    choose_next_session,
    recipients,
    build_mail,
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

    uni_id = simpledialog.askstring(
        "FP Mailer – Einrichtung", "Uni-ID:", initialvalue=uni_id, parent=root
    )
    if not uni_id:
        raise RuntimeError("Einrichtung abgebrochen: keine Uni-ID angegeben.")
    password = simpledialog.askstring(
        "FP Mailer – Einrichtung", "Uni-Passwort:", show="•", parent=root
    )
    if not password:
        raise RuntimeError("Einrichtung abgebrochen: kein Passwort angegeben.")

    cfg["uni_id"] = uni_id.strip()
    cfg.pop("sender_email", None)
    save_config(cfg)
    keyring.set_password(KEYRING_SERVICE, uni_id.strip(), password)
    return uni_id.strip(), password


def compact_summary(session_date, groups) -> str:
    recips = recipients(groups)
    lines = [
        f"Termin: {session_date.strftime('%d.%m.%Y')}   |   Versuchspaare: {len(groups)}   |   Empfänger: {len(recips)}",
        "",
    ]
    for g in groups:
        lines.append(g.experiment)
        for name in g.names:
            lines.append(f"  • {name}")
        lines.append("")
    lines += ["Empfänger (BCC):", "; ".join(recips)]
    return "\n".join(lines)


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
        messagebox.showinfo(
            APP_NAME,
            "Zugangsdaten wurden aktualisiert. Beim nächsten Start werden sie verwendet.",
            parent=root,
        )
    except Exception as e:
        messagebox.showwarning(APP_NAME, str(e), parent=root)


def build_mailto_uri(recips: list[str], subject: str, body: str) -> str:
    recips = sorted({r.strip().lower() for r in recips if r.strip()})
    if not recips:
        raise ValueError("Keine Empfänger vorhanden.")
    if not subject.strip():
        raise ValueError("Der Betreff ist leer.")
    if not body.strip():
        raise ValueError("Der Mailtext ist leer.")

    query = urlencode(
        {
            "bcc": ",".join(recips),
            "subject": subject.strip(),
            "body": body.rstrip(),
        },
        quote_via=quote,
        safe="@,",
    )
    return f"mailto:?{query}"


def open_mail_app(
    root: tk.Tk,
    groups,
    subject_var: tk.StringVar,
    body_widget: tk.Text,
) -> None:
    recips = recipients(groups)
    subject = subject_var.get().strip()
    body = body_widget.get("1.0", "end-1c").strip()

    try:
        uri = build_mailto_uri(recips, subject, body)
        os.startfile(uri)
        log(f"Mail-App geöffnet: {len(recips)} BCC-Empfänger, mailto-Länge={len(uri)}")
    except Exception as e:
        log("Mail-App konnte nicht geöffnet werden: " + repr(e))
        messagebox.showerror(
            "Mail-App konnte nicht geöffnet werden",
            "Windows konnte keine Standard-App für E-Mail öffnen.\n\n"
            "Bitte unter Windows Einstellungen → Apps → Standard-Apps eine App für den Linktyp MAILTO festlegen "
            "(z. B. Outlook) und danach erneut versuchen.\n\n"
            f"Technischer Fehler: {e}",
            parent=root,
        )


def show_result(root: tk.Tk, session_date, groups, subject: str, body: str) -> None:
    root.deiconify()
    root.title("FP Mailer – Vorschau")
    root.geometry("900x820")
    root.minsize(760, 650)

    outer = tk.Frame(root, padx=14, pady=14)
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="FP Mailer", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    tk.Label(
        outer,
        text=(
            "Bitte Empfänger, Betreff und Mailtext prüfen. „In Mail-App öffnen“ erstellt nur einen neuen Entwurf "
            "in deiner Standard-Mail-App. Der FP Mailer kann selbst keine E-Mail versenden."
        ),
        font=("Segoe UI", 10),
        wraplength=850,
        justify="left",
    ).pack(anchor="w", pady=(2, 10))

    summary = tk.Text(
        outer,
        height=max(10, 7 + 3 * len(groups)),
        wrap="word",
        font=("Segoe UI", 10),
    )
    summary.pack(fill="x", pady=(0, 10))
    summary.insert("1.0", compact_summary(session_date, groups))
    summary.configure(state="disabled")

    tk.Label(
        outer,
        text="Absenderkonto: wird von deiner Standard-Mail-App festgelegt",
        anchor="w",
        font=("Segoe UI", 9),
    ).pack(fill="x", pady=(0, 8))

    subject_frame = tk.Frame(outer)
    subject_frame.pack(fill="x", pady=(0, 8))
    tk.Label(subject_frame, text="Betreff:", width=10, anchor="w").pack(side="left")
    subject_var = tk.StringVar(value=subject)
    tk.Entry(subject_frame, textvariable=subject_var).pack(side="left", fill="x", expand=True)

    tk.Label(outer, text="Mailtext:", anchor="w").pack(fill="x")
    body_widget = tk.Text(outer, wrap="word", font=("Segoe UI", 10))
    body_widget.pack(fill="both", expand=True, pady=(3, 10))
    body_widget.insert("1.0", body)

    buttons = tk.Frame(outer)
    buttons.pack(fill="x")
    tk.Button(
        buttons,
        text="Zugangsdaten neu speichern",
        command=lambda: reset_credentials(root),
    ).pack(side="left")
    tk.Button(buttons, text="Schließen", command=root.destroy, width=14).pack(side="right")
    tk.Button(
        buttons,
        text="In Mail-App öffnen",
        width=20,
        command=lambda: open_mail_app(root, groups, subject_var, body_widget),
    ).pack(side="right", padx=(0, 8))


def save_diagnostics(html: str, participants_count: int | None = None) -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    summary = diagnostic_summary(html)
    if participants_count is not None:
        summary += f"\n\nParser-Ergebnis: {participants_count} dir zugeordnete Teilnehmerzeilen"
    DEBUG_FILE.write_text(summary, encoding="utf-8")
    log("Parser-Diagnose:\n" + summary)
    return summary


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        uni_id, password = ask_credentials(root)
        log("Start")
        html = fetch_live_page(uni_id, password)

        participants = parse_participants(html)
        groups = group_participants(participants)
        if not participants:
            save_diagnostics(html, 0)
            raise RuntimeError(
                "Die Betreuerseite wurde geladen, aber keine Elektronik-Zeile mit dir als ausgewähltem Betreuer erkannt.\n\n"
                f"Eine Diagnose ohne Passwörter wurde gespeichert unter:\n{DEBUG_FILE}"
            )

        try:
            session_date, selected = choose_next_session(groups)
        except RuntimeError:
            save_diagnostics(html, len(participants))
            raise RuntimeError(
                "Dir zugeordnete Gruppen wurden erkannt, aber keine davon liegt heute oder in der Zukunft.\n\n"
                f"Eine Diagnose wurde gespeichert unter:\n{DEBUG_FILE}"
            )

        subject, body = build_mail(session_date)
        compact = compact_summary(session_date, selected)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "last_preview.txt").write_text(
            compact + "\n\nBETREFF\n" + subject + "\n\nMAILTEXT\n" + body,
            encoding="utf-8",
        )
        log(
            f"Vorschau OK: {session_date.isoformat()}, "
            f"{len(selected)} Paare, {len(recipients(selected))} Empfänger"
        )
        show_result(root, session_date, selected, subject, body)
        root.mainloop()
        return 0

    except requests.RequestException as e:
        log("Netzwerkfehler: " + repr(e))
        messagebox.showerror(
            APP_NAME,
            f"Netzwerkfehler:\n\n{e}\n\nFalls die Betreuerseite nur im Uni-Netz erreichbar ist, zuerst VPN verbinden.",
            parent=root,
        )
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
