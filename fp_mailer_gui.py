from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import keyring
import requests

from fp_mailer_core import (
    fetch_live_page,
    list_supervisors,
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
        "FP Mailer – Anmeldung", "Uni-ID:", initialvalue=uni_id, parent=root
    )
    if not uni_id:
        raise RuntimeError("Anmeldung abgebrochen: keine Uni-ID angegeben.")
    password = simpledialog.askstring(
        "FP Mailer – Anmeldung", "Uni-Passwort:", show="•", parent=root
    )
    if not password:
        raise RuntimeError("Anmeldung abgebrochen: kein Passwort angegeben.")

    cfg["uni_id"] = uni_id.strip()
    save_config(cfg)
    keyring.set_password(KEYRING_SERVICE, uni_id.strip(), password)
    return uni_id.strip(), password


def _default_signature(supervisor_name: str) -> str:
    parts = supervisor_name.strip().split()
    return parts[0] if parts else supervisor_name.strip()


def clear_root(root: tk.Tk) -> None:
    for child in root.winfo_children():
        try:
            child.destroy()
        except Exception:
            pass


def show_loading(root: tk.Tk, message: str) -> None:
    clear_root(root)
    root.deiconify()
    root.title("FP Mailer")
    root.geometry("500x170")
    root.minsize(440, 150)
    root.resizable(True, False)

    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="FP Mailer",
        font=("Segoe UI", 15, "bold"),
    ).pack(anchor="w")

    label = ttk.Label(
        frame,
        text=message,
        font=("Segoe UI", 10),
        wraplength=450,
        justify="left",
    )
    label.pack(anchor="w", pady=(10, 12))

    bar = ttk.Progressbar(frame, mode="indeterminate")
    bar.pack(fill="x")
    bar.start(12)

    root.update_idletasks()
    root.update()


def choose_profile(root: tk.Tk, html: str, force: bool = False) -> dict:
    cfg = load_config()
    existing = cfg.get("profile") or {}
    if (
        not force
        and existing.get("supervisor_id")
        and existing.get("supervisor_name")
        and existing.get("signature_name")
    ):
        return existing

    supervisors = list_supervisors(html)
    if not supervisors:
        raise RuntimeError("Auf der FP-Seite konnten keine Betreuer gefunden werden.")

    dialog = tk.Toplevel(root)
    dialog.title("FP Mailer – Wer bist du?")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()
    dialog.lift()
    try:
        dialog.attributes("-topmost", True)
        dialog.after(300, lambda: dialog.attributes("-topmost", False))
    except Exception:
        pass

    frame = ttk.Frame(dialog, padding=16)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)

    ttk.Label(
        frame,
        text="Wer bist du?",
        font=("Segoe UI", 13, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text=(
            "Wähle deinen Namen aus der Betreuerliste. Diese Auswahl wird lokal gespeichert "
            "und bestimmt, welche Versuchspaare der FP Mailer anzeigt."
        ),
        wraplength=470,
        justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(4, 12))

    by_label = {f"{name}  (ID {sid})": (sid, name) for sid, name in supervisors}
    labels = list(by_label.keys())

    current_label = labels[0]
    if existing.get("supervisor_id"):
        for label, (sid, _) in by_label.items():
            if sid == str(existing.get("supervisor_id")):
                current_label = label
                break

    profile_var = tk.StringVar(value=current_label)
    ttk.Label(frame, text="Betreuer/in:").grid(row=2, column=0, sticky="w")
    combo = ttk.Combobox(
        frame,
        textvariable=profile_var,
        values=labels,
        state="readonly",
        width=52,
    )
    combo.grid(row=3, column=0, sticky="ew", pady=(3, 10))

    signature_var = tk.StringVar()
    ttk.Label(frame, text="Name in der Grußformel:").grid(row=4, column=0, sticky="w")
    ttk.Entry(frame, textvariable=signature_var, width=32).grid(
        row=5, column=0, sticky="ew", pady=(3, 12)
    )

    def update_signature(*_):
        sid, name = by_label[profile_var.get()]
        if not signature_var.get().strip() or force:
            signature_var.set(
                existing.get("signature_name")
                if existing.get("supervisor_id") == sid and existing.get("signature_name")
                else _default_signature(name)
            )

    profile_var.trace_add("write", update_signature)
    update_signature()

    result: dict = {}

    def save_and_close():
        label = profile_var.get()
        if label not in by_label:
            return
        sid, name = by_label[label]
        signature = signature_var.get().strip() or _default_signature(name)
        result.update(
            {
                "supervisor_id": sid,
                "supervisor_name": name,
                "signature_name": signature,
            }
        )
        cfg2 = load_config()
        cfg2["profile"] = dict(result)
        save_config(cfg2)
        dialog.destroy()

    def cancel():
        dialog.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, sticky="e")
    ttk.Button(buttons, text="Abbrechen", command=cancel).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Speichern", command=save_and_close).pack(side="left")

    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.update_idletasks()
    x = root.winfo_screenwidth() // 2 - dialog.winfo_reqwidth() // 2
    y = root.winfo_screenheight() // 2 - dialog.winfo_reqheight() // 2
    dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    dialog.lift()
    dialog.focus_force()
    combo.focus_set()
    log("Profilauswahl sichtbar")
    root.wait_window(dialog)

    if not result:
        raise RuntimeError("Profilauswahl abgebrochen.")
    return result


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


