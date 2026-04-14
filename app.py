"""
Hospital Voice Agent - Run with: python app.py
Then open: http://localhost:8080
No pip installs needed - uses only Python built-ins.
"""
import http.server, socketserver, json, sqlite3, uuid, os, sys, webbrowser, threading

PORT = 8080
DB   = os.path.join(os.getenv("TMPDIR", "/tmp"), "hospital_agent.db")

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    c = sqlite3.connect(DB); c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id TEXT PRIMARY KEY, patient_name TEXT, patient_phone TEXT,
            patient_email TEXT, department TEXT, doctor_name TEXT,
            appointment_date TEXT, appointment_time TEXT,
            reason TEXT, status TEXT DEFAULT 'scheduled',
            created_at TEXT DEFAULT (datetime('now')))""")
    c.commit(); c.close()

def db_exec(sql, params=(), fetch=False):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    cur = c.execute(sql, params); c.commit()
    rows = [dict(r) for r in cur.fetchall()] if fetch else []
    c.close(); return rows

def book_appt(d):
    aid = str(uuid.uuid4())
    db_exec("INSERT INTO appointments(id,patient_name,patient_phone,patient_email,department,doctor_name,appointment_date,appointment_time,reason) VALUES(?,?,?,?,?,?,?,?,?)",
            (aid,d.get("patient_name",""),d.get("patient_phone",""),d.get("patient_email"),d.get("department",""),d.get("doctor_name"),d.get("appointment_date",""),d.get("appointment_time",""),d.get("reason")))
    return db_exec("SELECT * FROM appointments WHERE id=?", (aid,), True)[0]

def get_by_phone(phone):
    return db_exec("SELECT * FROM appointments WHERE patient_phone=? AND status='scheduled' ORDER BY appointment_date,appointment_time",(phone,),True)

def cancel_appt(ref):
    rows = db_exec("SELECT * FROM appointments WHERE UPPER(id) LIKE ? AND status='scheduled'",(ref.upper()+"%",),True)
    if rows:
        db_exec("UPDATE appointments SET status='cancelled' WHERE id=?",(rows[0]["id"],))
        rows[0]["status"]="cancelled"; return rows[0]
    return None

# ── The full HTML page (inline) ───────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>City General Hospital – Voice Assistant</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--pri:#1a73e8;--prid:#1557b0;--ok:#0f9d58;--err:#d93025;--bg:#eef2ff;--card:#fff;--txt:#202124;--mut:#5f6368;--bdr:#dadce0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--txt);min-height:100vh;display:flex;flex-direction:column}
header{background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;padding:18px 28px;display:flex;align-items:center;gap:14px;box-shadow:0 2px 14px rgba(0,0,0,.22)}
.hi{font-size:2rem;animation:pulse 2s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.65}}
.ht h1{font-size:1.4rem;font-weight:700}.ht p{font-size:.82rem;opacity:.85;margin-top:2px}
.hb{margin-left:auto;background:rgba(255,255,255,.18);border-radius:20px;padding:6px 14px;font-size:.76rem;font-weight:700}
#apibar{background:#fffde7;border-bottom:2px solid #f9ab00;padding:10px 22px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:.84rem}
#apibar strong{color:#e65100}#apibar input{flex:1;min-width:200px;border:1.5px solid #f9ab00;border-radius:8px;padding:6px 12px;font-size:.84rem;font-family:monospace;outline:none}
#apibar input:focus{border-color:var(--pri)}#savebtn{background:var(--pri);color:#fff;border:none;border-radius:8px;padding:7px 16px;cursor:pointer;font-weight:600;font-size:.82rem;white-space:nowrap}
#savebtn:hover{background:var(--prid)}.anote{color:#795548;font-size:.77rem}
main{flex:1;max-width:820px;width:100%;margin:0 auto;padding:20px 14px;display:flex;flex-direction:column;gap:16px}
#ebanner{display:none;background:var(--err);color:#fff;padding:12px 18px;border-radius:12px;font-weight:700;text-align:center}
#ebanner a{color:#fff}
.qgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media(min-width:560px){.qgrid{grid-template-columns:repeat(4,1fr)}}
.qb{background:var(--card);border:2px solid var(--bdr);border-radius:12px;padding:13px 8px;cursor:pointer;text-align:center;transition:all .18s;font-size:.82rem;font-weight:500}
.qb:hover{border-color:var(--pri);background:#e8f0fe;transform:translateY(-2px);box-shadow:0 4px 12px rgba(26,115,232,.15)}
.qb .qi{font-size:1.45rem;display:block;margin-bottom:5px}
.cc{background:var(--card);border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.09);display:flex;flex-direction:column;overflow:hidden}
.ch{padding:12px 18px;background:#f8f9fa;border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:10px;font-size:.87rem;font-weight:600;color:var(--mut)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px rgba(15,157,88,.2)}
.ttswrap{margin-left:auto;display:flex;align-items:center;gap:7px;font-size:.79rem;cursor:pointer}
.tog{position:relative;width:36px;height:20px}.tog input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#ccc;border-radius:20px;transition:.3s;cursor:pointer}
.sl::before{content:'';position:absolute;height:14px;width:14px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.3s}
input:checked+.sl{background:var(--pri)}input:checked+.sl::before{transform:translateX(16px)}
#msgs{height:370px;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:12px;scroll-behavior:smooth}
#msgs::-webkit-scrollbar{width:4px}#msgs::-webkit-scrollbar-thumb{background:#ccc;border-radius:10px}
.mw{display:flex;flex-direction:column}.mw.uw{align-items:flex-end}
.msg{max-width:82%;padding:11px 15px;border-radius:18px;line-height:1.55;font-size:.92rem;animation:fi .28s ease;white-space:pre-wrap}
@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.msg.bot{background:#e8f0fe;border-bottom-left-radius:4px;align-self:flex-start}
.msg.bot.emg{background:#fce8e6;border:2px solid var(--err)}
.msg.usr{background:var(--pri);color:#fff;border-bottom-right-radius:4px;align-self:flex-end}
.mt{font-size:.7rem;opacity:.5;margin-top:3px;padding:0 4px}
.typ{display:none;align-items:center;gap:5px;padding:10px 15px;background:#e8f0fe;border-radius:18px;border-bottom-left-radius:4px;width:fit-content}
.typ span{width:7px;height:7px;border-radius:50%;background:var(--pri);animation:bo 1.2s infinite}
.typ span:nth-child(2){animation-delay:.2s}.typ span:nth-child(3){animation-delay:.4s}
@keyframes bo{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-7px)}}
.ia{padding:14px 18px;border-top:1px solid var(--bdr);display:flex;gap:8px;align-items:center;background:#fafafa}
#tin{flex:1;border:2px solid var(--bdr);border-radius:24px;padding:9px 16px;font-size:.93rem;outline:none;transition:border-color .2s;font-family:inherit;background:#fff}
#tin:focus{border-color:var(--pri)}#tin::placeholder{color:#aaa}
.btn{border:none;border-radius:50%;width:44px;height:44px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.05rem;transition:all .2s;flex-shrink:0}
#sbtn{background:var(--pri);color:#fff}#sbtn:hover{background:var(--prid);transform:scale(1.05)}
#mbtn{background:#f1f3f4}#mbtn:hover{background:#e8f0fe;color:var(--pri)}
#mbtn.on{background:var(--err);color:#fff;animation:mp 1s infinite}
@keyframes mp{0%,100%{box-shadow:0 0 0 0 rgba(217,48,37,.4)}50%{box-shadow:0 0 0 10px rgba(217,48,37,0)}}
.vw{display:none;align-items:center;gap:3px;height:28px}.vw.on{display:flex}
.vb{width:4px;border-radius:2px;background:var(--err);animation:wv .8s ease-in-out infinite}
.vb:nth-child(1){height:8px;animation-delay:0s}.vb:nth-child(2){height:16px;animation-delay:.1s}
.vb:nth-child(3){height:22px;animation-delay:.2s}.vb:nth-child(4){height:16px;animation-delay:.3s}
.vb:nth-child(5){height:8px;animation-delay:.4s}@keyframes wv{0%,100%{transform:scaleY(.4)}50%{transform:scaleY(1)}}
.acard{background:linear-gradient(135deg,#e6f4ea,#d2e9d3);border:1px solid #a8d5b5;border-radius:12px;padding:13px 16px;margin-top:7px;font-size:.86rem}
.acard h4{color:var(--ok);margin-bottom:7px}.acard .ref{font-size:1.1rem;font-weight:700;font-family:monospace;letter-spacing:2px;color:var(--ok)}
.cstrip{display:flex;gap:10px;flex-wrap:wrap;justify-content:center}
.chip{text-decoration:none;background:var(--card);border:2px solid var(--bdr);border-radius:24px;padding:9px 16px;font-size:.81rem;font-weight:500;color:var(--txt);transition:all .18s}
.chip:hover{border-color:var(--pri);background:#e8f0fe}.chip.red{border-color:#fcc;color:var(--err)}.chip.red:hover{background:#fce8e6}
footer{text-align:center;padding:13px;font-size:.74rem;color:var(--mut);border-top:1px solid var(--bdr)}
</style>
</head>
<body>
<header>
  <div class="hi">🏥</div>
  <div class="ht"><h1>City General Hospital</h1><p>Virtual Voice Assistant — 24 / 7</p></div>
  <div class="hb">🟢 ONLINE</div>
</header>
<div id="apibar">
  <strong>🔑 OpenAI Key (optional):</strong>
  <input id="akey" type="password" placeholder="sk-...  Paste your key for full AI mode (works without it too)"/>
  <button id="savebtn">Save Key</button>
  <span class="anote" id="anote">💡 Smart built-in replies active — no key needed</span>
</div>
<main>
  <div id="ebanner">🚨 EMERGENCY — Call <a href="tel:911">911</a> immediately | ER: <a href="tel:18005550911">1-800-555-0911</a></div>
  <div class="qgrid">
    <button class="qb" onclick="quick('I want to book a new appointment')"><span class="qi">📅</span>Book Appointment</button>
    <button class="qb" onclick="quick('Check my existing appointments')"><span class="qi">🔍</span>Check Appointments</button>
    <button class="qb" onclick="quick('Cancel my appointment')"><span class="qi">❌</span>Cancel Appointment</button>
    <button class="qb" onclick="quick('Hospital hours and location')"><span class="qi">ℹ️</span>Hospital Info</button>
  </div>
  <div class="cc">
    <div class="ch">
      <div class="dot"></div>Hospital AI Assistant
      <label class="ttswrap">🔊 Speak replies
        <label class="tog"><input type="checkbox" id="ttschk" checked/><span class="sl"></span></label>
      </label>
    </div>
    <div id="msgs"></div>
    <div style="padding:0 18px 4px"><div class="typ" id="typ"><span></span><span></span><span></span></div></div>
    <div class="ia">
      <div class="vw" id="vw"><div class="vb"></div><div class="vb"></div><div class="vb"></div><div class="vb"></div><div class="vb"></div></div>
      <input id="tin" type="text" placeholder="Type here or tap 🎤 to speak…" autocomplete="off"/>
      <button class="btn" id="mbtn" title="Click to speak">🎤</button>
      <button class="btn" id="sbtn">➤</button>
    </div>
  </div>
  <div class="cstrip">
    <a class="chip" href="tel:18005550100">📞 Main: 1-800-555-0100</a>
    <a class="chip" href="tel:18005550200">📅 Appts: 1-800-555-0200</a>
    <a class="chip red" href="tel:18005550911">🚨 ER: 1-800-555-0911</a>
  </div>
</main>
<footer>City General Hospital · 123 Health Avenue, Medical District · AI Voice Assistant</footer>
<script>
// ── DATA ────────────────────────────────────────────────────────────────────
const H={name:"City General Hospital",addr:"123 Health Avenue, Medical District",phone:"1-800-555-0100",er:"1-800-555-0911",appt:"1-800-555-0200",
depts:["Cardiology","Neurology","Orthopedics","Pediatrics","Oncology","Emergency Medicine","Radiology","General Surgery","Obstetrics & Gynecology","Psychiatry","Dermatology","Ophthalmology","ENT","Internal Medicine"],
docs:[{n:"Dr. Sarah Johnson",d:"Cardiology",days:"Mon,Wed,Fri"},{n:"Dr. Michael Chen",d:"Neurology",days:"Tue,Thu"},{n:"Dr. Emily Rodriguez",d:"Pediatrics",days:"Mon-Fri"},{n:"Dr. James Patel",d:"Orthopedics",days:"Mon,Wed,Fri"},{n:"Dr. Lisa Kim",d:"Dermatology",days:"Tue,Thu,Fri"},{n:"Dr. Robert Williams",d:"Internal Medicine",days:"Mon-Fri"},{n:"Dr. Amanda Foster",d:"OB/GYN",days:"Mon,Wed,Thu"},{n:"Dr. David Nguyen",d:"General Surgery",days:"Tue,Thu,Fri"}],
slots:["9:00","9:30","10:00","10:30","11:00","11:30","14:00","14:30","15:00","15:30","16:00"]};
const FAQS=[
  {k:"visiting hours visit",a:"Visiting hours: daily 9:00 AM – 8:00 PM. ICU: 11 AM–12 PM and 5–6 PM only."},
  {k:"location address where find",a:"We are at 123 Health Avenue, Medical District, near Central Metro Station. Free parking available."},
  {k:"emergency contact number phone",a:"Emergency line (24/7): 1-800-555-0911. For life-threatening emergencies call 911 immediately."},
  {k:"insurance accept",a:"We accept Medicare, Medicaid, BlueCross BlueShield, Aetna, Cigna, United Health. Bring your card."},
  {k:"parking car",a:"Free parking in Lots A, B, C. Valet at Main Entrance for $10."},
  {k:"bring documents appointment",a:"Bring: photo ID, insurance card, medication list, referral letter (if any), and previous medical records."},
  {k:"departments available specialties",a:`Our 14 departments: ${["Cardiology","Neurology","Orthopedics","Pediatrics","Oncology","Radiology","General Surgery","OB/GYN","Psychiatry","Dermatology","Ophthalmology","ENT","Internal Medicine","Emergency Medicine"].join(", ")}.`},
  {k:"doctors physicians",a:"Our doctors: Dr. Sarah Johnson (Cardiology), Dr. Michael Chen (Neurology), Dr. Emily Rodriguez (Pediatrics), Dr. James Patel (Orthopedics), Dr. Robert Williams (Internal Medicine) and more."},
  {k:"hours open timing",a:"Outpatient: Mon–Fri 8AM–6PM. Emergency: 24/7. Pharmacy: Mon–Sat 8AM–9PM. Visiting: daily 9AM–8PM."},
  {k:"pharmacy medicine",a:"Pharmacy on ground floor: Mon–Sat 8:00 AM – 9:00 PM."},
  {k:"records medical history",a:"Request records at Medical Records office (1st floor) or call 1-800-555-0100. Ready in 5–7 business days."},
  {k:"heart attack symptoms",a:"Heart attack signs: chest pain/pressure, arm or jaw pain, shortness of breath, sweating, nausea. CALL 911 IMMEDIATELY."},
  {k:"stroke",a:"Remember FAST: Face drooping, Arm weakness, Speech difficulty, Time to call 911. Every minute counts!"},
  {k:"cardiology heart",a:"Cardiology: 3rd Floor, Wing B. Extension 3001."},
  {k:"pediatrics children kids",a:"Pediatrics: 2nd Floor, Wing A. Open Mon–Fri 8AM–6PM. Emergency pediatrics 24/7."},
  {k:"wait time er emergency room",a:"Life-threatening: seen immediately. Non-urgent: 1–3 hours. Check live wait times on our website."},
];
function findFaq(msg){
  const ml=msg.toLowerCase(); let best=null,bs=0;
  for(const f of FAQS){const s=f.k.split(" ").filter(w=>ml.includes(w)).length;if(s>bs){bs=s;best=f.a;}}
  return bs>=1?best:null;
}
const EW=["emergency","heart attack","stroke","can't breathe","cannot breathe","chest pain","unconscious","bleeding","severe pain","dying","overdose","choking","not breathing","seizure","fainted","collapsed","poisoning","anaphylaxis"];
const isEmg=m=>EW.some(w=>m.toLowerCase().includes(w));

// ── IN-MEMORY APPOINTMENTS ───────────────────────────────────────────────────
let APTS=[];
const mkId=()=>Math.random().toString(36).substr(2,8).toUpperCase();

// ── CONVERSATION STATE ───────────────────────────────────────────────────────
let apiKey="", hist=[], ctx={stage:null,data:{}};

function localReply(msg){
  const ml=msg.toLowerCase();
  // Booking multi-step
  if(ctx.stage==="name"){ctx.data.patient_name=msg.trim();ctx.stage="phone";return `Nice to meet you, ${ctx.data.patient_name}! What's your phone number?`;}
  if(ctx.stage==="phone"){
    const ph=msg.replace(/[\s\-\(\)]/g,"");
    if(ph.replace(/\D/g,"").length<7) return "Please enter a valid phone number.";
    ctx.data.patient_phone=msg.trim();ctx.stage="dept";
    return `Got it! Which department?\n\n${H.depts.join(" · ")}`;
  }
  if(ctx.stage==="dept"){
    const match=H.depts.find(d=>d.toLowerCase().includes(ml.split(" ")[0]))||msg.trim();
    ctx.data.department=match;ctx.stage="date";
    const t=new Date();t.setDate(t.getDate()+1);
    return `Which date? (e.g. ${t.toISOString().slice(0,10)})\nAvailable times: ${H.slots.join(", ")}`;
  }
  if(ctx.stage==="date"){
    const dm=msg.match(/\d{4}[-\/]\d{1,2}[-\/]\d{1,2}/);
    if(!dm) return `Please use format YYYY-MM-DD (e.g. ${new Date(Date.now()+864e5).toISOString().slice(0,10)})`;
    ctx.data.appointment_date=dm[0].replace(/\//g,"-");ctx.stage="time";
    return `What time? Available: ${H.slots.join(", ")}`;
  }
  if(ctx.stage==="time"){
    const tm=msg.match(/\d{1,2}:\d{2}/)||msg.match(/\d{1,2}\s*(am|pm)/i);
    if(!tm) return `Please pick a time from: ${H.slots.join(", ")}`;
    ctx.data.appointment_time=tm[0];ctx.stage="confirm";
    const d=ctx.data;
    return `Please confirm:\n\n👤 ${d.patient_name}\n📱 ${d.patient_phone}\n🏥 ${d.department}\n📅 ${d.appointment_date} at ${d.appointment_time}\n\nType YES to confirm or NO to cancel.`;
  }
  if(ctx.stage==="confirm"){
    if(ml.includes("yes")||ml.includes("confirm")||ml==="y"){
      const a={...ctx.data,id:mkId(),status:"scheduled",created:new Date().toISOString()};
      APTS.push(a);ctx.stage=null;ctx.data={};
      return {text:`✅ Appointment Confirmed!\n\n📋 Booking Ref: **${a.id}**\n📅 ${a.appointment_date} at ${a.appointment_time}\n🏥 ${a.department}\n\nSave your reference number. Anything else?`,appt:a};
    } else {ctx.stage=null;ctx.data={};return "Appointment cancelled. How else can I help?";}
  }
  if(ctx.stage==="checkphone"){
    const found=APTS.filter(a=>a.patient_phone===msg.trim()&&a.status==="scheduled");
    ctx.stage=null;
    if(!found.length) return `No appointments found for ${msg.trim()}. Would you like to book one?`;
    return `Found ${found.length} appointment(s):\n\n${found.map(a=>`📅 ${a.appointment_date} ${a.appointment_time} — ${a.department}\n   Ref: ${a.id}`).join("\n\n")}`;
  }
  if(ctx.stage==="cancelref"){
    const ref=msg.trim().toUpperCase();
    const a=APTS.find(a=>a.id.startsWith(ref)&&a.status==="scheduled");
    ctx.stage=null;
    if(a){a.status="cancelled";return `✅ Appointment ${a.id} cancelled successfully.\n\nAnything else I can help with?`;}
    return `No active appointment found with ref "${ref}". Please double-check your booking reference.`;
  }
  // Intent detection
  if((ml.includes("book")||ml.includes("schedule")||ml.includes("new appointment"))&&!ml.includes("check")&&!ml.includes("cancel")){
    ctx.stage="name";ctx.data={};return "I'll help you book! What's your full name?";
  }
  if(ml.includes("check")||ml.includes("my appointment")||ml.includes("upcoming")||ml.includes("existing")){
    ctx.stage="checkphone";return "Please share your phone number to look up your appointments.";
  }
  if(ml.includes("cancel")){ctx.stage="cancelref";return "Please provide your 8-character booking reference number.";}
  // FAQ
  const faq=findFaq(msg);
  if(faq) return faq+"\n\nIs there anything else I can help you with?";
  // Default
  return `I can help you:\n\n📅 Book, check, or cancel appointments\nℹ️ Answer questions about ${H.name}\n🚨 Emergency guidance\n\nWhat would you like?`;
}

async function aiReply(msg){
  hist.push({role:"user",content:msg});
  if(hist.length>16) hist=hist.slice(-16);
  const sys=`You are a warm, professional voice assistant for ${H.name}. Help with appointments, FAQs, and emergencies. Departments: ${H.depts.join(", ")}. Doctors: ${H.docs.map(d=>d.n+" ("+d.d+")").join("; ")}. Slots: ${H.slots.join(", ")}. Today: ${new Date().toDateString()}. For bookings collect name, phone, department, date(YYYY-MM-DD), time(HH:MM). When confirmed reply normally AND add: ACTION:BOOK DATA:{"patient_name":"...","patient_phone":"...","department":"...","appointment_date":"...","appointment_time":"..."}. Keep replies short (2-4 sentences).`;
  const r=await fetch("https://api.openai.com/v1/chat/completions",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+apiKey},body:JSON.stringify({model:"gpt-4o-mini",messages:[{role:"system",content:sys},...hist],temperature:0.4,max_tokens:350})});
  if(!r.ok){const e=await r.json();throw new Error(e.error?.message||"API error");}
  const data=await r.json();
  const raw=data.choices[0].message.content.trim();
  hist.push({role:"assistant",content:raw});
  // Parse action
  const am=raw.match(/ACTION:BOOK/i),dm=raw.match(/DATA:\s*(\{[\s\S]*?\})/i);
  let appt=null;
  if(am&&dm){try{const d=JSON.parse(dm[1]);const a={...d,id:mkId(),status:"scheduled",created:new Date().toISOString()};APTS.push(a);appt=a;}catch(e){}}
  const text=raw.replace(/ACTION:BOOK[\s\S]*$/i,"").trim();
  return {text,appt};
}

async function process(msg){
  if(isEmg(msg)){document.getElementById("ebanner").style.display="block";return {text:`⚠️ MEDICAL EMERGENCY DETECTED!\n\nCall 911 immediately or go to our ER (Ground Floor).\nHospital Emergency: ${H.er}\n\nDo NOT drive yourself. Call 911 now.`,emg:true};}
  if(apiKey){try{return await aiReply(msg);}catch(e){return {text:"⚠️ AI error: "+e.message+". Using built-in mode instead.\n\n"+localReplyText(msg)};}}
  const r=localReply(msg);
  if(typeof r==="object") return r;
  return {text:r};
}
function localReplyText(msg){const r=localReply(msg);return typeof r==="object"?r.text:r;}

// ── UI ───────────────────────────────────────────────────────────────────────
const msgs=document.getElementById("msgs"),tin=document.getElementById("tin"),typ=document.getElementById("typ"),vw=document.getElementById("vw"),ttschk=document.getElementById("ttschk"),sy=window.speechSynthesis;

window.addEventListener("load",()=>{
  const h=new Date().getHours();
  addMsg(`${h<12?"Good morning":h<17?"Good afternoon":"Good evening"}! 👋 Welcome to ${H.name}.\n\nI can help you:\n• 📅 Book, check, or cancel appointments\n• ℹ️ Answer questions about our hospital\n• 🚨 Emergency guidance\n\nHow can I help you today?`,"bot");
});

document.getElementById("savebtn").onclick=()=>{
  apiKey=document.getElementById("akey").value.trim();
  if(apiKey){document.getElementById("apibar").style.cssText="background:#e8f5e9;border-bottom:2px solid #0f9d58;padding:10px 22px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:.84rem";document.getElementById("anote").textContent="✅ OpenAI key saved — Full AI mode active!";document.getElementById("anote").style.color="#0f9d58";addMsg("✅ OpenAI key saved! Full AI mode is now active.","bot");}
};
document.getElementById("akey").onkeydown=e=>{if(e.key==="Enter")document.getElementById("savebtn").click();};

function addMsg(text,role,emg=false,appt=null){
  const w=document.createElement("div");w.className="mw"+(role==="usr"?" uw":"");
  const b=document.createElement("div");b.className="msg "+(role==="usr"?"usr":"bot"+(emg?" emg":""));
  b.innerHTML=text.replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>").replace(/\n/g,"<br/>");
  const t=document.createElement("div");t.className="mt";t.textContent=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
  w.appendChild(b);w.appendChild(t);
  if(appt){const c=document.createElement("div");c.className="acard";c.innerHTML=`<h4>✅ Appointment Confirmed!</h4><div>Booking Ref: <span class="ref">${appt.id}</span></div><div><b>Patient:</b> ${appt.patient_name||"—"}</div><div><b>Department:</b> ${appt.department}</div><div><b>Date:</b> ${appt.appointment_date} at ${appt.appointment_time}</div><div style="margin-top:6px;font-size:.78rem;color:#555">📌 Save your booking reference number</div>`;w.appendChild(c);}
  msgs.appendChild(w);msgs.scrollTop=msgs.scrollHeight;
}
function showTyp(v){typ.style.display=v?"flex":"none";if(v)msgs.scrollTop=msgs.scrollHeight;}
function speak(t){if(!ttschk.checked||!sy)return;sy.cancel();const u=new SpeechSynthesisUtterance(t.replace(/<[^>]+>/g,"").replace(/[^\x00-\x7F]/g,"").replace(/\n/g,". ").substring(0,280));u.rate=.95;u.pitch=1;const vs=sy.getVoices();const v=vs.find(v=>v.name.includes("Samantha")||v.name.includes("Google US English"));if(v)u.voice=v;sy.speak(u);}
function quick(t){tin.value=t;send();}
tin.onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}};
document.getElementById("sbtn").onclick=send;

async function send(ov){
  const m=(ov||tin.value).trim();if(!m)return;tin.value="";
  addMsg(m,"usr");showTyp(true);
  try{
    const r=await process(m);showTyp(false);
    addMsg(r.text||"","bot",r.emg||false,r.appt||null);
    if(r.emg)document.getElementById("ebanner").style.display="block";
    speak(r.text||"");
  }catch(e){showTyp(false);addMsg("⚠️ Error. Please try again or call 1-800-555-0100.","bot");}
}

// ── MICROPHONE ───────────────────────────────────────────────────────────────
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let rec=null,lis=false;
const mbtn=document.getElementById("mbtn");
if(SR){
  rec=new SR();rec.continuous=false;rec.interimResults=true;rec.lang="en-US";
  rec.onstart=()=>{lis=true;mbtn.classList.add("on");mbtn.textContent="⏹";vw.classList.add("on");tin.placeholder="Listening…";};
  rec.onresult=e=>{const t=Array.from(e.results).map(r=>r[0].transcript).join("");tin.value=t;if(e.results[e.results.length-1].isFinal){stopL();send(t);}};
  rec.onerror=()=>stopL();rec.onend=()=>stopL();
  mbtn.onclick=()=>{if(lis)rec.stop();else{sy&&sy.cancel();rec.start();}};
}else{
  mbtn.title="Microphone needs Chrome/Edge";mbtn.style.opacity=".4";mbtn.style.cursor="not-allowed";
  mbtn.onclick=()=>alert("Microphone works in Chrome or Edge only.");
}
function stopL(){lis=false;mbtn.classList.remove("on");mbtn.textContent="🎤";vw.classList.remove("on");tin.placeholder="Type here or tap 🎤 to speak…";}
if(sy)sy.onvoiceschanged=()=>sy.getVoices();
</script>
</body>
</html>"""

