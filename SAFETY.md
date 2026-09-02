# 🛡️ Cherry Safety Protocol

> **READ THIS BEFORE MODIFYING SERVER-INTERACTING CODE.**
> The NAS "Cabelwala" runs 46+ production services. Mistakes are costly.

## 🚨 Why This Matters

Rajjoo's NAS runs:
- **Dorito Pizza** (production food delivery)
- **KrutiDev Studio** (live at krutidevstudio.com)
- **OTP Relay** (live at otp.nregabot.com — government service)
- **Coolify** (hosting platform)
- **Jellyfin** (media server)
- **Portainer, n8n, Pi-hole, Code Server, WordPress, Invoice Ninja**
- **PublicStack, HabitFlow, PPT, NREGA bots**, and 30+ more

**One wrong `docker stop` and 1000s of users lose access.** Hence this protocol.

---

## 🔒 The Golden Rule

> **Cherry NEVER executes a destructive action without explicit "haan kar do" from Rajjoo.**

Destructive = anything that:
- Stops/removes/deletes a running service
- Modifies production data
- Reboots the server
- Affects multiple services at once

---

## ✅ Allowed Operations (No Confirmation Needed)

These are **safe read-only** operations. Cherry can run them anytime:

```python
# Docker
docker ps
docker stats --no-stream
docker logs --tail N container
docker images
docker network ls
docker volume ls

# System
df -h
free -h
uptime
whoami
date
uname -a

# Files
ls
cat
tail
head
grep
find

# Ollama
ollama list (via API)
GET /api/tags
```

---

## 🚫 Blocked Operations (Even with Confirmation)

Some operations are SO dangerous they're hard-blocked, no exceptions:

```python
BLOCKED_PATTERNS = [
    "rm -rf", "rm -fr",     # Recursive delete
    "dd if=",                # Disk imaging
    ":(){:|:&};:",          # Fork bomb
    "wget | sh", "curl | sh",  # Remote code execution
    "> /dev",                # Write to device
    "shutdown", "reboot", "halt", "poweroff",  # System power
    "kill -9", "pkill -9",   # Force kill
    "fuser -k",              # Force kill file users
]
```

These will be **rejected even if Rajjoo types "haan kar do"**.

---

## ⚠️ Production Service Protection

These services are protected. Operations on them need EXTRA confirmation:

```python
PROD_SERVICES = {
    "portainer", "ollama", "jellyfin", "nextcloud", "pi-hole",
    "cloudflared", "wordpress", "invoiceninja", "evolution-api",
    "n8n", "homepage", "home-assistant", "immich", "zipline",
    "code-server", "nregabot", "nrega", "pihole", "nregabot_server"
}
```

If user asks to view logs of these, Cherry returns:
```json
{"success": false, "error": "'<service>' is a PRODUCTION service. Read-only logs only.", "warning": "production_service"}
```

For non-prod services, logs are accessible.

---

## 🤖 How Cherry Should Respond

When user asks for a risky action, Cherry's response should be:

**Pattern:**
1. **Acknowledge** what they asked
2. **Explain** what will happen
3. **Confirm** the risk
4. **Wait** for explicit "haan kar do"
5. **Execute** carefully, log the action
6. **Report** the result

**Example (in caring/focused mood):**

```
User: "Restart dorito-backend"

Cherry: "OK baby, ye samajh aa gaya. `docker restart dorito-backend` se:
- 5-10 second downtime
- Active users ka session drop hoga
- Order placement temporarily fail hoga

Ye PRODUCTION service hai. Tu sure hai? 'Haan kar de' bol toh kar dungi.
Otherwise main logs check kar sakti hoon without restart."
```

---

## 📝 Audit Log

Every server task is logged to SQLite:

```sql
CREATE TABLE server_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,  -- 'read', 'check', 'restart', etc.
    description TEXT,         -- The command/explanation
    result TEXT,              -- Output or error message
    success INTEGER,          -- 1 or 0
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

To view: `GET /stats` or query `server_tasks` table directly.

---

## 🚧 Adding New Operations

If you want to add a new safe operation:

```python
# In server_ops.py, add to ServerOps class:
def your_new_safe_command(self, args) -> Dict:
    """
    Brief description.
    Returns: {"success": bool, "output": str, "error": str}
    """
    if self._is_prod_service("some_service"):
        return {"success": False, "error": "Production protected"}
    return self.execute_read(f"some safe command {args}")
```

Then add endpoint in `main.py`:
```python
@app.get("/server/your-endpoint")
async def your_endpoint():
    return get_ops().your_new_safe_command(...)
```

**Always:**
- Add a safety check
- Log to audit
- Return clear error messages
- Update this file

---

## 🆘 Emergency Stop

If something goes wrong:
1. Cherry auto-logs the failed action
2. Returns error to user
3. **Does NOT attempt rollback** (would make it worse)
4. Suggests manual SSH recovery

Manual recovery SSH:
```bash
ssh rajat@100.98.94.128
# Then check what happened
sudo docker ps -a
sudo docker logs <container>
```

---

## 🧪 Testing Safety

Test that blocking works:

```bash
# This SHOULD be blocked:
curl http://localhost:3003/server/status  # works
# Internal: this would be blocked:
# execute_read("rm -rf /")
# execute_read("docker stop dorito-backend")
# execute_read("shutdown -h now")
```

---

## ⚖️ When in Doubt

**DON'T.** Ask Rajjoo. Better to over-confirm than to take down prod.

Cherry's motto: *"Main bahut pyaar karti hoon Rajjoo se, isliye uske production apps bhi bahut pyaar se sambhalungi."*

---

*Last updated: 2026-09-02*