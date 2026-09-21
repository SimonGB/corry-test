from __future__ import annotations

import hashlib
import json
import os
import smtplib
import traceback
from datetime import datetime
from pathlib import Path
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
    infer_sender_email,
    send_email_via_uni_smtp,
)

APP_NAME = "FP Mailer"
KEYRING_SERVICE = "Heidelberg FP Mailer"
CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "FP-Mailer"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "fp_mailer.log"
DEBUG_FILE = CONFIG_DIR / "debug_parse.txt"
SENT_FILE = CONFIG_DIR / "sent_sessions.json"


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


def load_sent_state() -> dict:
    try:
        return json.loads(SENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sent_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


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

    cfg["uni_id"] = uni_id.strip()
    save_config(cfg)
    keyring.set_password(KEYRING_SERVICE, uni_id.strip(), password)
    return uni_id.strip(), password


def ensure_sender_email(root: tk.Tk, inferred: str | None) -> str:
    cfg = load_config()
    sender = inferred or cfg.get("sender_email", "")
    if sender:
        if cfg.get("sender_email") != sender:
            cfg["sender_email"] = sender
            save_config(cfg)
        return sender

    sender = simpledialog.askstring(
        "FP Mailer – Absender",
        "Deine Uni-E-Mail-Adresse, von der versendet werden soll:",
        parent=root,
    )
    if not sender:
        raise RuntimeError("Keine Absenderadresse angegeben.")
    sender = sender.strip().lower()
    cfg["sender_email"] = sender
    save_config(cfg)
    return sender


def compact_summary(session_date, groups) -> str:
    recips = recipients(groups)
    lines = [
        f"Termin: {session_date.strftime('%d.%m.%Y')}   |   Versuchspaare: {len(groups)}   |   Empfänger: {len(recips)}",
        "",
    ]
    for g in groups:
        lines.append(f"{g.experiment}: {'; '.join(g.names)}")
    lines += ["", "Empfänger:", "; ".join(recips)]
    return "\n".join(lines)


def recipients_digest(recips: list[str]) -> str:
    payload = "\n".join(sorted(r.lower() for r in recips)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def already_sent_info(session_date, recips: list[str]) -> dict | None:
    state = load_sent_state()
    item = state.get(session_date.isoformat())
    if not item or item.get("recipient_digest") != recipients_digest(recips):
        return None
    return item


def mark_sent(session_date, recips: list[str], subject: str) -> None:
    state = load_sent_state()
    state[session_date.isoformat()] = {
        "sent_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "recipient_count": len(recips),
        "recipient_digest": recipients_digest(recips),
        "subject": subject,
    }
    save_sent_state(state)


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


def send_from_window(
    root: tk.Tk,
    send_button: tk.Button,
    session_date,
    groups,
    sender_email: str,
    uni_id: str,
    password: str,
    subject_var: tk.StringVar,
    body_widget: tk.Text,
) -> None:
    recips = recipients(groups)
    subject = subject_var.get().strip()
    body = body_widget.get("1.0", "end-1c").strip()

    previous = already_sent_info(session_date, recips)
    if previous:
        sent_at = previous.get("sent_at", "unbekannt")
        if not messagebox.askyesno(
            "Bereits versendet",
            f"Für diesen Termin und genau diese Empfängerliste wurde bereits eine E-Mail versendet.\n\n"
            f"Gesendet: {sent_at}\nEmpfänger: {len(recips)}\n\nTrotzdem erneut senden?",
            parent=root,
        ):
            return

    preview_names = "\n".join(f"• {g.experiment}: {', '.join(g.names)}" for g in groups)
    if not messagebox.askyesno(
        "E-Mail wirklich absenden?",
        f"Absender: {sender_email}\n"
        f"Termin: {session_date.strftime('%d.%m.%Y')}\n"
        f"Empfänger: {len(recips)} (BCC)\n\n"
        f"{preview_names}\n\n"
        "Die E-Mail wird jetzt wirklich versendet. Fortfahren?",
        parent=root,
    ):
        return

    send_button.configure(state="disabled", text="Wird gesendet …")
    root.update_idletasks()

    try:
        send_email_via_uni_smtp(
            sender_email=sender_email,
            uni_id=uni_id,
            password=password,
            recipient_emails=recips,
            subject=subject,
            body=body,
        )
        mark_sent(session_date, recips, subject)
        log(f"Mail gesendet: {session_date.isoformat()}, {len(recips)} Empfänger")
        send_button.configure(text="E-Mail gesendet ✓", state="disabled")
        messagebox.showinfo(
            "E-Mail gesendet",
            f"Die E-Mail wurde erfolgreich an {len(recips)} Empfänger versendet.\n\n"
            "Die Adressen wurden als BCC verwendet.",
            parent=root,
        )
    except smtplib.SMTPAuthenticationError:
        log("SMTP-Authentifizierung fehlgeschlagen")
        send_button.configure(state="normal", text="E-Mail absenden")
        messagebox.showerror(
            "Versand fehlgeschlagen",
            "Die Anmeldung am Uni-Mailserver wurde abgelehnt. Bitte Uni-ID/Passwort prüfen.",
            parent=root,
        )
    except Exception as e:
        log("SMTP-Fehler: " + repr(e))
        send_button.configure(state="normal", text="E-Mail absenden")
        messagebox.showerror(
            "Versand fehlgeschlagen",
            f"Die E-Mail konnte nicht versendet werden:\n\n{e}\n\n"
            "Falls du nicht in Deutschland bzw. nicht im Uni-Netz bist, verbinde zuerst das Uni-VPN.",
            parent=root,
        )


def show_result(
    root: tk.Tk,
    session_date,
    groups,
    sender_email: str,
    uni_id: str,
    password: str,
    subject: str,
    body: str,
) -> None:
    root.deiconify()
    root.title("FP Mailer – Vorschau & Versand")
    root.geometry("900x820")
    root.minsize(760, 650)

    outer = tk.Frame(root, padx=14, pady=14)
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="FP Mailer", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    tk.Label(
        outer,
        text="Bitte Empfänger und Mailtext prüfen. Gesendet wird erst nach Klick auf „E-Mail absenden“ und einer zusätzlichen Bestätigung.",
        font=("Segoe UI", 10),
        wraplength=850,
        justify="left",
    ).pack(anchor="w", pady=(2, 10))

    summary = tk.Text(outer, height=max(8, 5 + len(groups)), wrap="word", font=("Segoe UI", 10))
    summary.pack(fill="x", pady=(0, 10))
    summary.insert("1.0", compact_summary(session_date, groups))
    summary.configure(state="disabled")

    meta = tk.Frame(outer)
    meta.pack(fill="x", pady=(0, 8))
    tk.Label(meta, text="Von:", width=10, anchor="w").pack(side="left")
    tk.Label(meta, text=sender_email, anchor="w").pack(side="left")

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
    send_button = tk.Button(buttons, text="E-Mail absenden", width=18)
    send_button.pack(side="right", padx=(0, 8))
    send_button.configure(
        command=lambda: send_from_window(
            root,
            send_button,
            session_date,
            groups,
            sender_email,
            uni_id,
            password,
            subject_var,
            body_widget,
        )
    )

    recips = recipients(groups)
    previous = already_sent_info(session_date, recips)
    if previous:
        tk.Label(
            outer,
            text=f"Hinweis: Für genau diese Empfängerliste wurde bereits am {previous.get('sent_at', 'unbekannt')} gesendet.",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(8, 0))


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

        sender_email = ensure_sender_email(root, infer_sender_email(html))
        subject, body = build_mail(session_date)
        compact = compact_summary(session_date, selected)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "last_preview.txt").write_text(
            compact + "\n\nBETREFF\n" + subject + "\n\nMAILTEXT\n" + body,
            encoding="utf-8",
        )
        log(f"Vorschau OK: {session_date.isoformat()}, {len(selected)} Paare, {len(recipients(selected))} Empfänger")
        show_result(root, session_date, selected, sender_email, uni_id, password, subject, body)
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