def open_mail_app(root: tk.Tk, groups, subject_var: tk.StringVar, body_widget: tk.Text) -> None:
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
            "Bitte unter Windows Einstellungen → Apps → Standard-Apps eine App für MAILTO festlegen "
            "(z. B. Outlook) und danach erneut versuchen.\n\n"
            f"Technischer Fehler: {e}",
            parent=root,
        )


def show_recipients(root: tk.Tk, groups) -> None:
    popup = tk.Toplevel(root)
    popup.title("FP Mailer – BCC-Empfänger")
    popup.geometry("570x360")
    popup.minsize(430, 260)
    popup.transient(root)

    frame = ttk.Frame(popup, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame,
        text=f"BCC-Empfänger ({len(recipients(groups))})",
        font=("Segoe UI", 12, "bold"),
    ).pack(anchor="w", pady=(0, 8))

    text = tk.Text(frame, wrap="none", font=("Consolas", 9))
    scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    text.insert("1.0", "\n".join(recipients(groups)))
    text.configure(state="disabled")


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
        messagebox.showinfo(APP_NAME, "Zugangsdaten wurden aktualisiert.", parent=root)
    except Exception as e:
        messagebox.showwarning(APP_NAME, str(e), parent=root)


def change_profile(root: tk.Tk, html: str) -> None:
    try:
        profile = choose_profile(root, html, force=True)
        messagebox.showinfo(
            APP_NAME,
            f"Profil geändert auf {profile['supervisor_name']}.\n\n"
            "Bitte FP Mailer schließen und neu öffnen, damit die Gruppenauswahl aktualisiert wird.",
            parent=root,
        )
    except Exception as e:
        messagebox.showwarning(APP_NAME, str(e), parent=root)


def show_result(root: tk.Tk, html: str, profile: dict, session_date, groups, subject: str, body: str) -> None:
    clear_root(root)
    root.deiconify()
    root.title("FP Mailer – Vorschau")
    root.geometry("860x650")
    root.minsize(680, 500)

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    outer = ttk.Frame(root, padding=12)
    outer.grid(row=0, column=0, sticky="nsew")
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(5, weight=1)

    header = ttk.Frame(outer)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="FP Mailer", font=("Segoe UI", 15, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        header,
        text=f"Profil: {profile['supervisor_name']}",
        font=("Segoe UI", 9),
    ).grid(row=0, column=1, sticky="e")

    ttk.Label(
        outer,
        text=(
            f"Termin {session_date.strftime('%d.%m.%Y')}  •  "
            f"{len(groups)} Versuchspaare  •  {len(recipients(groups))} BCC-Empfänger"
        ),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=1, column=0, sticky="w", pady=(0, 8))

    summary_frame = ttk.LabelFrame(outer, text="Versuchspaare", padding=6)
    summary_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    summary_frame.columnconfigure(0, weight=1)

    tree = ttk.Treeview(
        summary_frame,
        columns=("experiment", "participants"),
        show="headings",
        height=max(2, min(5, len(groups))),
    )
    tree.heading("experiment", text="Versuch")
    tree.heading("participants", text="Teilnehmende")
    tree.column("experiment", width=90, anchor="center", stretch=False)
    tree.column("participants", width=620, anchor="w")
    for g in groups:
        tree.insert("", "end", values=(g.experiment, ", ".join(g.names)))
    tree.grid(row=0, column=0, sticky="ew")

    recipient_row = ttk.Frame(summary_frame)
    recipient_row.grid(row=1, column=0, sticky="ew", pady=(5, 0))
    ttk.Label(
        recipient_row,
        text=f"{len(recipients(groups))} Adressen werden als BCC eingetragen.",
    ).pack(side="left")
    ttk.Button(
        recipient_row,
        text="Empfänger anzeigen",
        command=lambda: show_recipients(root, groups),
    ).pack(side="right")

    subject_frame = ttk.Frame(outer)
    subject_frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    subject_frame.columnconfigure(1, weight=1)
    ttk.Label(subject_frame, text="Betreff:", width=9).grid(row=0, column=0, sticky="w")
    subject_var = tk.StringVar(value=subject)
    ttk.Entry(subject_frame, textvariable=subject_var).grid(row=0, column=1, sticky="ew")

    ttk.Label(outer, text="Mailtext:").grid(row=4, column=0, sticky="w")

    body_frame = ttk.Frame(outer)
    body_frame.grid(row=5, column=0, sticky="nsew", pady=(3, 8))
    body_frame.columnconfigure(0, weight=1)
    body_frame.rowconfigure(0, weight=1)
    body_widget = tk.Text(body_frame, wrap="word", font=("Segoe UI", 10), undo=True)
    body_scroll = ttk.Scrollbar(body_frame, orient="vertical", command=body_widget.yview)
    body_widget.configure(yscrollcommand=body_scroll.set)
    body_widget.grid(row=0, column=0, sticky="nsew")
    body_scroll.grid(row=0, column=1, sticky="ns")
    body_widget.insert("1.0", body)

    buttons = ttk.Frame(outer)
    buttons.grid(row=6, column=0, sticky="ew")
    buttons.columnconfigure(2, weight=1)
    ttk.Button(
        buttons,
        text="Profil ändern",
        command=lambda: change_profile(root, html),
    ).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(
        buttons,
        text="Login ändern",
        command=lambda: reset_credentials(root),
    ).grid(row=0, column=1)
    ttk.Button(buttons, text="Schließen", command=root.destroy).grid(
        row=0, column=3, padx=(6, 6)
    )
    ttk.Button(
        buttons,
        text="In Mail-App öffnen",
        command=lambda: open_mail_app(root, groups, subject_var, body_widget),
    ).grid(row=0, column=4)


