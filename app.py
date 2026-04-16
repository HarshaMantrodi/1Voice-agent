"""
Hospital Voice Agent v2.0 — Production Ready
Features:
  - Multi-language: English, Hindi, Kannada
  - Appointment booking, checking, cancellation
  - Call History & Admin Dashboard
  - Emergency detection (all 3 languages)
  - OpenAI GPT-4o-mini (optional — works without key)
  - Twilio phone/IVR support
  - Zero pip installs — Python standard library only

Run  : python app.py
Open : http://localhost:8080
Admin: http://localhost:8080/admin
"""
import http.server, socketserver, json, sqlite3, uuid, os, webbrowser, threading, re
from datetime import datetime

PORT = int(os.getenv("PORT", 8080))
DB   = os.path.join(os.getenv("TMPDIR", os.path.expanduser("~")), "hospital_agent.db")

# ══════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════
def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS appointments (
            id TEXT PRIMARY KEY,
            patient_name TEXT, patient_phone TEXT, patient_email TEXT,
            department TEXT, doctor_name TEXT,
            appointment_date TEXT, appointment_time TEXT,
            reason TEXT, status TEXT DEFAULT 'scheduled',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS call_history (
            id TEXT PRIMARY KEY,
            session_id TEXT UNIQUE,
            caller_name TEXT DEFAULT 'Unknown',
            caller_phone TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            channel TEXT DEFAULT 'web',
            started_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT,
            total_messages INTEGER DEFAULT 0,
            summary TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            language TEXT DEFAULT 'en',
            timestamp TEXT DEFAULT (datetime('now'))
        );
    """)
    c.commit(); c.close()

def db(sql, params=(), fetch=False, one=False):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    cur = con.execute(sql, params); con.commit()
    if one:   r = cur.fetchone(); con.close(); return dict(r) if r else None
    if fetch: r = [dict(x) for x in cur.fetchall()]; con.close(); return r
    con.close()

def log_message(session_id, role, content, language="en"):
    db("INSERT INTO messages(id,session_id,role,content,language) VALUES(?,?,?,?,?)",
       (str(uuid.uuid4()), session_id, role, content, language))
    db("UPDATE call_history SET total_messages=total_messages+1 WHERE session_id=?", (session_id,))

def ensure_session(session_id, language="en", channel="web"):
    existing = db("SELECT id FROM call_history WHERE session_id=?", (session_id,), one=True)
    if not existing:
        db("INSERT INTO call_history(id,session_id,language,channel) VALUES(?,?,?,?)",
           (str(uuid.uuid4()), session_id, language, channel))

def update_caller_info(session_id, name=None, phone=None):
    if name:  db("UPDATE call_history SET caller_name=? WHERE session_id=?", (name, session_id))
    if phone: db("UPDATE call_history SET caller_phone=? WHERE session_id=?", (phone, session_id))

def book_appt(d):
    aid = str(uuid.uuid4())
    db("INSERT INTO appointments(id,patient_name,patient_phone,patient_email,department,doctor_name,appointment_date,appointment_time,reason) VALUES(?,?,?,?,?,?,?,?,?)",
       (aid, d.get("patient_name",""), d.get("patient_phone",""), d.get("patient_email",""),
        d.get("department",""), d.get("doctor_name",""), d.get("appointment_date",""),
        d.get("appointment_time",""), d.get("reason","")))
    return db("SELECT * FROM appointments WHERE id=?", (aid,), one=True)

def get_appts_by_phone(phone):
    return db("SELECT * FROM appointments WHERE patient_phone=? AND status='scheduled' ORDER BY appointment_date,appointment_time", (phone,), fetch=True)

def cancel_appt(ref):
    rows = db("SELECT * FROM appointments WHERE UPPER(id) LIKE ? AND status='scheduled'", (ref.upper()+"%",), fetch=True)
    if rows:
        db("UPDATE appointments SET status='cancelled' WHERE id=?", (rows[0]["id"],))
        rows[0]["status"] = "cancelled"; return rows[0]
    return None

def get_stats():
    total   = db("SELECT COUNT(*) as n FROM appointments", one=True)["n"]
    sched   = db("SELECT COUNT(*) as n FROM appointments WHERE status='scheduled'", one=True)["n"]
    canc    = db("SELECT COUNT(*) as n FROM appointments WHERE status='cancelled'", one=True)["n"]
    sessions= db("SELECT COUNT(*) as n FROM call_history", one=True)["n"]
    msgs    = db("SELECT COUNT(*) as n FROM messages", one=True)["n"]
    en_c    = db("SELECT COUNT(*) as n FROM call_history WHERE language='en'", one=True)["n"]
    hi_c    = db("SELECT COUNT(*) as n FROM call_history WHERE language='hi'", one=True)["n"]
    kn_c    = db("SELECT COUNT(*) as n FROM call_history WHERE language='kn'", one=True)["n"]
    depts   = db("SELECT department, COUNT(*) as cnt FROM appointments GROUP BY department ORDER BY cnt DESC", fetch=True)
    return {"total":total,"scheduled":sched,"cancelled":canc,"sessions":sessions,
            "messages":msgs,"en":en_c,"hi":hi_c,"kn":kn_c,"depts":depts}

# ══════════════════════════════════════════════════════════════════
#  MULTILINGUAL STRINGS
# ══════════════════════════════════════════════════════════════════
T = {
    "greeting": {
        "en": "Welcome to City General Hospital! I can help you book appointments, check existing ones, answer hospital questions, or provide emergency guidance. How can I help you today?",
        "hi": "सिटी जनरल अस्पताल में आपका स्वागत है! मैं अपॉइंटमेंट बुक करने, मौजूदा अपॉइंटमेंट चेक करने, और अस्पताल के सवालों के जवाब देने में मदद कर सकता हूं। आज मैं आपकी कैसे मदद कर सकता हूं?",
        "kn": "ಸಿಟಿ ಜನರಲ್ ಆಸ್ಪತ್ರೆಗೆ ಸ್ವಾಗತ! ನಾನು ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು, ಪರಿಶೀಲಿಸಲು ಮತ್ತು ಆಸ್ಪತ್ರೆ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಲು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"
    },
    "ask_name":   {"en":"I'd love to help you book an appointment! What is your full name?","hi":"मैं आपकी अपॉइंटमेंट बुक करने में मदद करूंगा! आपका पूरा नाम क्या है?","kn":"ನಾನು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ! ನಿಮ್ಮ ಪೂರ್ಣ ಹೆಸರು ಏನು?"},
    "ask_phone":  {"en":"Nice to meet you, {name}! What is your phone number?","hi":"आपसे मिलकर खुशी हुई, {name}! आपका फोन नंबर क्या है?","kn":"ನಿಮ್ಮನ್ನು ಭೇಟಿಯಾಗಿ ಸಂತೋಷ, {name}! ನಿಮ್ಮ ಫೋನ್ ನಂಬರ್ ಏನು?"},
    "ask_dept":   {"en":"Which department do you need?\n\nCardiology · Neurology · Orthopedics · Pediatrics · Oncology · Dermatology · Surgery · Internal Medicine · OB/GYN · ENT · Psychiatry","hi":"आपको किस विभाग में जाना है?\n\nहृदय रोग · तंत्रिका विज्ञान · हड्डी रोग · बाल रोग · कैंसर · त्वचा रोग · शल्य चिकित्सा · आंतरिक चिकित्सा · ENT","kn":"ನಿಮಗೆ ಯಾವ ವಿಭಾಗ ಬೇಕು?\n\nಹೃದ್ರೋಗ · ನರವಿಜ್ಞಾನ · ಮೂಳೆ ರೋಗ · ಮಕ್ಕಳ ತಜ್ಞ · ಚರ್ಮರೋಗ · ಶಸ್ತ್ರಚಿಕಿತ್ಸೆ · ENT"},
    "ask_date":   {"en":"What date would you like? (format: YYYY-MM-DD)\nAvailable: 9:00 · 9:30 · 10:00 · 10:30 · 11:00 · 14:00 · 14:30 · 15:00","hi":"आप किस तारीख को चाहते हैं? (प्रारूप: YYYY-MM-DD)","kn":"ನೀವು ಯಾವ ದಿನಾಂಕ ಬಯಸುತ್ತೀರಿ? (ರೂಪ: YYYY-MM-DD)"},
    "ask_time":   {"en":"What time would you prefer?\nAvailable: 9:00 · 9:30 · 10:00 · 10:30 · 11:00 · 14:00 · 14:30 · 15:00","hi":"आप किस समय चाहते हैं?\nउपलब्ध: 9:00, 9:30, 10:00, 10:30, 11:00, 14:00, 14:30, 15:00","kn":"ನೀವು ಯಾವ ಸಮಯ ಬಯಸುತ್ತೀರಿ?\nಲಭ್ಯ: 9:00, 9:30, 10:00, 10:30, 11:00, 14:00, 14:30, 15:00"},
    "confirm_booking":{"en":"Please confirm your appointment:\n\n👤 Name: {name}\n📱 Phone: {phone}\n🏥 Dept: {dept}\n📅 Date: {date} at {time}\n\nType YES to confirm or NO to cancel.","hi":"कृपया अपनी अपॉइंटमेंट की पुष्टि करें:\n\n👤 नाम: {name}\n📱 फोन: {phone}\n🏥 विभाग: {dept}\n📅 तारीख: {date} समय: {time}\n\nपुष्टि के लिए YES टाइप करें।","kn":"ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದೃಢೀಕರಿಸಿ:\n\n👤 ಹೆಸರು: {name}\n📱 ಫೋನ್: {phone}\n🏥 ವಿಭಾಗ: {dept}\n📅 ದಿನಾಂಕ: {date} ಸಮಯ: {time}\n\nದೃಢೀಕರಿಸಲು YES ಟೈಪ್ ಮಾಡಿ."},
    "booked":     {"en":"✅ Appointment Confirmed!\n\n📋 Ref: {ref}\n📅 {date} at {time}\n🏥 {dept}\n\nPlease save your reference number.","hi":"✅ अपॉइंटमेंट की पुष्टि हो गई!\n\n📋 संदर्भ: {ref}\n📅 {date} समय {time}\n🏥 {dept}","kn":"✅ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದೃಢೀಕರಿಸಲಾಗಿದೆ!\n\n📋 ರೆಫ್: {ref}\n📅 {date} ಸಮಯ {time}\n🏥 {dept}"},
    "cancelled":  {"en":"Booking cancelled. How else can I help you?","hi":"अपॉइंटमेंट रद्द कर दी गई। मैं और कैसे मदद करूं?","kn":"ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ರದ್ದು ಮಾಡಲಾಗಿದೆ. ನಾನು ಇನ್ನೂ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"},
    "ask_phone_check":{"en":"Please share your phone number to look up your appointments.","hi":"अपनी अपॉइंटमेंट देखने के लिए अपना फोन नंबर बताएं।","kn":"ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ನೋಡಲು ನಿಮ್ಮ ಫೋನ್ ನಂಬರ್ ಹಂಚಿಕೊಳ್ಳಿ."},
    "no_appts":   {"en":"No active appointments found for {phone}. Would you like to book one?","hi":"{phone} के लिए कोई अपॉइंटमेंट नहीं मिली। क्या आप एक बुक करना चाहते हैं?","kn":"{phone} ಗೆ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಕಂಡುಬಂದಿಲ್ಲ. ಒಂದನ್ನು ಬುಕ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಾ?"},
    "ask_cancel_ref":{"en":"Please provide your booking reference number (e.g. A1B2C3D4).","hi":"कृपया अपना बुकिंग संदर्भ नंबर बताएं।","kn":"ದಯವಿಟ್ಟು ನಿಮ್ಮ ಬುಕಿಂಗ್ ರೆಫರೆನ್ಸ್ ನಂಬರ್ ನೀಡಿ."},
    "cancel_ok":  {"en":"✅ Appointment {ref} cancelled successfully. Is there anything else I can help with?","hi":"✅ अपॉइंटमेंट {ref} सफलतापूर्वक रद्द।","kn":"✅ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ {ref} ಯಶಸ್ವಿಯಾಗಿ ರದ್ದು."},
    "cancel_fail":{"en":"No active appointment found with reference \"{ref}\". Please double-check your booking reference.","hi":"संदर्भ \"{ref}\" के साथ कोई सक्रिय अपॉइंटमेंट नहीं मिली।","kn":"ರೆಫರೆನ್ಸ್ \"{ref}\" ನೊಂದಿಗೆ ಯಾವುದೇ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಕಂಡುಬಂದಿಲ್ಲ."},
    "emergency":  {"en":"⚠️ MEDICAL EMERGENCY!\n\nCall 911 immediately or go to our Emergency Room (Ground Floor).\n☎️ Emergency: 1-800-555-0911\n\nDo NOT drive yourself. Call 911 NOW.","hi":"⚠️ चिकित्सा आपातकाल!\n\nतुरंत 911 पर कॉल करें या भूतल के आपातकालीन कक्ष में जाएं।\n☎️ आपातकालीन: 1-800-555-0911","kn":"⚠️ ವೈದ್ಯಕೀಯ ತುರ್ತು!\n\nತಕ್ಷಣ 911 ಗೆ ಕರೆ ಮಾಡಿ ಅಥವಾ ತುರ್ತು ಕೊಠಡಿಗೆ (ನೆಲ ಮಹಡಿ) ಹೋಗಿ.\n☎️ ತುರ್ತು: 1-800-555-0911"},
    "hours":      {"en":"Outpatient: Mon–Fri 8AM–6PM. Emergency: 24/7. Visiting: Daily 9AM–8PM. Pharmacy: Mon–Sat 8AM–9PM.","hi":"बाह्य रोगी: सोम–शुक्र 8AM–6PM। आपातकाल: 24/7। मुलाकात: रोज 9AM–8PM।","kn":"ಹೊರರೋಗಿ: ಸೋಮ–ಶುಕ್ರ 8AM–6PM. ತುರ್ತು: 24/7. ಭೇಟಿ: ದಿನಂಪ್ರತಿ 9AM–8PM."},
    "location":   {"en":"123 Health Avenue, Medical District. Near Central Metro Station. Free parking in Lots A, B, C.","hi":"123 हेल्थ एवेन्यू, मेडिकल डिस्ट्रिक्ट। सेंट्रल मेट्रो स्टेशन के पास। मुफ्त पार्किंग।","kn":"123 ಹೆಲ್ತ್ ಅವೆನ್ಯೂ, ಮೆಡಿಕಲ್ ಡಿಸ್ಟ್ರಿಕ್ಟ್. ಸೆಂಟ್ರಲ್ ಮೆಟ್ರೋ ಸಮೀಪ. ಉಚಿತ ಪಾರ್ಕಿಂಗ್."},
    "default":    {"en":"I can help you:\n• 📅 Book, check, or cancel appointments\n• ℹ️ Answer hospital questions\n• 🚨 Emergency guidance\n\nWhat would you like?","hi":"मैं मदद कर सकता हूं:\n• 📅 अपॉइंटमेंट बुक, चेक या रद्द\n• ℹ️ अस्पताल के सवाल\n• 🚨 आपातकालीन मार्गदर्शन","kn":"ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ:\n• 📅 ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್, ಪರಿಶೀಲಿಸಿ ಅಥವಾ ರದ್ದು\n• ℹ️ ಆಸ್ಪತ್ರೆ ಪ್ರಶ್ನೆಗಳು\n• 🚨 ತುರ್ತು ಮಾರ್ಗದರ್ಶನ"}
}

def t(key, lang, **kwargs):
    text = T.get(key, {}).get(lang) or T.get(key, {}).get("en", "")
    for k, v in kwargs.items():
        text = text.replace("{"+k+"}", str(v))
    return text

EW = ["emergency","heart attack","stroke","can't breathe","cannot breathe","chest pain",
      "unconscious","bleeding","severe pain","dying","overdose","choking","not breathing",
      "seizure","fainted","collapsed","anaphylaxis","code blue",
      "दिल का दौरा","सांस नहीं","सीने में दर्द","आपातकाल","बेहोश",
      "ಹೃದಯ ಸ್ತಂಭನ","ಉಸಿರಾಡಲು","ಎದೆ ನೋವು","ತುರ್ತು","ಪ್ರಜ್ಞೆ ತಪ್ಪಿದೆ"]

def is_emg(msg): return any(w in msg.lower() for w in EW)

FAQS = {
    "en": [
        (["hours","open","timing","close","when"],       "Outpatient: Mon–Fri 8AM–6PM. Emergency: 24/7. Visiting: Daily 9AM–8PM."),
        (["location","address","where","direction"],     "123 Health Avenue, Medical District. Near Central Metro. Free parking in Lots A, B, C."),
        (["parking"],                                    "Free parking in Lots A, B, C. Valet at Main Entrance $10."),
        (["insurance","accept","cover"],                 "We accept Medicare, Medicaid, BlueCross, Aetna, Cigna, United Health."),
        (["department","specialist","specialty"],        "14 departments: Cardiology, Neurology, Orthopedics, Pediatrics, Oncology, Radiology, Surgery, OB/GYN, Psychiatry, Dermatology, Ophthalmology, ENT, Internal Medicine, Emergency."),
        (["doctor","physician","staff"],                 "Our team: Dr. Sarah Johnson (Cardiology), Dr. Michael Chen (Neurology), Dr. Emily Rodriguez (Pediatrics), Dr. James Patel (Orthopedics)."),
        (["pharmacy","medicine","prescription"],         "Pharmacy: Ground Floor. Hours: Mon–Sat 8AM–9PM."),
        (["wait","er","emergency room","how long"],      "Life-threatening: seen immediately. Non-urgent: 1–3 hours average."),
        (["records","medical","history","report"],       "Medical Records: 1st Floor or call 1-800-555-0100."),
        (["fee","cost","price","charge","billing"],      "Consultation starts at $150. Insurance co-pay may apply. Call billing: 1-800-555-0200."),
        (["wifi","internet","password"],                 "Free WiFi: HospitalGuest. No password needed."),
        (["cafeteria","food","eat","canteen"],           "Cafeteria: Ground Floor. Open 7AM–9PM. Vending machines available 24/7."),
    ],
    "hi": [
        (["समय","खुला","बंद","घंटे","कब"],              "बाह्य रोगी: सोम–शुक्र 8AM–6PM। आपातकाल: 24/7। मुलाकात: रोज 9AM–8PM।"),
        (["पता","स्थान","कहाँ","दिशा"],                 "123 हेल्थ एवेन्यू, मेडिकल डिस्ट्रिक्ट। सेंट्रल मेट्रो के पास।"),
        (["विभाग","स्पेशलिस्ट"],                        "14 विभाग: हृदय रोग, तंत्रिका विज्ञान, हड्डी रोग, बाल रोग और अधिक।"),
        (["बीमा","इंश्योरेंस"],                         "हम Medicare, Medicaid, BlueCross, Aetna, Cigna स्वीकार करते हैं।"),
        (["फीस","कितना","शुल्क"],                       "परामर्श शुल्क $150 से शुरू। बिलिंग: 1-800-555-0200।"),
    ],
    "kn": [
        (["ಸಮಯ","ತೆರೆದಿರುತ್ತದೆ","ಮುಚ್ಚುತ್ತದೆ","ಯಾವಾಗ"], "ಹೊರರೋಗಿ: ಸೋಮ–ಶುಕ್ರ 8AM–6PM. ತುರ್ತು: 24/7."),
        (["ವಿಳಾಸ","ಎಲ್ಲಿ","ಸ್ಥಳ"],                     "123 ಹೆಲ್ತ್ ಅವೆನ್ಯೂ, ಮೆಡಿಕಲ್ ಡಿಸ್ಟ್ರಿಕ್ಟ್."),
        (["ವಿಭಾಗ","ತಜ್ಞ"],                              "14 ವಿಭಾಗಗಳು: ಹೃದ್ರೋಗ, ನರವಿಜ್ಞಾನ, ಮೂಳೆ ರೋಗ, ಮಕ್ಕಳ ತಜ್ಞ ಮತ್ತು ಇನ್ನಷ್ಟು."),
        (["ವಿಮೆ","ಇನ್ಷೂರೆನ್ಸ್"],                        "ನಾವು Medicare, Medicaid, BlueCross, Aetna, Cigna ಸ್ವೀಕರಿಸುತ್ತೇವೆ."),
        (["ಶುಲ್ಕ","ಬೆಲೆ","ಎಷ್ಟು"],                       "ಸಮಾಲೋಚನೆ $150 ರಿಂದ ಪ್ರಾರಂಭ. ಬಿಲ್ಲಿಂಗ್: 1-800-555-0200."),
    ]
}

def find_faq(msg, lang):
    ml = msg.lower()
    for keywords, answer in FAQS.get(lang, FAQS["en"]):
        if any(k in ml for k in keywords):
            return answer
    for keywords, answer in FAQS["en"]:
        if any(k in ml for k in keywords):
            return answer
    return None

# ══════════════════════════════════════════════════════════════════
#  CONVERSATION STATE
# ══════════════════════════════════════════════════════════════════
_CTX = {}

def get_ctx(sid):
    if sid not in _CTX:
        _CTX[sid] = {"stage": None, "data": {}, "lang": "en"}
    return _CTX[sid]

def local_reply(msg, sid):
    ctx  = get_ctx(sid)
    lang = ctx["lang"]
    ml   = msg.lower().strip()

    if ctx["stage"] == "name":
        ctx["data"]["patient_name"] = msg.strip()
        ctx["stage"] = "phone"
        update_caller_info(sid, name=msg.strip())
        return t("ask_phone", lang, name=msg.strip())

    if ctx["stage"] == "phone":
        ph = msg.strip()
        if len(re.sub(r'[\s\-\+\(\)]','',ph)) < 7:
            return {"en":"Please enter a valid phone number (at least 7 digits).","hi":"कृपया वैध फोन नंबर दर्ज करें।","kn":"ದಯವಿಟ್ಟು ಮಾನ್ಯ ಫೋನ್ ನಂಬರ್ ನಮೂದಿಸಿ."}.get(lang,"Please enter a valid phone number.")
        ctx["data"]["patient_phone"] = ph
        ctx["stage"] = "dept"
        update_caller_info(sid, phone=ph)
        return t("ask_dept", lang)

    if ctx["stage"] == "dept":
        depts = ["Cardiology","Neurology","Orthopedics","Pediatrics","Oncology",
                 "Dermatology","General Surgery","Internal Medicine","OB/GYN","ENT","Psychiatry","Radiology"]
        match = next((d for d in depts if d.lower() in ml), msg.strip().title())
        ctx["data"]["department"] = match
        ctx["stage"] = "date"
        return t("ask_date", lang)

    if ctx["stage"] == "date":
        dm = re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', msg)
        if not dm:
            return {"en":"Please use YYYY-MM-DD format (e.g. 2025-03-15).","hi":"कृपया YYYY-MM-DD प्रारूप उपयोग करें।","kn":"ದಯವಿಟ್ಟು YYYY-MM-DD ರೂಪ ಬಳಸಿ."}.get(lang,"Please use YYYY-MM-DD format.")
        ctx["data"]["appointment_date"] = dm.group().replace("/","-")
        ctx["stage"] = "time"
        return t("ask_time", lang)

    if ctx["stage"] == "time":
        tm = re.search(r'\d{1,2}:\d{2}', msg) or re.search(r'\d{1,2}\s*(am|pm)', msg, re.I)
        if not tm:
            return {"en":"Please pick a time like 9:00 or 14:30.","hi":"9:00 या 14:30 जैसा समय चुनें।","kn":"9:00 ಅಥವಾ 14:30 ರೀತಿ ಸಮಯ ಆಯ್ಕೆ ಮಾಡಿ."}.get(lang,"Please pick a valid time.")
        ctx["data"]["appointment_time"] = tm.group()
        ctx["stage"] = "confirm"
        d = ctx["data"]
        return t("confirm_booking", lang, name=d.get("patient_name",""), phone=d.get("patient_phone",""),
                 dept=d.get("department",""), date=d.get("appointment_date",""), time=d.get("appointment_time",""))

    if ctx["stage"] == "confirm":
        yes_words = ["yes","confirm","ok","y","sure","yeah","yep","हाँ","हां","ठीक","ಹೌದು","ಸರಿ"]
        if any(w in ml for w in yes_words):
            appt = book_appt(ctx["data"])
            ctx["stage"] = None; ctx["data"] = {}
            return {"text": t("booked", lang, ref=appt["id"][:8].upper(),
                              date=appt["appointment_date"], time=appt["appointment_time"],
                              dept=appt["department"]), "appt": appt}
        else:
            ctx["stage"] = None; ctx["data"] = {}
            return t("cancelled", lang)

    if ctx["stage"] == "check_phone":
        appts = get_appts_by_phone(msg.strip())
        ctx["stage"] = None
        if not appts: return t("no_appts", lang, phone=msg.strip())
        lines = [f"📅 {a['appointment_date']} {a['appointment_time']} — {a['department']} | Ref: {a['id'][:8].upper()}" for a in appts]
        hdr = {"en":f"Found {len(appts)} appointment(s):","hi":f"{len(appts)} अपॉइंटमेंट मिली:","kn":f"{len(appts)} ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸಿಕ್ಕಿದೆ:"}.get(lang,f"Found {len(appts)} appointment(s):")
        return hdr + "\n\n" + "\n".join(lines)

    if ctx["stage"] == "cancel_ref":
        ref = msg.strip().upper()
        cancelled = cancel_appt(ref)
        ctx["stage"] = None
        if cancelled: return t("cancel_ok", lang, ref=cancelled["id"][:8].upper())
        return t("cancel_fail", lang, ref=ref)

    # Intent detection
    book_kw   = ["book","schedule","new appointment","make appointment","अपॉइंटमेंट बुक","बुक करें","ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್","ಬುಕ್ ಮಾಡಿ"]
    check_kw  = ["check","my appointment","existing","upcoming","मेरी अपॉइंटमेंट","ನನ್ನ ಅಪಾಯಿಂಟ್ಮೆಂಟ್","ಪರಿಶೀಲಿಸಿ"]
    cancel_kw = ["cancel","cancellation","रद्द","कैंसिल","ರದ್ದು"]

    if any(w in ml for w in book_kw) and not any(w in ml for w in check_kw):
        ctx["stage"] = "name"; ctx["data"] = {}
        return t("ask_name", lang)
    if any(w in ml for w in check_kw):
        ctx["stage"] = "check_phone"
        return t("ask_phone_check", lang)
    if any(w in ml for w in cancel_kw):
        ctx["stage"] = "cancel_ref"
        return t("ask_cancel_ref", lang)
    if any(w in ml for w in ["location","address","where","पता","कहाँ","ವಿಳಾಸ","ಎಲ್ಲಿ"]):
        return t("location", lang)
    if any(w in ml for w in ["hours","timing","open","समय","खुला","ಸಮಯ","ತೆರೆ"]):
        return t("hours", lang)

    faq = find_faq(msg, lang)
    if faq: return faq
    return t("default", lang)

# ══════════════════════════════════════════════════════════════════
#  MAIN WEB UI
# ══════════════════════════════════════════════════════════════════
HTML_APP = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>City General Hospital — Voice Assistant</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --p:#1a73e8;--pd:#1557b0;--g:#0f9d58;--r:#d93025;--o:#f9ab00;
  --bg:#eef2ff;--card:#fff;--tx:#202124;--mu:#5f6368;--bd:#dadce0;
  --sh:0 4px 20px rgba(0,0,0,.09)
}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;display:flex;flex-direction:column}

/* HEADER */
header{background:linear-gradient(135deg,#1b3a6b 0%,#1a73e8 100%);color:#fff;padding:14px 22px;display:flex;align-items:center;gap:12px;box-shadow:0 3px 16px rgba(0,0,0,.25)}
.h-icon{font-size:2rem;animation:pulse 3s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}
.h-text h1{font-size:1.25rem;font-weight:700;letter-spacing:-.3px}
.h-text p{font-size:.77rem;opacity:.82;margin-top:2px}
.h-right{margin-left:auto;display:flex;align-items:center;gap:8px}
.badge{background:rgba(255,255,255,.18);border-radius:20px;padding:4px 12px;font-size:.72rem;font-weight:700;letter-spacing:.5px}
.hbtn{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);color:#fff;border-radius:8px;padding:6px 13px;font-size:.76rem;cursor:pointer;text-decoration:none;font-weight:600;transition:background .2s}
.hbtn:hover{background:rgba(255,255,255,.24)}

/* LANG BAR */
#langbar{background:#fff;border-bottom:2px solid var(--bd);padding:9px 18px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
#langbar label{font-size:.8rem;font-weight:600;color:var(--mu)}
.lbtn{border:2px solid var(--bd);background:#fff;border-radius:20px;padding:5px 15px;font-size:.8rem;cursor:pointer;transition:all .18s;font-weight:500}
.lbtn.on{border-color:var(--p);background:#e8f0fe;color:var(--p);font-weight:700}
.lbtn:hover{border-color:var(--p)}

/* API BAR */
#apibar{background:#fffde7;border-bottom:2px solid #f9ab00;padding:7px 18px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:.8rem}
#apibar strong{color:#e65100}
#akey{flex:1;min-width:180px;border:1.5px solid #f9ab00;border-radius:8px;padding:5px 10px;font-size:.8rem;font-family:monospace;outline:none}
#savebtn{background:var(--p);color:#fff;border:none;border-radius:8px;padding:6px 13px;cursor:pointer;font-size:.78rem;font-weight:600}
.anote{color:#795548;font-size:.74rem}

/* MAIN LAYOUT */
main{flex:1;max-width:820px;width:100%;margin:0 auto;padding:14px 12px;display:flex;flex-direction:column;gap:12px}

/* EMERGENCY BANNER */
#ebanner{display:none;background:var(--r);color:#fff;padding:12px 18px;border-radius:12px;font-weight:700;text-align:center;font-size:.9rem;animation:fadein .3s ease}
#ebanner a{color:#fff;font-weight:800}
@keyframes fadein{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}

/* QUICK BUTTONS */
.qgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
@media(min-width:500px){.qgrid{grid-template-columns:repeat(4,1fr)}}
.qb{background:var(--card);border:2px solid var(--bd);border-radius:12px;padding:12px 6px;cursor:pointer;text-align:center;transition:all .18s;font-size:.79rem;font-weight:500;line-height:1.4}
.qb:hover{border-color:var(--p);background:#e8f0fe;transform:translateY(-2px);box-shadow:var(--sh)}
.qi{font-size:1.5rem;display:block;margin-bottom:4px}

/* CHAT CARD */
.chat-card{background:var(--card);border-radius:14px;box-shadow:var(--sh);display:flex;flex-direction:column;overflow:hidden;border:1px solid var(--bd)}
.chat-hdr{padding:10px 16px;background:#f8f9fa;border-bottom:1px solid var(--bd);display:flex;align-items:center;gap:8px;font-size:.84rem;font-weight:600;color:var(--mu)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--g);box-shadow:0 0 0 3px rgba(15,157,88,.18);animation:glow 2s ease-in-out infinite}
@keyframes glow{0%,100%{box-shadow:0 0 0 3px rgba(15,157,88,.18)}50%{box-shadow:0 0 0 5px rgba(15,157,88,.1)}}
.tts-wrap{margin-left:auto;display:flex;align-items:center;gap:5px;font-size:.76rem;cursor:pointer}
.tog{position:relative;width:34px;height:18px}
.tog input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#ccc;border-radius:18px;transition:.3s;cursor:pointer}
.sl::before{content:'';position:absolute;height:12px;width:12px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.3s}
input:checked+.sl{background:var(--p)}input:checked+.sl::before{transform:translateX(16px)}

#msgs{height:360px;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth}
#msgs::-webkit-scrollbar{width:4px}#msgs::-webkit-scrollbar-thumb{background:#ccc;border-radius:10px}

.mw{display:flex;flex-direction:column}
.mw.uw{align-items:flex-end}
.msg{max-width:84%;padding:10px 14px;border-radius:16px;line-height:1.58;font-size:.88rem;animation:popin .22s ease;white-space:pre-wrap;word-break:break-word}
@keyframes popin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.msg.bot{background:#e8f0fe;border-bottom-left-radius:3px;color:#1b2a4a}
.msg.bot.emg{background:#fce8e6;border:2px solid var(--r);font-weight:600}
.msg.usr{background:var(--p);color:#fff;border-bottom-right-radius:3px}
.mtime{font-size:.66rem;opacity:.45;margin-top:2px;padding:0 3px}

/* TYPING */
.typ{display:none;align-items:center;gap:4px;padding:9px 13px;background:#e8f0fe;border-radius:16px;border-bottom-left-radius:3px;width:fit-content;margin:4px 16px}
.typ span{width:6px;height:6px;border-radius:50%;background:var(--p);animation:bounce 1.2s infinite}
.typ span:nth-child(2){animation-delay:.2s}
.typ span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-7px)}}

/* INPUT AREA */
.inp-row{padding:10px 14px;border-top:1px solid var(--bd);display:flex;gap:7px;align-items:center;background:#fafafa}
#tin{flex:1;border:2px solid var(--bd);border-radius:22px;padding:9px 15px;font-size:.88rem;outline:none;transition:border-color .2s;font-family:inherit;background:#fff}
#tin:focus{border-color:var(--p)}
#tin::placeholder{color:#bbb}
.abtn{border:none;border-radius:50%;width:42px;height:42px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1rem;transition:all .2s;flex-shrink:0}
#sbtn{background:var(--p);color:#fff}#sbtn:hover{background:var(--pd);transform:scale(1.05)}
#mbtn{background:#f1f3f4}#mbtn:hover{background:#e8f0fe}
#mbtn.rec{background:var(--r);color:#fff;animation:recpulse 1s infinite}
@keyframes recpulse{0%,100%{box-shadow:0 0 0 0 rgba(217,48,37,.35)}50%{box-shadow:0 0 0 9px rgba(217,48,37,0)}}
.waves{display:none;align-items:center;gap:2px;height:26px}
.waves.on{display:flex}
.wave{width:3px;border-radius:2px;background:var(--r);animation:waveanim .8s ease-in-out infinite}
.wave:nth-child(1){height:7px}.wave:nth-child(2){height:14px;animation-delay:.1s}.wave:nth-child(3){height:22px;animation-delay:.2s}.wave:nth-child(4){height:14px;animation-delay:.3s}.wave:nth-child(5){height:7px;animation-delay:.4s}
@keyframes waveanim{0%,100%{transform:scaleY(.4)}50%{transform:scaleY(1)}}

/* APPOINTMENT CARD */
.appt-card{background:linear-gradient(135deg,#e6f4ea,#d0ebd8);border:1px solid #a8d5b5;border-radius:11px;padding:13px 15px;margin-top:7px;font-size:.84rem}
.appt-card h4{color:var(--g);margin-bottom:7px;font-size:.9rem}
.ref-code{font-size:1.1rem;font-weight:700;font-family:monospace;letter-spacing:3px;color:var(--g);background:#fff;padding:3px 9px;border-radius:6px;display:inline-block;margin:4px 0}
.appt-row{margin:3px 0;font-size:.83rem}

/* CHIPS */
.chips{display:flex;gap:7px;flex-wrap:wrap;justify-content:center}
.chip{text-decoration:none;background:var(--card);border:2px solid var(--bd);border-radius:22px;padding:7px 14px;font-size:.78rem;font-weight:500;color:var(--tx);transition:all .18s}
.chip:hover{border-color:var(--p);background:#e8f0fe}
.chip.red{border-color:#fcc;color:var(--r)}
.chip.red:hover{background:#fce8e6;border-color:var(--r)}

footer{text-align:center;padding:11px;font-size:.7rem;color:var(--mu);border-top:1px solid var(--bd)}
</style>
</head><body>
<header>
  <div class="h-icon">🏥</div>
  <div class="h-text"><h1>City General Hospital</h1><p>AI Voice Assistant · 24/7</p></div>
  <div class="h-right">
    <a class="hbtn" href="/admin">📊 Admin</a>
    <a class="hbtn" href="/history">📞 History</a>
    <span class="badge">🟢 LIVE</span>
  </div>
</header>

<div id="langbar">
  <label>🌐 Language:</label>
  <button class="lbtn on" onclick="setLang('en','en-US',this)">🇬🇧 English</button>
  <button class="lbtn"   onclick="setLang('hi','hi-IN',this)">🇮🇳 हिंदी</button>
  <button class="lbtn"   onclick="setLang('kn','kn-IN',this)">🇮🇳 ಕನ್ನಡ</button>
</div>

<div id="apibar">
  <strong>🔑 OpenAI (optional):</strong>
  <input id="akey" type="password" placeholder="sk-... paste your key for GPT-4o-mini mode"/>
  <button id="savebtn">Save Key</button>
  <span class="anote" id="anote">💡 Works without key — smart built-in AI active</span>
</div>

<main>
  <div id="ebanner">🚨 MEDICAL EMERGENCY — Call <a href="tel:911">911</a> immediately | ER Line: <a href="tel:18005550911">1-800-555-0911</a></div>

  <div class="qgrid">
    <button class="qb" onclick="quick('book')"><span class="qi">📅</span><span id="ql0">Book Appointment</span></button>
    <button class="qb" onclick="quick('check')"><span class="qi">🔍</span><span id="ql1">Check Appointments</span></button>
    <button class="qb" onclick="quick('cancel')"><span class="qi">❌</span><span id="ql2">Cancel Appointment</span></button>
    <button class="qb" onclick="quick('info')"><span class="qi">ℹ️</span><span id="ql3">Hospital Info</span></button>
  </div>

  <div class="chat-card">
    <div class="chat-hdr">
      <div class="dot"></div>
      <span id="agent-name">Hospital AI Assistant</span>
      <div class="tts-wrap">
        🔊
        <label class="tog"><input type="checkbox" id="ttschk" checked/><span class="sl"></span></label>
      </div>
    </div>
    <div id="msgs"></div>
    <div class="typ" id="typ"><span></span><span></span><span></span></div>
    <div class="inp-row">
      <div class="waves" id="waves"><div class="wave"></div><div class="wave"></div><div class="wave"></div><div class="wave"></div><div class="wave"></div></div>
      <input id="tin" type="text" placeholder="Type or tap 🎤 to speak…" autocomplete="off"/>
      <button class="abtn" id="mbtn" title="Microphone">🎤</button>
      <button class="abtn" id="sbtn" title="Send">➤</button>
    </div>
  </div>

  <div class="chips">
    <a class="chip" href="tel:18005550100">📞 Main: 1-800-555-0100</a>
    <a class="chip" href="tel:18005550200">📅 Appts: 1-800-555-0200</a>
    <a class="chip red" href="tel:18005550911">🚨 ER: 1-800-555-0911</a>
  </div>
</main>
<footer>City General Hospital · 123 Health Avenue · AI Voice Assistant v2.0</footer>

<script>
const LABELS={
  en:['Book Appointment','Check Appointments','Cancel Appointment','Hospital Info'],
  hi:['अपॉइंटमेंट बुक करें','अपॉइंटमेंट जांचें','अपॉइंटमेंट रद्द करें','अस्पताल जानकारी'],
  kn:['ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್ ಮಾಡಿ','ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಪರಿಶೀಲಿಸಿ','ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ರದ್ದು ಮಾಡಿ','ಆಸ್ಪತ್ರೆ ಮಾಹಿತಿ']
};
const QUICK={
  en:{book:'I want to book a new appointment',check:'Check my existing appointments',cancel:'Cancel my appointment',info:'Hospital hours and location'},
  hi:{book:'मुझे नई अपॉइंटमेंट बुक करनी है',check:'मेरी अपॉइंटमेंट चेक करें',cancel:'अपॉइंटमेंट रद्द करें',info:'अस्पताल का समय और पता'},
  kn:{book:'ನಾನು ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ಬಯಸುತ್ತೇನೆ',check:'ನನ್ನ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಪರಿಶೀಲಿಸಿ',cancel:'ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ರದ್ದು ಮಾಡಿ',info:'ಆಸ್ಪತ್ರೆ ಸಮಯ ಮತ್ತು ಸ್ಥಳ'}
};
const AGENTS={en:'Hospital AI Assistant',hi:'अस्पताल AI सहायक',kn:'ಆಸ್ಪತ್ರೆ AI ಸಹಾಯಕ'};
const PH={en:'Type or tap 🎤 to speak…',hi:'यहाँ टाइप करें या 🎤 दबाएं…',kn:'ಇಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ ಅಥವಾ 🎤 ಒತ್ತಿ…'};

let lang='en', srLang='en-US', apiKey='', sid=null, synth=window.speechSynthesis;

function setLang(l,sl,btn){
  lang=l; srLang=sl;
  document.querySelectorAll('.lbtn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.getElementById('tin').placeholder=PH[l];
  document.getElementById('agent-name').textContent=AGENTS[l];
  [0,1,2,3].forEach(i=>document.getElementById('ql'+i).textContent=LABELS[l][i]);
  if(rec) rec.lang=sl;
}
function quick(k){ send(QUICK[lang][k]); }

window.addEventListener('load',()=>{
  const h=new Date().getHours();
  const tod=h<12?{en:'morning',hi:'प्रभात',kn:'ಶುಭೋದಯ'}[lang]
              :h<17?{en:'afternoon',hi:'दोपहर',kn:'ಮಧ್ಯಾಹ್ನ'}[lang]
                   :{en:'evening',hi:'शाम',kn:'ಸಂಜೆ'}[lang];
  const greet={
    en:`Good ${tod}! 👋 Welcome to City General Hospital.\n\nI can help you:\n• 📅 Book, check or cancel appointments\n• ℹ️ Answer hospital questions\n• 🚨 Emergency guidance\n\nHow can I help you today?`,
    hi:`शुभ ${tod}! 👋 सिटी जनरल अस्पताल में आपका स्वागत है।\n\nमैं मदद कर सकता हूं:\n• 📅 अपॉइंटमेंट बुक, चेक या रद्द\n• ℹ️ अस्पताल के सवाल\n• 🚨 आपातकालीन मार्गदर्शन\n\nआज मैं आपकी कैसे मदद करूं?`,
    kn:`ಶುಭ ${tod}! 👋 ಸಿಟಿ ಜನರಲ್ ಆಸ್ಪತ್ರೆಗೆ ಸ್ವಾಗತ.\n\nನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ:\n• 📅 ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್, ಪರಿಶೀಲಿಸಿ ಅಥವಾ ರದ್ದು\n• ℹ️ ಆಸ್ಪತ್ರೆ ಪ್ರಶ್ನೆಗಳು\n• 🚨 ತುರ್ತು ಮಾರ್ಗದರ್ಶನ\n\nಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?`
  };
  addMsg(greet[lang]||greet.en,'bot');
});

document.getElementById('savebtn').onclick=()=>{
  apiKey=document.getElementById('akey').value.trim();
  const bar=document.getElementById('apibar'), note=document.getElementById('anote');
  if(apiKey){
    bar.style.background='#e8f5e9'; bar.style.borderBottomColor='#0f9d58';
    note.textContent='✅ Key saved — GPT-4o-mini mode active!'; note.style.color='#0f9d58';
  }
};

function addMsg(text, role, isEmg=false, appt=null){
  const wrap=document.createElement('div'); wrap.className='mw'+(role==='usr'?' uw':'');
  const bubble=document.createElement('div');
  bubble.className='msg '+(role==='usr'?'usr':'bot'+(isEmg?' emg':''));
  bubble.innerHTML=text.replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br/>');
  const ts=document.createElement('div'); ts.className='mtime';
  ts.textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
  wrap.appendChild(bubble); wrap.appendChild(ts);
  if(appt){
    const card=document.createElement('div'); card.className='appt-card';
    card.innerHTML=`<h4>✅ Appointment Confirmed</h4>
      <div><span class="ref-code">${appt.id.substring(0,8).toUpperCase()}</span></div>
      <div class="appt-row"><b>👤 Patient:</b> ${appt.patient_name||'—'}</div>
      <div class="appt-row"><b>🏥 Dept:</b> ${appt.department}</div>
      <div class="appt-row"><b>📅 Date:</b> ${appt.appointment_date} at ${appt.appointment_time}</div>
      <div class="appt-row" style="margin-top:7px;font-size:.76rem;color:#555">Save the reference code above to cancel or look up your appointment.</div>`;
    wrap.appendChild(card);
  }
  document.getElementById('msgs').appendChild(wrap);
  document.getElementById('msgs').scrollTop=99999;
}

function showTyping(v){ document.getElementById('typ').style.display=v?'flex':'none'; }

function speak(txt){
  if(!document.getElementById('ttschk').checked||!synth) return;
  synth.cancel();
  const clean=txt.replace(/<[^>]+>/g,'').replace(/\n+/g,'. ').substring(0,300);
  const u=new SpeechSynthesisUtterance(clean);
  u.lang=srLang; u.rate=.92; u.pitch=1;
  const vs=synth.getVoices();
  const v=vs.find(v=>v.lang===srLang)||vs.find(v=>v.lang.startsWith(srLang.split('-')[0]));
  if(v) u.voice=v;
  synth.speak(u);
}

document.getElementById('tin').onkeydown=e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();} };
document.getElementById('sbtn').onclick=()=>send();

async function send(override){
  const msg=(override||document.getElementById('tin').value).trim();
  if(!msg) return;
  document.getElementById('tin').value='';
  addMsg(msg,'usr'); showTyping(true);
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg,session_id:sid,language:lang,api_key:apiKey})});
    const d=await res.json();
    sid=d.session_id; showTyping(false);
    addMsg(d.reply,'bot',d.action==='emergency',d.appointment||null);
    if(d.action==='emergency') document.getElementById('ebanner').style.display='block';
    speak(d.reply);
  }catch(err){ showTyping(false); addMsg('⚠️ Connection error. Please try again.','bot'); }
}

// Speech recognition
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let rec=null, listening=false;
const mb=document.getElementById('mbtn'), tin=document.getElementById('tin'), wv=document.getElementById('waves');
if(SR){
  rec=new SR(); rec.continuous=false; rec.interimResults=true; rec.lang=srLang;
  rec.onstart=()=>{ listening=true; mb.classList.add('rec'); mb.textContent='⏹'; wv.classList.add('on'); tin.placeholder='Listening…'; };
  rec.onresult=e=>{ const t=Array.from(e.results).map(r=>r[0].transcript).join(''); tin.value=t; if(e.results[e.results.length-1].isFinal){stopRec();send(t);} };
  rec.onerror=()=>stopRec(); rec.onend=()=>stopRec();
  mb.onclick=()=>{ if(listening)rec.stop(); else{synth&&synth.cancel();rec.lang=srLang;rec.start();} };
}else{
  mb.style.opacity='.4';
  mb.onclick=()=>alert('Voice input requires Chrome or Edge browser.');
}
function stopRec(){ listening=false; mb.classList.remove('rec'); mb.textContent='🎤'; wv.classList.remove('on'); tin.placeholder=PH[lang]; }
if(synth) synth.onvoiceschanged=()=>synth.getVoices();
</script>
</body></html>"""

# ══════════════════════════════════════════════════════════════════
#  CALL HISTORY PAGE
# ══════════════════════════════════════════════════════════════════
def build_history_html():
    rows = db("""SELECT ch.*, COUNT(m.id) as msg_count
                 FROM call_history ch
                 LEFT JOIN messages m ON ch.session_id=m.session_id
                 GROUP BY ch.session_id ORDER BY ch.started_at DESC LIMIT 300""", fetch=True)
    lang_label = {"en":"🇬🇧 English","hi":"🇮🇳 Hindi","kn":"🇮🇳 Kannada"}
    ch_icon    = {"web":"🌐","phone":"📞","twilio":"📞"}
    rows_html  = ""
    for r in rows:
        msgs = db("SELECT * FROM messages WHERE session_id=? ORDER BY timestamp", (r["session_id"],), fetch=True)
        conv = "".join(
            f"<div class='{'um' if m['role']=='user' else 'bm'}'>"
            f"<b>{'User' if m['role']=='user' else 'Bot'}:</b> {m['content'][:130]}{'…' if len(m['content'])>130 else ''}</div>"
            for m in msgs)
        mc = r.get('total_messages',0) or r.get('msg_count',0)
        rows_html += f"""
        <tr onclick="toggle('{r['session_id']}')">
          <td>{r['started_at'][:16].replace('T',' ')}</td>
          <td>{r['caller_name']}</td>
          <td>{r['caller_phone'] or '—'}</td>
          <td>{lang_label.get(r['language'],'🌐 '+r['language'])}</td>
          <td>{ch_icon.get(r['channel'],'🌐')} {r['channel'].title()}</td>
          <td><span class='cnt'>{mc}</span></td>
        </tr>
        <tr class='cdet' id='c-{r['session_id']}' style='display:none'>
          <td colspan='6'><div class='cbox'>{conv or '<i style="color:#999">No messages</i>'}</div></td>
        </tr>"""
    total_msgs = sum((r.get('total_messages',0) or r.get('msg_count',0)) for r in rows)
    return f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"/><title>Call History — City General Hospital</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f4ff;color:#202124}}
header{{background:linear-gradient(135deg,#1b3a6b,#1a73e8);color:#fff;padding:14px 22px;display:flex;align-items:center;gap:12px}}
header h1{{font-size:1.15rem;font-weight:700}}
.back{{margin-left:auto;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);color:#fff;border-radius:8px;padding:6px 13px;text-decoration:none;font-size:.78rem;font-weight:600}}
.back:hover{{background:rgba(255,255,255,.24)}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;padding:14px 18px;max-width:1000px;margin:0 auto}}
.stat{{background:#fff;border-radius:12px;padding:14px 18px;flex:1;min-width:120px;box-shadow:0 2px 8px rgba(0,0,0,.07);text-align:center;border:1px solid #e0e0e0}}
.stat .val{{font-size:1.7rem;font-weight:700;color:#1a73e8}}
.stat .lbl{{font-size:.75rem;color:#5f6368;margin-top:4px}}
.wrap{{max-width:1000px;margin:0 auto;padding:0 16px 24px}}
.search-row{{display:flex;gap:8px;margin-bottom:10px}}
#search{{flex:1;border:2px solid #dadce0;border-radius:22px;padding:8px 15px;font-size:.85rem;outline:none}}
#search:focus{{border-color:#1a73e8}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07);border:1px solid #e0e0e0}}
thead tr{{background:#1a73e8;color:#fff;font-size:.8rem}}
th{{padding:11px 13px;text-align:left;font-weight:600}}
tbody tr{{border-bottom:1px solid #f0f0f0;cursor:pointer;transition:background .15s;font-size:.83rem}}
tbody tr:hover{{background:#f0f4ff}}
td{{padding:10px 13px}}
.cnt{{background:#e8f0fe;color:#1a73e8;border-radius:12px;padding:2px 9px;font-size:.76rem;font-weight:700}}
.cdet td{{background:#f8f9ff;padding:0}}
.cbox{{padding:10px 15px;border-top:2px solid #e8f0fe;max-height:200px;overflow-y:auto}}
.um{{background:#e8f0fe;border-radius:8px;padding:5px 10px;margin:3px 0;font-size:.81rem}}
.bm{{background:#e8f5e9;border-radius:8px;padding:5px 10px;margin:3px 0;font-size:.81rem}}
.empty{{text-align:center;padding:40px;color:#999;font-size:.88rem}}
</style></head><body>
<header>
  <div style="font-size:1.5rem">📞</div>
  <h1>Call History — City General Hospital</h1>
  <div style="display:flex;gap:8px;margin-left:auto">
    <a class="back" href="/admin">📊 Admin</a>
    <a class="back" href="/">← Assistant</a>
  </div>
</header>
<div class="stats">
  <div class="stat"><div class="val">{len(rows)}</div><div class="lbl">Total Sessions</div></div>
  <div class="stat"><div class="val">{total_msgs}</div><div class="lbl">Total Messages</div></div>
  <div class="stat"><div class="val">{sum(1 for r in rows if r.get('language')=='en')}</div><div class="lbl">🇬🇧 English</div></div>
  <div class="stat"><div class="val">{sum(1 for r in rows if r.get('language')=='hi')}</div><div class="lbl">🇮🇳 Hindi</div></div>
  <div class="stat"><div class="val">{sum(1 for r in rows if r.get('language')=='kn')}</div><div class="lbl">🇮🇳 Kannada</div></div>
</div>
<div class="wrap">
  <div class="search-row">
    <input id="search" placeholder="🔍 Search by name, phone, language…" oninput="filterTable()"/>
  </div>
  <table id="htable">
    <thead><tr><th>Date &amp; Time</th><th>Patient Name</th><th>Phone</th><th>Language</th><th>Channel</th><th>Messages</th></tr></thead>
    <tbody id="tbody">
      {''.join([rows_html]) if rows else '<tr><td colspan="6" class="empty">No call history yet. Start chatting to see records here! 💬</td></tr>'}
    </tbody>
  </table>
</div>
<script>
function toggle(id){{const el=document.getElementById('c-'+id);el.style.display=el.style.display==='none'?'table-row':'none';}}
function filterTable(){{
  const q=document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('#tbody tr:not(.cdet)').forEach(tr=>{{
    const show=tr.textContent.toLowerCase().includes(q);
    tr.style.display=show?'':'none';
    const det=document.getElementById('c-'+tr.onclick?.toString()?.match(/'([^']+)'/)?.[1]);
    if(det) det.style.display='none';
  }});
}}
</script>
</body></html>"""

# ══════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════════
def build_admin_html():
    s     = get_stats()
    appts = db("SELECT * FROM appointments ORDER BY appointment_date DESC LIMIT 50", fetch=True)

    status_badge = lambda st: (
        "<span style='background:#d5f5e3;color:#1e8449;border-radius:10px;padding:2px 9px;font-size:.75rem;font-weight:700'>✅ Scheduled</span>" if st=="scheduled"
        else "<span style='background:#fadbd8;color:#c0392b;border-radius:10px;padding:2px 9px;font-size:.75rem;font-weight:700'>❌ Cancelled</span>"
    )

    appt_rows = "".join(f"""
    <tr>
      <td style='font-family:monospace;font-weight:700;color:#1a73e8'>{a['id'][:8].upper()}</td>
      <td>{a['patient_name']}</td>
      <td>{a['patient_phone']}</td>
      <td>{a['department']}</td>
      <td>{a['appointment_date']}</td>
      <td>{a['appointment_time']}</td>
      <td>{status_badge(a['status'])}</td>
    </tr>""" for a in appts)

    dept_bars = "".join(
        f"<div style='display:flex;align-items:center;gap:8px;margin:5px 0;font-size:.82rem'>"
        f"<div style='width:110px;color:#555;text-overflow:ellipsis;overflow:hidden;white-space:nowrap'>{d['department']}</div>"
        f"<div style='flex:1;background:#e8f0fe;border-radius:6px;height:18px'>"
        f"<div style='background:#1a73e8;border-radius:6px;height:18px;width:{min(100,int(d['cnt']/max(s['total'],1)*100*3))}%;min-width:4px'></div></div>"
        f"<div style='color:#1a73e8;font-weight:700;min-width:24px;text-align:right'>{d['cnt']}</div></div>"
        for d in (s['depts'] or [])
    )

    return f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"/><title>Admin Dashboard — City General Hospital</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f4ff;color:#202124}}
header{{background:linear-gradient(135deg,#1b3a6b,#1a73e8);color:#fff;padding:14px 22px;display:flex;align-items:center;gap:12px}}
header h1{{font-size:1.15rem;font-weight:700}}
.back{{margin-left:auto;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);color:#fff;border-radius:8px;padding:6px 13px;text-decoration:none;font-size:.78rem;font-weight:600}}
.back:hover{{background:rgba(255,255,255,.24)}}
.wrap{{max-width:1100px;margin:0 auto;padding:16px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}}
.kpi{{background:#fff;border-radius:12px;padding:16px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.07);border:1px solid #e0e0e0}}
.kpi .v{{font-size:2rem;font-weight:700}}.kpi .l{{font-size:.74rem;color:#5f6368;margin-top:4px}}
.kpi.blue .v{{color:#1a73e8}}.kpi.green .v{{color:#0f9d58}}.kpi.red .v{{color:#d93025}}.kpi.orange .v{{color:#f9ab00}}
.row2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}}
@media(max-width:640px){{.row2{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border-radius:12px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.07);border:1px solid #e0e0e0}}
.panel h3{{font-size:.92rem;font-weight:700;color:#1b3a6b;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e8f0fe}}
.lang-item{{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:.83rem}}
.lang-bar{{flex:1;background:#f0f0f0;border-radius:6px;height:16px;overflow:hidden}}
.lang-fill{{height:16px;border-radius:6px}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
thead tr{{background:#1a73e8;color:#fff}} th{{padding:9px 12px;text-align:left;font-weight:600}}
tbody tr{{border-bottom:1px solid #f0f0f0;transition:background .15s}} tbody tr:hover{{background:#f8f9ff}}
td{{padding:9px 12px}}
</style></head><body>
<header>
  <div style="font-size:1.5rem">📊</div>
  <h1>Admin Dashboard — City General Hospital</h1>
  <div style="display:flex;gap:8px;margin-left:auto">
    <a class="back" href="/history">📞 History</a>
    <a class="back" href="/">← Assistant</a>
  </div>
</header>
<div class="wrap">
  <div class="kpi-grid">
    <div class="kpi blue"><div class="v">{s['total']}</div><div class="l">Total Appointments</div></div>
    <div class="kpi green"><div class="v">{s['scheduled']}</div><div class="l">Active / Scheduled</div></div>
    <div class="kpi red"><div class="v">{s['cancelled']}</div><div class="l">Cancelled</div></div>
    <div class="kpi orange"><div class="v">{s['sessions']}</div><div class="l">Chat Sessions</div></div>
    <div class="kpi blue"><div class="v">{s['messages']}</div><div class="l">Total Messages</div></div>
  </div>
  <div class="row2">
    <div class="panel">
      <h3>🌐 Sessions by Language</h3>
      {''.join([
        f"<div class='lang-item'><span style='width:85px'>{{'en':'🇬🇧 English','hi':'🇮🇳 Hindi','kn':'🇮🇳 Kannada'}}[k]</span>"
        f"<div class='lang-bar'><div class='lang-fill' style='width:{int(v/max(s['sessions'],1)*100)}%;background:{c}'></div></div>"
        f"<span style='font-weight:700;min-width:24px;text-align:right;color:{c}'>{v}</span></div>"
        for k,v,c in [('en',s['en'],'#1a73e8'),('hi',s['hi'],'#f9ab00'),('kn',s['kn'],'#0f9d58')]
      ])}
    </div>
    <div class="panel">
      <h3>🏥 Appointments by Department</h3>
      {dept_bars or '<p style="color:#999;font-size:.84rem">No appointments yet.</p>'}
    </div>
  </div>
  <div class="panel">
    <h3>📅 Recent Appointments</h3>
    <table>
      <thead><tr><th>Ref</th><th>Patient</th><th>Phone</th><th>Department</th><th>Date</th><th>Time</th><th>Status</th></tr></thead>
      <tbody>
        {appt_rows or '<tr><td colspan="7" style="text-align:center;padding:24px;color:#999">No appointments yet.</td></tr>'}
      </tbody>
    </table>
  </div>
</div>
</body></html>"""

# ══════════════════════════════════════════════════════════════════
#  HTTP SERVER
# ══════════════════════════════════════════════════════════════════
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")

    def _json(self, code, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json"); self._cors(); self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8"); self._cors(); self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status":"ok","version":"2.0"})
        elif self.path == "/history":
            self._html(build_history_html())
        elif self.path == "/admin":
            self._html(build_admin_html())
        elif self.path == "/api/appointments":
            self._json(200, db("SELECT * FROM appointments ORDER BY appointment_date DESC", fetch=True))
        elif self.path == "/api/stats":
            self._json(200, get_stats())
        else:
            self._html(HTML_APP)

    def do_POST(self):
        length     = int(self.headers.get("Content-Length", 0))
        body       = json.loads(self.rfile.read(length) or b"{}")
        session_id = body.get("session_id") or str(uuid.uuid4())

        if self.path == "/api/chat":
            msg      = body.get("message","").strip()
            language = body.get("language","en")
            api_key  = body.get("api_key","")

            ensure_session(session_id, language)
            ctx = get_ctx(session_id)
            ctx["lang"] = language
            log_message(session_id, "user", msg, language)

            # Emergency check
            if is_emg(msg):
                reply = t("emergency", language)
                log_message(session_id, "bot", reply, language)
                self._json(200, {"reply":reply,"action":"emergency","session_id":session_id,"appointment":None})
                return

            # OpenAI GPT-4o-mini (optional)
            if api_key:
                try:
                    import urllib.request as ur
                    lang_name = {"hi":"Hindi","kn":"Kannada"}.get(language,"English")
                    sys_p = f"""You are a warm, professional hospital voice assistant for City General Hospital.
Always respond in {lang_name} only.
Help with: appointment booking/checking/cancellation, hospital FAQs, emergency guidance.
Departments: Cardiology, Neurology, Orthopedics, Pediatrics, Oncology, Dermatology, Surgery, Internal Medicine, OB/GYN, ENT.
Keep responses concise (2–4 sentences). Be empathetic and clear."""
                    payload = json.dumps({"model":"gpt-4o-mini","messages":[{"role":"system","content":sys_p},{"role":"user","content":msg}],"temperature":0.4,"max_tokens":300}).encode()
                    req = ur.Request("https://api.openai.com/v1/chat/completions", data=payload,
                                     headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}, method="POST")
                    with ur.urlopen(req, timeout=15) as resp:
                        reply = json.loads(resp.read())["choices"][0]["message"]["content"].strip()
                    log_message(session_id, "bot", reply, language)
                    self._json(200, {"reply":reply,"action":None,"session_id":session_id,"appointment":None})
                    return
                except:
                    pass  # fallback to local engine

            # Built-in conversation engine
            result = local_reply(msg, session_id)
            appt   = None
            if isinstance(result, dict):
                reply = result.get("text","")
                appt  = result.get("appt")
            else:
                reply = result
            log_message(session_id, "bot", reply, language)
            self._json(200, {"reply":reply,"action":None,"session_id":session_id,"appointment":appt})

        elif self.path == "/twilio/voice":
            # Twilio IVR entry point
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" action="/twilio/process" method="POST" speechTimeout="auto" language="en-US">
    <Say voice="Polly.Joanna">Welcome to City General Hospital. I can help you book appointments or answer questions. Please speak after the tone.</Say>
  </Gather>
</Response>"""
            body = twiml.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/xml"); self._cors(); self.end_headers()
            self.wfile.write(body)

        elif self.path == "/twilio/process":
            speech = body.get("SpeechResult","") or body.get("Body","")
            caller = body.get("From","")
            if not session_id or session_id == body.get("session_id",""):
                session_id = body.get("CallSid") or str(uuid.uuid4())
            ensure_session(session_id, "en", "twilio")
            if caller: update_caller_info(session_id, phone=caller)
            ctx = get_ctx(session_id); ctx["lang"] = "en"
            if speech: log_message(session_id, "user", speech, "en")
            if is_emg(speech):
                reply = "This is a medical emergency. Please call 911 immediately or go to our Emergency Room on the ground floor. Do not drive yourself."
            else:
                result = local_reply(speech, session_id)
                reply  = result.get("text","") if isinstance(result,dict) else result
            log_message(session_id, "bot", reply, "en")
            clean_reply = re.sub(r'[^\w\s\.,!?-]','',reply)[:400]
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" action="/twilio/process" method="POST" speechTimeout="auto" language="en-US">
    <Say voice="Polly.Joanna">{clean_reply} Is there anything else I can help you with?</Say>
  </Gather>
  <Say voice="Polly.Joanna">Thank you for calling City General Hospital. Goodbye.</Say>
</Response>"""
            body_bytes = twiml.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/xml"); self._cors(); self.end_headers()
            self.wfile.write(body_bytes)

# ══════════════════════════════════════════════════════════════════
#  LAUNCH
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    is_local = not (os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("FLY_APP_NAME"))
    print(f"\n{'═'*56}")
    print(f"  🏥  City General Hospital — Voice Agent v2.0")
    print(f"{'═'*56}")
    print(f"  ✅  Port      : {PORT}")
    print(f"  🌐  Languages : English · Hindi · Kannada")
    print(f"  🏠  Home      : http://localhost:{PORT}")
    print(f"  📊  Admin     : http://localhost:{PORT}/admin")
    print(f"  📞  History   : http://localhost:{PORT}/history")
    print(f"  🔄  Stop      : Ctrl+C")
    print(f"{'═'*56}\n")
    if is_local:
        threading.Thread(
            target=lambda: __import__('time').sleep(1.2) or webbrowser.open(f"http://localhost:{PORT}"),
            daemon=True).start()
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped.")
