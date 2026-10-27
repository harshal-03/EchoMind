"""Google Calendar integration for EchoMind."""

import os

import netlog

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

TIMEZONE = "Asia/Kolkata"


def get_calendar_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )
            creds = flow.run_local_server(
                port=0,
                open_browser=False
            )

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build(
        "calendar",
        "v3",
        credentials=creds
    )


def create_calendar_event(title, start_iso, end_iso, description=None):
    netlog.record("www.googleapis.com", "external")   # counted in the privacy report
    service = get_calendar_service()

    event = {
        "summary": title,
        "start": {
            "dateTime": start_iso,
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {
                    "method": "popup",
                    "minutes": 5,
                }
            ],
        },
    }

    if description:
        event["description"] = description

    created = service.events().insert(
        calendarId="primary",
        body=event,
    ).execute()

    return created


def list_upcoming_events(max_results=10):
    """Return upcoming primary-calendar events without modifying the calendar."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    netlog.record("www.googleapis.com", "external")
    service = get_calendar_service()

    response = service.events().list(
        calendarId="primary",
        timeMin=datetime.now(timezone.utc).isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for event in response.get("items", []):
        start_info = event.get("start", {})
        if start_info.get("dateTime"):
            start_dt = datetime.fromisoformat(
                start_info["dateTime"].replace("Z", "+00:00")
            )
            when = start_dt.astimezone(
                ZoneInfo(TIMEZONE)
            ).strftime("%a, %d %b at %I:%M %p")
        elif start_info.get("date"):
            day = datetime.strptime(
                start_info["date"], "%Y-%m-%d"
            )
            when = day.strftime("%a, %d %b (all day)")
        else:
            when = "time unavailable"

        events.append({
            "title": event.get("summary") or "Untitled event",
            "when": when,
        })

    return events
