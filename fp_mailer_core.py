from __future__ import annotations

import re
import smtplib
import ssl
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from urllib.parse import parse_qs, urlparse, urljoin
from email.message import EmailMessage

import requests
from bs4 import BeautifulSoup

FP_URL = "https://www.physi.uni-heidelberg.de/cgi-bin/fp/fp-testate.pl"
SMTP_HOST = "mail.urz.uni-heidelberg.de"
SMTP_PORT = 587
DEFAULT_CODES = ("E01", "E06", "E07", "E08", "E09")
GERMAN_WEEKDAYS = {
    0: "Montag", 1: "Dienstag", 2: "Mittwoch", 3: "Donnerstag",
    4: "Freitag", 5: "Samstag", 6: "Sonntag",
}
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4})$")

@dataclass(frozen=True)
class Participant:
    name: str
    experiment: str
    session_date: date
    emails: tuple[str, ...]
    status: str

@dataclass(frozen=True)
class Group:
    experiment: str
    session_date: date
    names: tuple[str, ...]
    emails: tuple[str, ...]

def clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())

def parse_fp_date(text: str) -> date:
    text = clean(text)
    for fmt in ("%d.%m.%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unbekanntes Datumsformat: {text!r}")

def extract_mail_link_emails(row) -> set[str]:
    found: set[str] = set()
    for a in row.find_all("a", href=True):
        parsed = urlparse(a.get("href", ""))
        if "mail.pl" not in parsed.path:
            continue
        query = parse_qs(parsed.query, keep_blank_values=True)
        for value in query.get("email", []):
            for addr in re.split(r"[,;]", value):
                addr = addr.strip().lower()
                if EMAIL_RE.match(addr):
                    found.add(addr)
    return found

