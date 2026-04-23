"""
MeetPilot AI - Live Demo Backend
Run: python app.py
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()
import smtplib
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

app = Flask(__name__)
CORS(app)

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GMAIL_ADDRESS   = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASS  = os.getenv("GMAIL_APP_PASS", "")
CONTACTS_FILE   = "contacts.json"
SCOPES          = ["https://www.googleapis.com/auth/calendar"]

# ── Gemini setup ──────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ── Contacts store ────────────────────────────────────────────────────────────
def load_contacts():
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    return {
        "Alice": {"email": "alice@example.com", "name": "Alice Johnson"},
        "Bob":   {"email": "bob@example.com",   "name": "Bob Smith"},
    }

def save_contacts(contacts):
    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts, f, indent=2)

# ── Google Calendar ───────────────────────────────────────────────────────────
def get_calendar_service():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.path.exists("credentials.json"):
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.pickle", "wb") as f:
                pickle.dump(creds, f)
        else:
            return None
    return build("calendar", "v3", credentials=creds)

def check_availability(participant_name, proposed_dt, duration_min=30):
    """Returns True if slot is free (or calendar not configured)."""
    service = get_calendar_service()
    if not service:
        return True, "Calendar not configured — slot assumed available"

    time_min = proposed_dt.isoformat() + "Z"
    time_max = (proposed_dt + timedelta(minutes=duration_min)).isoformat() + "Z"
    events_result = service.events().list(
        calendarId="primary", timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])
    if events:
        return False, f"Conflict: {events[0].get('summary', 'Busy')}"
    return True, "Available"

def create_calendar_event(summary, description, start_dt, duration_min, attendee_emails):
    service = get_calendar_service()
    if not service:
        return None, "Calendar not configured"

    end_dt = start_dt + timedelta(minutes=duration_min)
    event = {
        "summary": summary,
        "description": description,
        "start":  {"dateTime": start_dt.isoformat(), "timeZone": "America/New_York"},
        "end":    {"dateTime": end_dt.isoformat(),   "timeZone": "America/New_York"},
        "attendees": [{"email": e} for e in attendee_emails],
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return created.get("htmlLink"), None

# ── Gmail ─────────────────────────────────────────────────────────────────────
def send_email(to_email, subject, body):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASS:
        return False, "Gmail not configured (set GMAIL_ADDRESS and GMAIL_APP_PASS in .env)"
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.send_message(msg)
        return True, "Sent"
    except Exception as e:
        return False, str(e)

# ── Gemini helpers ────────────────────────────────────────────────────────────
def parse_intent(user_input: str) -> dict:
    """Extract structured scheduling intent from natural language."""
    prompt = f"""You are a meeting scheduling assistant. Parse this scheduling request and return ONLY valid JSON.

Request: "{user_input}"

Return JSON with these exact fields:
{{
  "participants": ["list of first names mentioned"],
  "duration_minutes": 30,
  "topic": "meeting topic or purpose",
  "preferred_time": "natural language time expression or null",
  "mode": "proposal" or "direct" or "followup",
  "confidence": 0-100
}}

mode rules:
- "direct" if a specific day+time is given (e.g. "Friday at 2 PM")
- "followup" if it references a previous meeting
- "proposal" if timing is flexible or approximate

Respond ONLY with JSON. No markdown, no explanation."""

    resp = model.generate_content(prompt)
    raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def generate_email(topic: str, participant: str, proposed_time: str, agenda_items: list, mode: str) -> dict:
    """Generate a professional meeting email."""
    agenda_str = "\n".join(f"  {i+1}. {item}" for i, item in enumerate(agenda_items))
    prompt = f"""Write a professional meeting invitation email.

Context:
- Topic: {topic}
- Recipient: {participant}
- Proposed time: {proposed_time}
- Mode: {mode} (proposal=asking for confirmation, direct=confirming a set time, followup=following up)
- Agenda:
{agenda_str}

Return ONLY valid JSON:
{{
  "subject": "concise email subject line",
  "body": "full email body, 3-4 sentences, professional but warm, sign off with 'Best,' and the sender's name as [Your Name]"
}}"""

    resp = model.generate_content(prompt)
    raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def generate_agenda(topic: str, participants: list, duration_min: int) -> list:
    """Generate a focused meeting agenda."""
    prompt = f"""Generate a concise meeting agenda for:
- Topic: {topic}
- Attendees: {", ".join(participants)}
- Duration: {duration_min} minutes

Return ONLY a JSON array of 3-4 agenda item strings. Example:
["Welcome and introductions (5 min)", "Review Q4 goals (15 min)", "Next steps and action items (10 min)"]

No markdown, no explanation. Just the JSON array."""

    resp = model.generate_content(prompt)
    raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def generate_meeting_summary(topic: str, participants: list, agenda: list) -> str:
    """Generate a pre-meeting briefing summary."""
    prompt = f"""Write a brief pre-meeting preparation summary (2-3 sentences) for:
