import argparse
import hashlib
import html as htmlmod
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Falta BeautifulSoup. Ejecuta: py -m pip install beautifulsoup4")
    raise

TEAM_ID = "90523"
TEAM_NAME = "FLORANGE U.E.MATARÓ"
SOURCE_URL = "https://www.basquetcatala.cat/partits/calendari_equip_global/3541/90523"
TZ = "Europe/Madrid"

def esc(s):
    return str(s).replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\r", "").replace("\n", r"\n")

def fold(line, limit=73):
    # Simple UTF-8-safe-enough folding for typical FCBQ text.
    out = []
    while len(line.encode("utf-8")) > 75:
        cut = min(limit, len(line))
        while len(line[:cut].encode("utf-8")) > 73:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)

def clean_text(node):
    return " ".join(node.stripped_strings)

def parse_rows(raw):
    soup = BeautifulSoup(raw, "html.parser")
    games = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 7:
            continue

        date_txt = clean_text(tds[0])
        time_txt = clean_text(tds[1])
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", date_txt):
            continue
        if not re.fullmatch(r"\d{2}:\d{2}", time_txt):
            continue

        home = clean_text(tds[2])
        away = clean_text(tds[3])
        competition = clean_text(tds[4])

        # Preserve venue/address split at <br>.
        venue_parts = [x.strip() for x in tds[5].stripped_strings if x.strip()]
        venue = venue_parts[0] if venue_parts else ""
        address = ", ".join(venue_parts[1:]) if len(venue_parts) > 1 else ""

        info = tds[6].find("a", href=re.compile(r"/partits/llistatpartits/\d+"))
        match_id = None
        match_url = SOURCE_URL
        if info:
            m = re.search(r"/partits/llistatpartits/(\d+)", info.get("href", ""))
            if m:
                match_id = m.group(1)
                match_url = urljoin(SOURCE_URL, info["href"])

        # Keep only this team's games.
        hrefs = [a.get("href", "") for a in (tds[2].find_all("a") + tds[3].find_all("a"))]
        if not any(f"/equip/{TEAM_ID}" in h for h in hrefs) and TEAM_NAME not in (home, away):
            continue

        changed = bool(tds[6].find("img", attrs={"title": re.compile("Canvis", re.I)}))
        start = datetime.strptime(f"{date_txt} {time_txt}", "%d/%m/%Y %H:%M")
        # FCBQ rows do not expose an end time; 2h is a calendar display convention.
        end = start + timedelta(hours=2)

        stable = match_id or hashlib.sha1(f"{home}|{away}|{competition}".encode("utf-8")).hexdigest()[:16]
        games.append({
            "id": stable, "url": match_url, "start": start, "end": end,
            "home": home, "away": away, "competition": competition,
            "venue": venue, "address": address, "changed": changed,
        })
    return games

def make_ics(games):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UEM Mataro//FCBQ Calendar//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:UEM Mataró Infantil A",
        f"X-WR-TIMEZONE:{TZ}",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for g in sorted(games, key=lambda x: x["start"]):
        desc = f"{g['competition']}\\nFitxa/acta FCBQ: {g['url']}"
        if g["changed"]:
            desc += "\\nFCBQ marca aquest partit amb canvis."
        location = ", ".join(x for x in [g["venue"], g["address"]] if x)
        ev = [
            "BEGIN:VEVENT",
            f"UID:fcBQ-{g['id']}@uem-mataro-calendar",
            f"DTSTAMP:{now}",
            f"DTSTART;TZID={TZ}:{g['start'].strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID={TZ}:{g['end'].strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{esc('🏀 ' + g['home'] + ' – ' + g['away'])}",
            f"LOCATION:{esc(location)}",
            f"DESCRIPTION:{esc(desc)}",
            f"URL:{g['url']}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ]
        lines.extend(ev)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"

def main():
    ap = argparse.ArgumentParser(description="Convierte el HTML del calendario global FCBQ en un calendario ICS.")
    ap.add_argument("html", help="HTML guardado desde el navegador (Ctrl+S, Página web solo HTML)")
    ap.add_argument("-o", "--output", default="uem-mataro-infantil-a.ics")
    args = ap.parse_args()

    raw = Path(args.html).read_text(encoding="utf-8", errors="replace")
    games = parse_rows(raw)
    if not games:
        sys.exit("No encontré partidos del equipo 90523. Guarda la página del Calendari Global ya verificada/cargada.")
    Path(args.output).write_text(make_ics(games), encoding="utf-8", newline="")
    print(f"OK: {len(games)} partidos -> {args.output}")
    for g in games:
        print(g["start"].strftime("%d/%m/%Y %H:%M"), "|", g["home"], "-", g["away"], "|", g["id"])

if __name__ == "__main__":
    main()
