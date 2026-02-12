import base64
from email.mime.text import MIMEText

def send_email(subject: str, html: str):
    import json
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    to_email = os.environ["TO_EMAIL"]

    client_secret_json = os.environ["GMAIL_CLIENT_SECRET_JSON"]
    token_json = os.environ["GMAIL_TOKEN_JSON"]

    # token 로드
    creds = Credentials.from_authorized_user_info(json.loads(token_json), scopes=["https://www.googleapis.com/auth/gmail.send"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)

    msg = MIMEText(html, "html", "utf-8")
    msg["to"] = to_email
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
