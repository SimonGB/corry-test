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

def _row_values(row) -> list[str]:
    cells = row.find_all(["td", "th"], recursive=False)
    if not cells:
        cells = row.find_all(["td", "th"])
    return [clean(c.get_text(" ", strip=True)) for c in cells]

def _find_experiment(values: list[str], codes: set[str]) -> tuple[str | None, int | None]:
    for i, value in enumerate(values):
        candidate = value.upper().strip()
        if candidate in codes:
            return candidate, i
    return None, None

def _find_date(values: list[str], experiment_index: int | None = None) -> tuple[date | None, int | None]:
    indices = list(range(len(values)))
    if experiment_index is not None:
        indices = list(range(experiment_index + 1, len(values))) + list(range(0, experiment_index))
    for i in indices:
        value = values[i]
        if not DATE_RE.match(value):
            continue
        try:
            return parse_fp_date(value), i
        except ValueError:
            pass
    return None, None

def _status_from_values(values: list[str]) -> str:
    lowered = [clean(v).lower() for v in values]
    if "eingeteilt" in lowered:
        return "eingeteilt"
    for value in lowered:
        if re.search(r"\beingeteilt\b", value):
            return "eingeteilt"
    return ""

def parse_participants(html: str, codes: set[str] | None = None) -> list[Participant]:
    codes = {c.upper() for c in (codes or set(DEFAULT_CODES))}
    soup = BeautifulSoup(html, "html.parser")
    participants: list[Participant] = []

    for row in soup.find_all("tr"):
        values = _row_values(row)
        if not values:
            continue
        experiment, exp_index = _find_experiment(values, codes)
        if not experiment:
            continue
        status = _status_from_values(values)
        if status != "eingeteilt":
            continue
        session_date, _ = _find_date(values, exp_index)
        if session_date is None:
            continue
        name = values[0] if values else ""
        if exp_index is not None and exp_index > 0:
            before = [v for v in values[:exp_index] if v]
            if before:
                name = before[-1]
        name = clean(name) or "Unbekannt"
        emails = tuple(sorted(extract_mail_link_emails(row)))
        if not emails:
            raise RuntimeError(
                f"Eingeteilter Eintrag ohne erkennbare E-Mail-Adresse: "
                f"{experiment} / {session_date.strftime('%d.%m.%Y')}"
            )
        participants.append(Participant(name, experiment, session_date, emails, status))
    return participants

def diagnostic_summary(html: str, codes: set[str] | None = None) -> str:
    codes = {c.upper() for c in (codes or set(DEFAULT_CODES))}
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    code_rows = []
    status_counter: Counter[str] = Counter()
    date_counter: Counter[str] = Counter()
    mail_rows = 0

    for row in rows:
        values = _row_values(row)
        experiment, exp_index = _find_experiment(values, codes)
        if not experiment:
            continue
        status = _status_from_values(values) or "<kein eingeteilt-Status erkannt>"
        session_date, _ = _find_date(values, exp_index)
        mail_count = len(extract_mail_link_emails(row))
        if mail_count:
            mail_rows += 1
        status_counter[status] += 1
        if session_date:
            date_counter[session_date.isoformat()] += 1
        code_rows.append((experiment, session_date.isoformat() if session_date else "?", status, len(values), mail_count))

    lines = [
        f"Lokales Datum: {date.today().isoformat()}",
        f"Tabellenzeilen gesamt: {len(rows)}",
        f"Elektronik-Zeilen erkannt: {len(code_rows)}",
        f"Elektronik-Zeilen mit mail.pl-Adresse: {mail_rows}",
        "Status-Verteilung: " + (", ".join(f"{k}={v}" for k, v in status_counter.items()) or "<leer>"),
        "Erkannte Versuchstermine: " + (", ".join(f"{k} ({v} Zeilen)" for k, v in sorted(date_counter.items())) or "<keine>"),
        "",
        "Erste erkannte Elektronik-Zeilen (ohne Namen/E-Mail-Adressen):",
    ]
    for experiment, d, status, n_cells, mail_count in code_rows[:30]:
        lines.append(f"- {experiment} | Datum={d} | Status={status} | Spalten={n_cells} | MailLinks={mail_count}")
    if len(code_rows) > 30:
        lines.append(f"... {len(code_rows) - 30} weitere Zeilen")
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
        raise RuntimeError("Keine zukünftigen eingeteilten Elektronik-Gruppen gefunden.")
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
