# Fix "Service Unreachable" on Twilio

## Why it happens
Twilio tries to call your webhook URL when someone dials your number.
If that URL points to localhost or an offline server, it says "Service Unreachable".

## Fix — 3 Steps

### Step 1: Deploy to Render (free)
1. Upload app.py, requirements.txt, Procfile to GitHub
2. Deploy on render.com (free tier)
3. Get your URL: https://hospital-voice-agent.onrender.com

### Step 2: Set Twilio Webhook
1. Go to https://console.twilio.com
2. Phone Numbers → Manage → Active Numbers → click your number
3. Under "Voice & Fax" → "A Call Comes In":
   - Set to: https://hospital-voice-agent.onrender.com/twilio/voice
   - Method: HTTP POST
4. Save

### Step 3: Test
Call your Twilio number → it should answer in the selected language!

## Free Twilio Trial
- Go to twilio.com → sign up free
- Get a free phone number
- $15 free credit included (enough for hundreds of calls)