# ── HTTP Server ───────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence request logs

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200,{"status":"ok"})
        elif self.path == "/api/appointments":
            self._json(200, db_exec("SELECT * FROM appointments ORDER BY appointment_date",fetch=True))
        else:
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(HTML.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/api/voice/chat":
            msg  = body.get("message","").strip()
            if not msg:
                self._json(400,{"error":"message required"}); return

            # Emergency check
            ew=["emergency","heart attack","stroke","can't breathe","chest pain","unconscious",
                "bleeding","severe pain","dying","overdose","choking","not breathing","seizure",
                "fainted","collapsed","poisoning","anaphylaxis"]
            if any(w in msg.lower() for w in ew):
                self._json(200,{"reply":"⚠️ MEDICAL EMERGENCY! Call 911 immediately or go to our ER.\nEmergency Line: 1-800-555-0911\nDo NOT drive yourself.","action":"emergency","appointment":None}); return

            # Simple FAQ / keyword response (server-side fallback)
            self._json(200,{"reply":"Please type or speak your question. I am ready to help!","action":None,"appointment":None})

        elif self.path == "/api/appointments":
            try:
                appt = book_appt(body)
                self._json(201, appt)
            except Exception as e:
                self._json(500,{"error":str(e)})

    def do_DELETE(self):
        if self.path.startswith("/api/appointments/"):
            ref = self.path.split("/")[-1]
            result = cancel_appt(ref)
            if result: self._json(200, result)
            else:      self._json(404,{"error":"Not found"})

# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    url = f"http://localhost:{PORT}"

    is_local = os.getenv("RENDER") is None and os.getenv("RAILWAY_ENVIRONMENT") is None

    print(f"\n{'='*52}")
    print(f"  🏥  City General Hospital Voice Agent")
    print(f"{'='*52}")
    print(f"  ✅  Server running on port {PORT}")
    if is_local:
        print(f"  🌐  Open: http://localhost:{PORT}")
    else:
        print(f"  🚀  Running in production (cloud)")
    print(f"  🔄  Press Ctrl+C to stop")
    print(f"{'='*52}\n")

    # Auto-open browser only on local machine
    if is_local:
        def open_browser():
            import time; time.sleep(1)
            webbrowser.open(f"http://localhost:{PORT}")
        threading.Thread(target=open_browser, daemon=True).start()

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped.")
