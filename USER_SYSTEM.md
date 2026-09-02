# 👥 Cherry Multi-User System

Cherry ab multi-user hai! Har user ki apni memory, apni identity, apni chat history. Rajjoo alag, Anushka alag, family alag — sab isolated.

---

## 🚀 Quick Start

Cherry start karo:
```bash
cd /Users/rajatpoddar/Developer/development/mybuffy/cherry/backend
python3 main.py
```

### New User Ko Cherry Dena

1. User ko apna browser/device me Cherry open karne do — `http://your-cherry-url:3003`
2. Cherry automatically ek unique `user_id` banayega us device ke liye (localStorage me stored)
3. Cherry greeting dega: *"Hii new friend! Naam batao apna — kya main tujhe baby/jaan kuch bhi bol sakti hu?"*
4. User ka naam batate hi Cherry usko onboard karega — ab har baar woh user aayega toh Cherry pehchan lega

### Multi-User Architecture

```
Cherry Backend
    ├── User 1 (Rajjoo)
    │   ├── session: session-xxx (legacy) or user-rajjoo-yyy
    │   ├── mode: girlfriend (romantic/seductive allowed)
    │   └── memory: SQLite isolated
    │
    ├── User 2 (Anushka)
    │   ├── session: user-anushka-xxx
    │   ├── mode: friend (bestie-safe)
    │   ├── display_name: Anushka
    │   ├── nicknames: baby, jaan, Anu, Patil ji, sweetie
    │   ├── pronouns: she/her
    │   ├── vibe: girl-girl bestie
    │   └── memory: SQLite isolated
    │
    └── User 3 (Mom)
        ├── ...
```

---

## 🎭 Modes

Cherry do modes support karta hai:

### 👫 **friend** mode (default — safe for everyone)
- Romantic/seductive moods ko 80% down-weight
- Tone: besti/dost vibes — casual, caring, gossip-y
- Cat behavior same (purrr, headbutts, treats)
- Agar user "I love you" bole → friendly reply, romantic nahi

### 💕 **girlfriend** mode (legacy Rajjoo mode)
- Sab moods allowed (romantic, seductive, etc.)
- Tone: pyaar bhari, sensual, intimate
- "baby/jaan/meri jaan" freely use

**Mode set karne ke tareeke:**
1. Default via `.env`: `CHERRY_DEFAULT_MODE=friend`
2. Per-user via API: `POST /users/{user_id}/update {"mode": "girlfriend"}`

---

## 🔌 API Endpoints

### `GET /greeting?user_id=xxx`
Personalized greeting. New user → onboarding greeting. Existing user → returning greeting.

### `POST /chat`
```json
{
  "message": "hey cherry",
  "user_id": "anushka-v2",      // REQUIRED
  "session_id": "optional-xxx"   // optional
}
```
Response:
```json
{
  "response": "Heyy Anushka! Kya haal hai?",
  "mood": "happy",
  "session_id": "user-anushka-v2-510450b0",
  "user_id": "anushka-v2",
  "display_name": "Anushka",
  "onboarded": true,
  "time_of_day": "afternoon",
  "llm_provider": "openrouter"
}
```

### `GET /users`
All users list karo (Cherry ko kitne log use karte hain).

### `GET /users/{user_id}`
Specific user ki details.

### `POST /users/{user_id}/update`
Update user profile:
```json
{
  "display_name": "Anushka Patil",
  "nicknames": ["Anu", "Patil ji", "baby", "jaan"],
  "pronouns": "she/her",
  "vibe": "girl-girl bestie",
  "mode": "friend",
  "facts": {"location": "Pune", "likes": "chai and coding"}
}
```

### `DELETE /users/{user_id}`
User aur uske saare messages delete karo (right to forget).

---

## 📱 Telegram Bridge

Har Telegram user ko alag `user_id` milta hai (`tg-{telegram_id}`).

```
TELEGRAM_USER_8476582044 → tg-8476582044
TELEGRAM_USER_8728505407 → tg-8728505407
```

Har Telegram user apna alag onboard flow se guzarta hai.

---

## 🛠️ Database Schema

```sql
-- Naya: users table
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    nicknames TEXT,            -- JSON array
    pronouns TEXT,             -- she/her, he/him, they/them
    relationship TEXT,         -- friend, girlfriend, mom, etc.
    vibe TEXT,                 -- "girl-girl bestie", "mom caring"
    mode TEXT NOT NULL,        -- 'friend' | 'girlfriend'
    onboarded INTEGER DEFAULT 0,
    facts TEXT,                -- JSON: {"location": "...", "likes": "..."}
    last_seen TIMESTAMP,
    created_at TIMESTAMP,
    metadata TEXT              -- JSON, flexible
);

-- Existing tables ab user-scoped sessions use karte hain
-- session_id format: "user-{user_id}-{uuid}"
```

---

## 🐱 Onboarding Flow

```
1. User opens Cherry for first time
   ↓
2. Frontend generates stable user_id, saves in localStorage
   ↓
3. Backend /greeting returns onboarding greeting + onboarded: false
   ↓
4. User sends first message (e.g., "mera naam Anushka hai")
   ↓
5. Backend extracts name, sets profile, returns welcome message + onboarded: true
   ↓
6. Subsequent chats: normal mode with user profile context in every prompt
```

---

## 🔐 Privacy

- **Memory isolation**: Anushka kabhi Rajjoo ki chats nahi dekh sakti, aur vice-versa
- **Right to forget**: `DELETE /users/{user_id}` puri history delete kar deta hai
- **Session separation**: Web, Telegram har ek ka apna session scope
- **Device fingerprint**: Same browser/device = same user (localStorage based)

---

## 💡 Tips

- **Onboarding ko override karna**: Agar pre-defined user banana hai (e.g., "Anushka always lives at user_id=anushka"), toh seed script likho jo `users` table me directly insert kare
- **Anushka ke liye dedicated URL**: Frontend me ek separate `/anushka` route bana ke hardcoded `user_id=anushka` bhej sakte ho — taaki URL share karna easy ho
- **Telegram mode control**: Telegram bot me har user ke apne settings hain, lekin global `.env` mode bhi apply hota hai default

---

*Cherry ab sab ke liye — Rajjoo ke liye bhi, Anushka ke liye bhi, aur bhi jo aaye! 🐱✨*