BETREUER_NAME_RE = re.compile(
    r"^Betreuer\s+(E\d{2})\s+(\d{4}-\d{2}-\d{2})\s+(\d+)\s*$",
    re.IGNORECASE,
)
STATUS_NAME_RE = re.compile(
    r"^Status\s+(\d+)\s+(E\d{2})\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)


def _selected_option(select):
    """Return the selected option, or the first option as a defensive fallback."""
    if select is None:
        return None
    selected = select.find("option", selected=True)
    return selected if selected is not None else select.find("option")


def _parse_betreuer_select_name(select) -> tuple[str, date, str] | None:
    """Extract experiment, ISO date and participant id from:
    'Betreuer E08 2026-05-04 6437'.
    """
    name = clean(select.get("name", ""))
    match = BETREUER_NAME_RE.match(name)
    if not match:
        return None
    experiment, iso_date, participant_id = match.groups()
    try:
        session_date = datetime.strptime(iso_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return experiment.upper(), session_date, participant_id


def _selected_supervisor_from_select(select) -> tuple[str, str]:
    option = _selected_option(select)
    if option is None:
        return "", ""
    return clean(option.get("value", "")), clean(option.get_text(" ", strip=True))


def _selected_status_for_row(row, participant_id: str, experiment: str, session_date: date) -> tuple[str, str]:
    expected_name = f"Status {participant_id} {experiment} {session_date.isoformat()}"
    select = row.find("select", attrs={"name": expected_name})
    if select is None:
        # Fallback for harmless formatting differences.
        for candidate in row.find_all("select", attrs={"name": True}):
            if STATUS_NAME_RE.match(clean(candidate.get("name", ""))):
                select = candidate
                break
    option = _selected_option(select)
    if option is None:
        return "", ""
    return clean(option.get("value", "")).lower(), clean(option.get_text(" ", strip=True)).lower()


def _supervisor_matches(
    supervisor_id: str,
    supervisor_name: str,
    *,
    target_id: str,
    target_name: str,
) -> bool:
    if target_id and supervisor_id == target_id:
        return True
    return bool(target_name) and clean(supervisor_name).casefold() == clean(target_name).casefold()


def _student_name_from_row(row) -> str:
    # The mail.pl link is the most stable marker for the student name.
    for a in row.find_all("a", href=True):
        if "mail.pl" in urlparse(a.get("href", "")).path:
            name = clean(a.get_text(" ", strip=True))
            if name:
                return name

    cells = row.find_all("td")
    if cells:
        return clean(cells[0].get_text(" ", strip=True)) or "Unbekannt"
    return "Unbekannt"


def parse_participants(
    html: str,
    codes: set[str] | None = None,
    *,
    supervisor_id: str = "1370",
    supervisor_name: str = "Simon Groß-Bölting",
) -> list[Participant]:
    """Parse assignments using the Betreuer <select> itself.

    This deliberately does *not* depend on table-column positions. Every actual
    participant row contains a field such as:
        <select name="Betreuer E08 2026-05-04 6437">
    which already encodes experiment, date and participant id.
    """
    codes = {c.upper() for c in (codes or set(DEFAULT_CODES))}
    soup = BeautifulSoup(html, "html.parser")
    participants: list[Participant] = []

    betreuer_selects = soup.find_all(
        "select",
        attrs={"name": re.compile(r"^Betreuer\s+", re.IGNORECASE)},
    )

    for select in betreuer_selects:
        parsed = _parse_betreuer_select_name(select)
        if parsed is None:
            continue
        experiment, session_date, participant_id = parsed

        if experiment not in codes:
            continue

        selected_supervisor_id, selected_supervisor_name = _selected_supervisor_from_select(select)
        if not _supervisor_matches(
            selected_supervisor_id,
            selected_supervisor_name,
            target_id=supervisor_id,
            target_name=supervisor_name,
        ):
            continue

        row = select.find_parent("tr")
        if row is None:
            continue

        status_value, status_text = _selected_status_for_row(
            row, participant_id, experiment, session_date
        )
        # Explicitly excluded attempt. Empty status is normal for upcoming/open attempts.
        if status_value == "nicht":
            continue

        emails = tuple(sorted(extract_mail_link_emails(row)))
        if not emails:
            raise RuntimeError(
                f"Zugeordneter Eintrag ohne erkennbare E-Mail-Adresse: "
                f"{experiment} / {session_date.strftime('%d.%m.%Y')}"
            )

        participants.append(
            Participant(
                name=_student_name_from_anchor(mail_anchor),
                experiment=experiment,
                session_date=session_date,
                emails=emails,
                status=status_value or status_text,
            )
        )

    return participants


def diagnostic_summary(
    html: str,
    codes: set[str] | None = None,
    *,
    supervisor_id: str = "1370",
    supervisor_name: str = "Simon Groß-Bölting",
) -> str:
    """PII-light diagnostics: no student names, passwords or email addresses."""
    codes = {c.upper() for c in (codes or set(DEFAULT_CODES))}
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    all_selects = soup.find_all("select", attrs={"name": True})
    betreuer_selects = [
        s for s in all_selects
        if clean(s.get("name", "")).lower().startswith("betreuer ")
    ]

    parsed_rows = []
    supervisor_counter: Counter[str] = Counter()
    date_counter: Counter[str] = Counter()
    own_rows = 0
    valid_betreuer_names = 0

    for select in betreuer_selects:
        parsed = _parse_betreuer_select_name(select)
        if parsed is None:
            parsed_rows.append(("?", "?", "?", "<Betreuer-name nicht parsebar>", 0, False))
            continue

        valid_betreuer_names += 1
        experiment, session_date, participant_id = parsed
        if experiment not in codes:
            continue

        sup_id, sup_name = _selected_supervisor_from_select(select)
        supervisor_counter[sup_id or "<leer>"] += 1
        is_own = _supervisor_matches(
            sup_id,
            sup_name,
            target_id=supervisor_id,
            target_name=supervisor_name,
        )
        if is_own:
            own_rows += 1

        date_counter[session_date.isoformat()] += 1
        row = select.find_parent("tr")
        if row is not None:
            status_value, status_text = _selected_status_for_row(
                row, participant_id, experiment, session_date
            )
            mail_count = len(
                extract_emails_from_mail_link(_student_mail_anchor_for_select(select))
            )
        else:
            status_value, status_text, mail_count = "", "", 0

        status_label = status_value or status_text or "<leer>"
        parsed_rows.append(
            (
                experiment,
                session_date.isoformat(),
                sup_id or "<leer>",
                status_label,
                mail_count,
                is_own,
            )
        )

    # Useful if a future server response changes the field prefix.
    select_prefixes: Counter[str] = Counter()
    for select in all_selects:
        field_name = clean(select.get("name", ""))
        prefix = field_name.split(" ", 1)[0] if field_name else "<leer>"
        select_prefixes[prefix] += 1

    lines = [
        f"Lokales Datum: {date.today().isoformat()}",
        f"Tabellenzeilen gesamt: {len(rows)}",
        f"Select-Felder gesamt: {len(all_selects)}",
        f"Betreuer-Selects erkannt: {len(betreuer_selects)}",
        f"Davon Name-Schema parsebar: {valid_betreuer_names}",
        f"Elektronik-Betreuerzeilen: {len([r for r in parsed_rows if r[0] in codes])}",
        f"Davon Betreuer {supervisor_id}: {own_rows}",
        "Select-Präfixe: " + (
            ", ".join(f"{k}={v}" for k, v in select_prefixes.most_common(20))
            or "<leer>"
        ),
        "Betreuer-ID-Verteilung: " + (
            ", ".join(f"{k}={v}" for k, v in supervisor_counter.items())
            or "<leer>"
        ),
        "Erkannte Versuchstermine: " + (
            ", ".join(f"{k} ({v} Zeilen)" for k, v in sorted(date_counter.items()))
            or "<keine>"
        ),
        "",
        "Erste Betreuer-Zeilen (ohne Namen/E-Mail-Adressen):",
    ]

    for experiment, d, sup_id, status, mail_count, is_own in parsed_rows[:40]:
        own = "JA" if is_own else "nein"
        lines.append(
            f"- {experiment} | Datum={d} | BetreuerID={sup_id} | "
            f"Eigene={own} | Status={status} | MailLinks={mail_count}"
        )
    if len(parsed_rows) > 40:
        lines.append(f"... {len(parsed_rows) - 40} weitere Zeilen")

    return "\n".join(lines)


def group_participants(participants: Iterable[Participant]) -> list[Group]:
    buckets: dict[tuple[date, str], dict[str, set[str]]] = {}
    for p in participants:
        key = (p.session_date, p.experiment)
        b = buckets.setdefault(key, {"names": set(), "emails": set()})
        b["names"].add(p.name)
        b["emails"].update(p.emails)
    return sorted(
        [Group(exp, d, tuple(sorted(v["names"])), tuple(sorted(v["emails"])))
         for (d, exp), v in buckets.items()],
        key=lambda g: (g.session_date, g.experiment),
    )

def choose_next_session(groups: Iterable[Group], today: date | None = None) -> tuple[date, list[Group]]:
    today = today or date.today()
    future = [g for g in groups if g.session_date >= today]
    if not future:
        raise RuntimeError("Keine zukünftigen dir zugeordneten Elektronik-Gruppen gefunden.")
    next_date = min(g.session_date for g in future)
    return next_date, [g for g in future if g.session_date == next_date]

def recipients(groups: Iterable[Group]) -> list[str]:
    out: set[str] = set()
    for g in groups:
        out.update(g.emails)
    return sorted(out)

def build_mail(session_date: date) -> tuple[str, str]:
    weekday = GERMAN_WEEKDAYS[session_date.weekday()]
    pretty = session_date.strftime("%d.%m.%Y")
    subject = f'FP-Versuch "Elektroniker-Grundpraktikum" – {weekday}, {pretty}'
    body = f"""Moin zusammen,

für den FP-Versuch „Elektroniker-Grundpraktikum“ treffen wir uns am {weekday}, den {pretty}, um 09:00 Uhr am INF 501.

Für den Versuch sind insgesamt etwa zwei Tage eingeplant, jeweils ungefähr von 09:00 bis 17:00 Uhr.

Bitte denkt daran, euch vorher entsprechend vorzubereiten:
- Bearbeitet vorab einmal das Quiz.
- Berechnet die in der Versuchsanleitung geforderten Komponenten bzw. Bauteilwerte.

Dann können wir direkt mit dem Versuch starten.

Viele Grüße
Simon
"""
    return subject, body


def infer_sender_email(html: str) -> str | None:
    """Infer the tutor's email address from reply=/cc= in a mail.pl link."""
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        parsed = urlparse(anchor.get("href", ""))
        if "mail.pl" not in parsed.path:
            continue
        query = parse_qs(parsed.query, keep_blank_values=True)
        for key in ("reply", "cc"):
            for value in query.get(key, []):
                for addr in re.split(r"[,;]", value):
                    addr = addr.strip().lower()
                    if EMAIL_RE.match(addr):
                        return addr
    return None


def send_email_via_uni_smtp(
    *,
    sender_email: str,
    uni_id: str,
    password: str,
    recipient_emails: list[str],
    subject: str,
    body: str,
    timeout: int = 30,
) -> None:
    """Send one message through Heidelberg University's SMTP server."""
    if not EMAIL_RE.match(sender_email):
        raise ValueError(f"Ungültige Absenderadresse: {sender_email!r}")
    recipient_emails = sorted({
        e.strip().lower()
        for e in recipient_emails
        if EMAIL_RE.match(e.strip())
    })
    if not recipient_emails:
        raise ValueError("Keine gültigen Empfängeradressen vorhanden.")
    if not subject.strip():
        raise ValueError("Der Betreff ist leer.")
    if not body.strip():
        raise ValueError("Der Mailtext ist leer.")

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = sender_email
    msg["Bcc"] = ", ".join(recipient_emails)
    msg["Subject"] = subject.strip()
    msg.set_content(body.rstrip() + "\n")

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=timeout) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(uni_id, password)
        smtp.send_message(msg)

def looks_logged_in(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(clean(x.get_text(" ", strip=True)) for x in soup.find_all(["th", "td"]))
    return "Student/in" in text and "Vers.-" in text

def find_login_form(soup: BeautifulSoup):
    for form in soup.find_all("form"):
        if form.find("input", attrs={"type": re.compile("password", re.I)}):
            return form
    return None

def _desc(inp) -> str:
    return " ".join(str(inp.get(k, "")) for k in ("name", "id", "placeholder", "value")).lower()

def _username_score(inp) -> int:
    d = _desc(inp)
    score = 0
    for token, points in (("uni-id",20),("uni_id",20),("uniid",20),("userid",15),("user",10),("login",8),("id",3)):
        if token in d:
            score += points
    return score

def _form_payload(form, uni_id: str, password: str):
    payload: dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name and (inp.get("type") or "text").lower() == "hidden":
            payload[name] = inp.get("value", "")
    pw_inputs = [x for x in form.find_all("input") if (x.get("type") or "").lower() == "password" and x.get("name")]
    if not pw_inputs:
        raise RuntimeError("Loginformular ohne Passwortfeld.")
    pw = pw_inputs[0]
    candidates = []
    for inp in form.find_all("input"):
        name = inp.get("name")
        typ = (inp.get("type") or "text").lower()
        if name and inp is not pw and typ in {"text", "email", "search", ""}:
            candidates.append(inp)
    if not candidates:
        raise RuntimeError("Loginformular ohne erkanntes Uni-ID-Feld.")
    user = max(candidates, key=_username_score)
    payload[user["name"]] = uni_id
    payload[pw["name"]] = password
    submit = form.find("input", attrs={"type": re.compile("submit", re.I)})
    if submit and submit.get("name"):
        payload[submit["name"]] = submit.get("value", "")
    return payload

def fetch_live_page(uni_id: str, password: str, timeout: int = 30) -> str:
    if not uni_id or not password:
        raise RuntimeError("Uni-ID oder Passwort fehlt.")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 FP-Mailer-Desktop/0.2"})
    r = session.get(FP_URL, timeout=timeout)
    r.raise_for_status()
    if looks_logged_in(r.text):
        return r.text
    soup = BeautifulSoup(r.text, "html.parser")
    form = find_login_form(soup)
    if form is None:
        raise RuntimeError("Kein Loginformular und keine Testattabelle gefunden.")
    payload = _form_payload(form, uni_id, password)
    action = urljoin(r.url, form.get("action") or r.url)
    method = (form.get("method") or "get").lower()
    r2 = session.post(action, data=payload, timeout=timeout) if method == "post" else session.get(action, params=payload, timeout=timeout)
    r2.raise_for_status()
    html = r2.text
    if not looks_logged_in(html):
        r3 = session.get(FP_URL, timeout=timeout)
        r3.raise_for_status()
        html = r3.text
    if not looks_logged_in(html):
        raise RuntimeError("Login nicht erfolgreich. Zugangsdaten oder Loginstruktur prüfen.")
    return html
