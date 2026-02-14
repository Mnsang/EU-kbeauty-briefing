import os
import re
import base64
import hashlib
from datetime import datetime, timezone
from email.mime.text import MIMEText

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request


RSS_FILE = "rss_urls.txt"

CATEGORIES = {
    "Regulation & Compliance": [
        r"\bCPNP\b", r"\bREACH\b", r"SCCS", r"regulation", r"ban",
        r"restricted", r"compliance", r"claims"
    ],
    "Retail & Channel": [
        r"Sephora", r"Douglas", r"\bdm\b", r"Rossmann", r"Boots",
        r"retail", r"listing", r"distribution", r"marketplace", r"e-?commerce"
    ],
    "Market & Data": [
        r"market size", r"\bCAGR\b", r"forecast", r"report", r"sales", r"growth"
    ],
    "Trend & Consumer": [
        r"trend", r"Gen Z", r"ingredient", r"barrier", r"dermo",
        r"clean beauty", r"K-?beauty"
    ],
    "Brand & Marketing": [
        r"campaign", r"influencer", r"branding", r"launch", r"collaboration"
    ],
    "Competition Watch": [
        r"acquired", r"merger", r"M&A", r"competitor", r"new brand", r"expansion"
    ],
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


def build_html_report(items):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_cat = {}
    for it in items:
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

    sections = [f"<p>수집 기사: <b>{len(items)}</b>개</p>"]
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
    import json

    to_email = os.environ["TO_EMAIL"]
    token_json = os.environ["GMAIL_TOKEN_JSON"]

    creds = Credentials.from_authorized_user_info(
        json.loads(token_json),
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)

    msg = MIMEText(html, "html", "utf-8")
    msg["to"] = to_email
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def main():
    items = fetch_all()
    print("Fetched items:", len(items))

    if not items:
        print("No items fetched (check rss_urls.txt).")
        return

    html = build_html_report(items[:40])
    subject = f"EU K-Beauty Daily Briefing ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"

    print("Sending email...")
    send_email(subject, html)
    print("Email sent.")


if __name__ == "__main__":
    main()