- Meeting topic: {topic}
- Participants: {", ".join(participants)}
- Agenda: {", ".join(agenda)}

Just the plain text summary. No labels, no markdown."""

    resp = model.generate_content(prompt)
    return resp.text.strip()

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/schedule", methods=["POST"])
def schedule():
    """Main scheduling endpoint — parse, check availability, generate content."""
    data = request.json
    user_input = data.get("input", "").strip()
    if not user_input:
        return jsonify({"error": "No input provided"}), 400

    contacts = load_contacts()

    # Step 1: Parse intent
    try:
        intent = parse_intent(user_input)
    except Exception as e:
        return jsonify({"error": f"Could not parse intent: {e}"}), 500

    participants = intent.get("participants", [])
    topic        = intent.get("topic", "Meeting")
    duration     = intent.get("duration_minutes", 30)
    mode         = intent.get("mode", "proposal")
    pref_time    = intent.get("preferred_time") or "Next available slot"

    # Step 2: Availability check (simulated if no Calendar credentials)
    now = datetime.now()
    proposed_dt = now + timedelta(days=2, hours=14)  # Default: 2 days from now at 2 PM
    available, avail_msg = check_availability(participants[0] if participants else "Guest", proposed_dt, duration)

    proposed_time_str = pref_time if pref_time else proposed_dt.strftime("%A, %B %d at %I:%M %p")

    # Step 3: Generate agenda
    try:
        agenda = generate_agenda(topic, participants, duration)
    except Exception as e:
        agenda = [f"Discuss {topic}", "Review action items", "Next steps"]

    # Step 4: Generate email
    participant_name = participants[0] if participants else "Team"
    try:
        email_content = generate_email(topic, participant_name, proposed_time_str, agenda, mode)
    except Exception as e:
        email_content = {
            "subject": f"Meeting: {topic}",
            "body": f"Hi {participant_name},\n\nI'd like to schedule a meeting to discuss {topic}.\n\nBest,\n[Your Name]"
        }

    # Step 5: Generate summary
    try:
        summary = generate_meeting_summary(topic, participants, agenda)
    except Exception:
        summary = f"This meeting will cover {topic} with {', '.join(participants)}."

    # Step 6: Resolve participant emails from contacts
    participant_emails = []
    for p in participants:
        for key, val in contacts.items():
            if key.lower() == p.lower() or val.get("name", "").lower().startswith(p.lower()):
                participant_emails.append(val["email"])
                break

    result = {
        "intent":            intent,
        "participants":      participants,
        "participant_emails": participant_emails,
        "topic":             topic,
        "duration_minutes":  duration,
        "mode":              mode,
        "proposed_time":     proposed_time_str,
        "available":         available,
        "availability_msg":  avail_msg,
        "agenda":            agenda,
        "email":             email_content,
        "summary":           summary,
    }
    return jsonify(result)

@app.route("/api/confirm", methods=["POST"])
def confirm():
    """Send email and/or create calendar event after user confirms."""
    data          = request.json
    topic         = data.get("topic", "Meeting")
    email_content = data.get("email", {})
    participant_emails = data.get("participant_emails", [])
    agenda        = data.get("agenda", [])
    proposed_time = data.get("proposed_time", "")
    duration      = data.get("duration_minutes", 30)
    send_mail     = data.get("send_email", True)
    create_event  = data.get("create_event", False)

    results = {"email_sent": False, "event_created": False, "messages": []}

    # Send email
    if send_mail and participant_emails:
        for email_addr in participant_emails:
            ok, msg = send_email(email_addr, email_content.get("subject", topic), email_content.get("body", ""))
            if ok:
                results["email_sent"] = True
                results["messages"].append(f"Email sent to {email_addr}")
            else:
                results["messages"].append(f"Email note: {msg}")
    elif send_mail:
        results["messages"].append("No participant emails found in contacts — email not sent (demo mode)")

    # Create calendar event
    if create_event:
        now = datetime.now()
        start_dt = now + timedelta(days=2, hours=14)
        emails = participant_emails or []
        link, err = create_calendar_event(
            summary=topic,
            description="\n".join(agenda),
            start_dt=start_dt,
            duration_min=duration,
            attendee_emails=emails
        )
        if link:
            results["event_created"] = True
            results["event_link"] = link
            results["messages"].append("Calendar event created")
        else:
            results["messages"].append(f"Calendar note: {err}")

    results["messages"].append("Meeting confirmed successfully")
    return jsonify(results)

@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    return jsonify(load_contacts())

@app.route("/api/contacts", methods=["POST"])
def add_contact():
    data = request.json
    contacts = load_contacts()
    contacts[data["name"]] = {"email": data["email"], "name": data["name"]}
    save_contacts(contacts)
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("\n  MeetPilot AI — Live Demo")
    print("  ─────────────────────────")
    print("  Running at: http://localhost:5050\n")
    app.run(debug=True, port=5050)
