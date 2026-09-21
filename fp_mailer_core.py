from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from urllib.parse import parse_qs, urlparse, urljoin

import requests
from bs4 import BeautifulSoup

FP_URL = "https://www.physi.uni-heidelberg.de/cgi-bin/fp/fp-testate.pl"
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

def _selected_option(select):
    """Return the currently selected <option> of a <select> element."""
    if select is None:
        return None
    selected = select.find("option", selected=True)
    if selected is not None:
        return selected
    return select.find("option")


def _selected_status(row) -> tuple[str, str]:
    select = row.find("select", attrs={"name": re.compile(r"^Status\\s", re.I)})
    option = _selected_option(select)
    if option is None:
        return "", ""
    return clean(option.get("value", "")).lower(), clean(option.get_text(" ", strip=True)).lower()


def _selected_supervisor(row) -> tuple[str, str]:
    select = row.find("select", attrs={"name": re.compile(r"^Betreuer\\s", re.I)})
    option = _selected_option(select)
    if option is None:
        return "", ""
    return clean(option.get("value", "")), clean(option.get_text(" ", strip=True))


def _supervisor_matches(supervisor_id: str, supervisor_name: str, *, target_id: str, target_name: str) -> bool:
    if target_id and supervisor_id == target_id:
        return True
    return clean(supervisor_name).casefold() == clean(target_name).casefold()


def parse_participants(
    html: str,
    codes: set[str] | None = None,
    *,
    supervisor_id: str = "1370",
    supervisor_name: str = "Simon Groß-Bölting",
) -> list[Participant]:
    """Parse rows assigned to this supervisor from the FP testate table.

    Direct table cells are:
      td[0] student, td[1] experiment, td[2] experiment date, ...

    Assignment is determined by the selected option in the Betreuer dropdown.
    Open/future attempts normally have an empty selected Status option.
    """
    codes = {c.upper() for c in (codes or set(DEFAULT_CODES))}
    soup = BeautifulSoup(html, "html.parser")
    participants: list[Participant] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue

        name = clean(cells[0].get_text(" ", strip=True))
        experiment = clean(cells[1].get_text(" ", strip=True)).upper()
        date_text = clean(cells[2].get_text(" ", strip=True))

        if experiment not in codes:
            continue

        try:
            session_date = parse_fp_date(date_text)
        except ValueError:
            continue

        selected_supervisor_id, selected_supervisor_name = _selected_supervisor(row)
        if not _supervisor_matches(
            selected_supervisor_id,
            selected_supervisor_name,
            target_id=supervisor_id,
            target_name=supervisor_name,
        ):
            continue

        status_value, status_text = _selected_status(row)
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
                name=name or "Unbekannt",
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

    electronics_rows = []
    supervisor_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    date_counter: Counter[str] = Counter()
    own_rows = 0

    for row in rows:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue

        experiment = clean(cells[1].get_text(" ", strip=True)).upper()
        if experiment not in codes:
            continue

        date_text = clean(cells[2].get_text(" ", strip=True))
        try:
            session_date = parse_fp_date(date_text)
            d = session_date.isoformat()
            date_counter[d] += 1
        except ValueError:
            d = "?"

        sup_id, sup_name = _selected_supervisor(row)
        supervisor_counter[sup_id or "<leer>"] += 1
        is_own = _supervisor_matches(
            sup_id, sup_name, target_id=supervisor_id, target_name=supervisor_name
        )
        if is_own:
            own_rows += 1

        status_value, status_text = _selected_status(row)
        status_label = status_value or status_text or "<leer>"
        status_counter[status_label] += 1
        mail_count = len(extract_mail_link_emails(row))
        electronics_rows.append((experiment, d, sup_id or "<leer>", status_label, mail_count, is_own))

    lines = [
        f"Lokales Datum: {date.today().isoformat()}",
        f"Tabellenzeilen gesamt: {len(rows)}",
        f"Elektronik-Zeilen erkannt: {len(electronics_rows)}",
        f"Davon Betreuer {supervisor_id}: {own_rows}",
        "Betreuer-ID-Verteilung: " + (", ".join(f"{k}={v}" for k, v in supervisor_counter.items()) or "<leer>"),
        "Status-Verteilung: " + (", ".join(f"{k}={v}" for k, v in status_counter.items()) or "<leer>"),
        "Erkannte Versuchstermine: " + (", ".join(f"{k} ({v} Zeilen)" for k, v in sorted(date_counter.items())) or "<keine>"),
        "",
        "Erste Elektronik-Zeilen (ohne Namen/E-Mail-Adressen):",
    ]
    for experiment, d, sup_id, status, mail_count, is_own in electronics_rows[:40]:
        own = "JA" if is_own else "nein"
        lines.append(
            f"- {experiment} | Datum={d} | BetreuerID={sup_id} | Eigene={own} | "
            f"Status={status} | MailLinks={mail_count}"
        )
    if len(electronics_rows) > 40:
        lines.append(f"... {len(electronics_rows) - 40} weitere Zeilen")
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
