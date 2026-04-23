# MeetPilot AI — Live Demo

> Schedule Smarter. Prepare Better.

A live, locally-running demo of MeetPilot AI built with Flask + Google Gemini.  
Parses natural language → checks availability → drafts email → generates agenda — all in real time.

---

## Quick Start (5 minutes)

### 1. Clone and enter the project

```bash
git clone https://github.com/YOUR_USERNAME/meetpilot-demo.git
cd meetpilot-demo
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up your API key

```bash
cp .env.example .env
```

Open `.env` and add your **Gemini API key** (required):

```
GEMINI_API_KEY=your_key_here
```

Get a free key at: https://aistudio.google.com/app/apikey

> **For the demo recording**, only `GEMINI_API_KEY` is needed.  
> Gmail and Calendar are optional — the demo works without them.

### 5. Run the app

```bash
python app.py
```

Open **http://localhost:5050** in your browser.

---

## Demo Prompts

Use these during your recording to show all three modes:

| Mode | Prompt |
|------|--------|
| **Proposal** | `Schedule a 30-minute meeting with Alice next Tuesday afternoon about Q4 planning` |
| **Direct** | `Schedule a meeting with Bob Friday at 2 PM about presentation prep` |
| **Follow-up** | `Schedule a follow-up with Alice next week to review the Q4 outcomes` |

---

## Optional: Real Email Sending

1. Enable 2FA on your Gmail account
2. Go to https://myaccount.google.com/apppasswords → create an App Password
3. Add to `.env`:
   ```
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASS=your_16_char_app_password
   ```

## Optional: Google Calendar Integration

1. Go to https://console.cloud.google.com/apis/credentials
2. Enable the **Google Calendar API**
3. Create **OAuth 2.0 Desktop** credentials → download as `credentials.json`
4. Place `credentials.json` in this folder
5. On first run the app opens a browser for OAuth — sign in and grant access

---

## Project Structure

```
meetpilot-demo/
├── app.py              # Flask backend — Gemini, Calendar, Gmail
├── templates/
│   └── index.html      # Full frontend UI
├── contacts.json       # Local contact store
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Tech Stack

- **Google Gemini 1.5 Flash** — intent parsing, agenda generation, email drafting
- **Google Calendar API** — real-time availability and event creation
- **Gmail SMTP** — sending meeting emails
- **Flask** — lightweight Python backend
- **Vanilla JS + CSS** — zero-dependency frontend