def save_diagnostics(html: str, profile: dict, participants_count: int | None = None) -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    summary = diagnostic_summary(
        html,
        supervisor_id=str(profile["supervisor_id"]),
        supervisor_name=profile["supervisor_name"],
    )
    if participants_count is not None:
        summary += f"\n\nParser-Ergebnis: {participants_count} zugeordnete Teilnehmerzeilen"
    DEBUG_FILE.write_text(summary, encoding="utf-8")
    log("Parser-Diagnose:\n" + summary)
    return summary


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        uni_id, password = ask_credentials(root)
        log("Start")

        show_loading(root, "FP-Seite wird geladen und Anmeldung wird geprüft …")
        log("FP-Seite wird geladen")
        html = fetch_live_page(uni_id, password)
        log("FP-Seite geladen")

        show_loading(root, "Betreuerprofil wird vorbereitet …")
        log("Profilauswahl wird vorbereitet")
        profile = choose_profile(root, html)
        log(
            f"Profil gewählt: {profile['supervisor_name']} "
            f"(ID {profile['supervisor_id']})"
        )

        show_loading(root, f"Versuchspaare für {profile['supervisor_name']} werden ausgewertet …")
        participants = parse_participants(
            html,
            supervisor_id=str(profile["supervisor_id"]),
            supervisor_name=profile["supervisor_name"],
        )
        groups = group_participants(participants)
        log(f"Gruppen ausgewertet: {len(participants)} Teilnehmerzeilen, {len(groups)} Gruppen")
        if not participants:
            save_diagnostics(html, profile, 0)
            raise RuntimeError(
                f"Für {profile['supervisor_name']} wurden keine Elektronik-Gruppen erkannt.\n\n"
                f"Diagnose:\n{DEBUG_FILE}"
            )

        try:
            session_date, selected = choose_next_session(groups)
        except RuntimeError:
            save_diagnostics(html, profile, len(participants))
            raise RuntimeError(
                f"Für {profile['supervisor_name']} gibt es keine zukünftigen zugeordneten Elektronik-Gruppen.\n\n"
                f"Diagnose:\n{DEBUG_FILE}"
            )

        log(
            f"Nächster Termin gewählt: {session_date.isoformat()}, "
            f"{len(selected)} Versuchspaare, {len(recipients(selected))} Empfänger"
        )
        subject, body = build_mail(session_date, profile.get("signature_name", ""))
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "last_preview.txt").write_text(
            f"Profil: {profile['supervisor_name']}\n"
            f"Termin: {session_date.strftime('%d.%m.%Y')}\n"
            f"Empfänger: {len(recipients(selected))}\n\n"
            "BETREFF\n" + subject + "\n\nMAILTEXT\n" + body,
            encoding="utf-8",
        )
        log(
            f"Vorschau OK: Profil={profile['supervisor_name']}, "
            f"{session_date.isoformat()}, {len(selected)} Paare, "
            f"{len(recipients(selected))} Empfänger"
        )
        show_result(root, html, profile, session_date, selected, subject, body)
        root.mainloop()
        return 0

    except requests.RequestException as e:
        log("Netzwerkfehler: " + repr(e))
        messagebox.showerror(
            APP_NAME,
            f"Netzwerkfehler:\n\n{e}\n\nFalls nötig, zuerst Uni-VPN verbinden.",
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
