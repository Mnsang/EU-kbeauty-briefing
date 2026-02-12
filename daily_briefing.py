import os, re, json, hashlib, smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

RSS_FILE = "rss_urls.txt"
STATE_FILE = "state_seen.json"

CATEGORIES = {
  "Regulation & Compliance": [r"\bCPNP\b", r"\bREACH\b", r"SCCS", r"regulation", r"ban", r"restricted", r"compliance", r"claims"],
  "Retail & Channel":        [r"Sephora", r"Douglas", r"\bdm\b", r"Rossmann", r"Boots", r"retail", r"listing", r"distribution", r"marketplace", r"e-?commerce"],
  "Market & Data":           [r"market size", r"\bCAGR\b", r"forecast", r"report", r"sales", r"growth"],
  "Trend & Consumer":        [r"trend", r"Gen Z", r"ingredient", r"barrier", r"dermo", r"clean beauty", r"K-?beauty"],
  "Brand & Marketing":       [r"campaign", r"influencer", r"branding", r"launch", r"collaboration"],
  "Competition Watch":       [r"acquired", r"merger", r"M&A", r"competitor", r"new brand", r"expansion"],
}

def strip_html(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)

def norm_dt(raw: str) -> str:
    if not raw:
        return ""
    try:
        dt = dateparser.parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""

def stable_key(link: str, title: str) -> str:
    base = f"{link}||{title}".encode("utf-8", errors="ignore")
    return hashlib.sha256(base).hexdigest()[:24]

def auto_tag(title: str, text: str):
    hay = f"{title or ''} {text or ''}"
    tags = []
    for cat, patterns in CATEGORIES.items():
        if any(re.search(p, hay, re.IGNORECASE) for p in patterns):
            tags.append(cat)
    return tags or ["Other"]

def load_urls():
    with open(RSS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    state["seen"] = state["seen"][-2000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_all():
    items = []
    for url in load_urls():
        feed = feedparser.parse(url)
        for e in getattr(feed, "entries", []):
            title = getattr(e, "title", "") or ""
            link = getattr(e, "link", "") or ""
            summary = strip_html(getattr(e, "summary", "") or getattr(e, "description", "") or "")
            published = norm_dt(getattr(e, "published", "") or getattr(e, "updated", "") or "")
            items.append({
                "key": stable_key(link, title),
                "title": title.strip(),
                "link": link.strip(),
                "summary": summary.strip(),
                "published": published,
                "tags": auto_tag(title, summary),
            })
    items.sort(key=lambda x: x["published"] or "0000", reverse=True)
    return items

def build_html_report(new_items):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_cat = {}
    for it in new_items:
        for t in it["tags"]:
            by_cat.setdefault(t, []).append(it)

    order = [
        "Regulation & Compliance",
        "Retail & Channel",
        "Market & Data",
        "Trend & Consumer",
        "Brand & Marketing",
        "Competition Watch",
        "Other",
    ]

    def item_html(it):
        s = (it["summary"][:220] + "…") if len(it["summary"]) > 220 else it["summary"]
        pub = it["published"][:10] if it["published"] else ""
        return f"""
        <li style="margin-bottom:12px;">
          <div><a href="{it['link']}" target="_blank" rel="noreferrer">{it['title']}</a></div>
          <div style="color:#666; font-size:12px;">{pub}</div>
          <div style="margin-top:4px; color:#111;">{s}</div>
        </li>
        """

    sections = [f"<p>오늘 신규 기사: <b>{len(new_items)}</b>개</p>"]
    for cat in order:
        arr = by_cat.get(cat, [])
        if not arr:
            continue
        arr = arr[:10]
        sections.append(f"<h3 style='margin-top:20px;'>{cat} ({len(arr)})</h3>")
        sections.append("<ul>" + "\n".join(item_html(it) for it in arr) + "</ul>")

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height:1.4;">
        <h2>EU K-Beauty Daily Briefing — {today} (UTC)</h2>
        {''.join(sections)}
        <hr/>
        <p style="color:#777; font-size:12px;">RSS 기반 자동 수집/분류 결과. 원문은 링크를 확인하세요.</p>
      </body>
    </html>
    """

def send_email(subject: str, html: str):
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_email  = os.environ["TO_EMAIL"]
    from_email = os.environ.get("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())

def main():
    state = load_state()
    seen = set(state.get("seen", []))

    items = fetch_all()
    new_items = [it for it in items if it["key"] not in seen]
    new_items = new_items[:40]

    for it in new_items:
        seen.add(it["key"])
    state["seen"] = list(seen)
    save_state(state)

    if not new_items:
        print("No new items.")
        return

    html = build_html_report(new_items)
    subject = f"EU K-Beauty Daily Briefing ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
    send_email(subject, html)
    print(f"Sent {len(new_items)} items.")

if __name__ == "__main__":
    main()
