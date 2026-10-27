import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CREDENTIALS_FILE = os.path.join(
    BASE_DIR,
    "credentials.json"
)

TOKEN_FILE = os.path.join(
    BASE_DIR,
    "token.json"
)

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


def create_test_event(service):
    # Create an event about 10 minutes from now.
    start = datetime.now() + timedelta(minutes=10)
    end = start + timedelta(minutes=15)

    event = {
        "summary": "EchoMind Test Reminder",
        "description": (
            "Test event created by EchoMind "
            "Google Calendar integration."
        ),
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end.isoformat(),
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

    created = service.events().insert(
        calendarId="primary",
        body=event,
    ).execute()

    return created


def main():
    print("Connecting to Google Calendar...")

    service = get_calendar_service()

    print("Connected successfully.")

    print()
    print("Creating test event...")

    event = create_test_event(service)

    print()
    print("TEST EVENT CREATED")
    print("  Title:", event.get("summary"))
    print("  Start:", event["start"].get("dateTime"))
    print("  Time zone:", TIMEZONE)
    print("  Event ID:", event.get("id"))
    print("  Calendar link:", event.get("htmlLink"))


if __name__ == "__main__":
    main()
