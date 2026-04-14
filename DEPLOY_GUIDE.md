# 🚀 Deploy Hospital Voice Agent to Cloud (Free)

## Option 1 — Render (RECOMMENDED — Free, easiest)

### Step 1: Create GitHub account & upload files
1. Go to https://github.com and sign up (free)
2. Click **"New repository"** → name it `hospital-voice-agent`
3. Click **"uploading an existing file"**
4. Drag & drop these files from your HospitalVoiceAgent folder:
   - app.py
   - requirements.txt
   - Procfile
   - .gitignore
5. Click **"Commit changes"**

### Step 2: Deploy on Render
1. Go to https://render.com → Sign up with GitHub
2. Click **"New +"** → **"Web Service"**
3. Connect your `hospital-voice-agent` GitHub repo
4. Fill in:
   - **Name:** hospital-voice-agent
   - **Runtime:** Python 3
   - **Build Command:** (leave empty)
   - **Start Command:** `python app.py`
5. Click **"Create Web Service"**
6. Wait 2 minutes → Render gives you a URL like:
   `https://hospital-voice-agent.onrender.com`

✅ That URL works anywhere in the world — send it to any hospital!

---

## Option 2 — Railway (Also free, very fast)

1. Go to https://railway.app → Sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your `hospital-voice-agent` repo
4. Railway auto-detects Python and deploys
5. Click **"Generate Domain"** to get your public URL

---

## Option 3 — Replit (Easiest, no GitHub needed)

1. Go to https://replit.com → Sign up
2. Click **"Create Repl"** → choose **Python**
3. Delete the default `main.py`
4. Upload `app.py` from your folder
5. Click the green **Run** button
6. Copy the public URL shown at the top

---

## To Add Your OpenAI API Key (for full AI mode)

On Render/Railway, go to your project → **Environment Variables** → Add:
```
OPENAI_API_KEY = sk-your-key-here
```

---

## Pricing to Sell to Hospitals

| Plan | Price | What to include |
|------|-------|-----------------|
| Basic | $500/month | Voice agent + appointment booking |
| Standard | $1,000/month | + Custom hospital branding |
| Premium | $2,500/month | + Full AI mode + Twilio phone calls |
