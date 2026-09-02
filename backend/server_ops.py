"""
🛡️ Server Operations — Safe server task executor
"""

import os
import subprocess
from typing import Dict, Optional
from datetime import datetime
from memory import log_server_task


PROD_SERVICES = {
    "portainer", "ollama", "jellyfin", "nextcloud", "pi-hole",
    "cloudflared", "wordpress", "invoiceninja", "evolution-api",
    "n8n", "homepage", "home-assistant", "immich", "zipline",
    "code-server", "nregabot", "nrega", "pihole", "nregabot_server"
}

BLOCKED_PATTERNS = [
    "rm -rf", "rm -fr", "drop", "truncate", "format",
    "mkfs", "dd if=", ":(){:|:&};:", "wget | sh", "curl | sh",
    "> /dev", "shutdown", "reboot", "halt", "poweroff",
    "kill -9", "pkill -9", "fuser -k"
]


class ServerOps:
    def __init__(self, ssh_host: str = None, ssh_user: str = "rajat"):
        # Default to NAS, but allow override. local=True means run commands directly.
        self.ssh_host = ssh_host or os.getenv("NAS_HOST", "100.98.94.128")
        self.ssh_user = ssh_user
        # local mode: only if explicitly set OR if ssh_host == "local" / "127.0.0.1"
        explicit_local = ssh_host in (None,) and os.getenv("CHERRY_LOCAL") == "1"
        self.local = explicit_local or ssh_host in ("local", "127.0.0.1", "localhost")

    def _is_blocked(self, command: str) -> bool:
        cmd_lower = command.lower()
        import re
        # Block ONLY if pattern appears as a standalone command/argument
        # (preceded/followed by space, semicolon, pipe, ||, &&, or end of string)
        # This prevents "--format" or "formatting" false positives
        word_boundary_patterns = [
            r"(^|\s|;|\||&&|\|\|)format(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)drop(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)truncate(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)kill(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)shutdown(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)reboot(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)halt(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)poweroff(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)mkfs(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)fuser(\s|$|;|\||&&)",
            r"(^|\s|;|\||&&|\|\|)pkill(\s|$|;|\||&&)",
        ]
        for pattern in word_boundary_patterns:
            if re.search(pattern, cmd_lower):
                return True

        # Substring patterns (always block)
        substring_patterns = [
            "rm -rf", "rm -fr", "dd if=", ":(){:|:&};:",
            "wget | sh", "curl | sh", "> /dev"
        ]
        return any(p in cmd_lower for p in substring_patterns)

    def _is_prod_service(self, service_name: str) -> bool:
        return any(prod in service_name.lower() for prod in PROD_SERVICES)

    def execute_read(self, command: str, timeout: int = 30) -> Dict:
        if self._is_blocked(command):
            result = {"success": False, "output": "", "error": "BLOCKED: Dangerous command pattern detected."}
            log_server_task("read", command, result["error"], False)
            return result

        try:
            if self.local:
                proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
            else:
                # SSH needs full PATH and proper shell. Use sudo for docker commands
                # because rajat user doesn't have docker group access.
                if command.strip().startswith("docker "):
                    full_cmd = f"export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH; sudo {command}"
                else:
                    full_cmd = f"export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH; {command}"
                ssh_cmd = f"ssh -o StrictHostKeyChecking=no {self.ssh_user}@{self.ssh_host} 'bash -c \"{full_cmd}\"'"
                proc = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=timeout)

            result = {
                "success": proc.returncode == 0,
                "output": proc.stdout,
                "error": proc.stderr,
                "command": command,
                "timestamp": datetime.now().isoformat()
            }
            log_server_task("read", command, proc.stdout[:500], proc.returncode == 0)
            return result
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timeout", "command": command}
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}

    def docker_ps(self) -> Dict:
        return self.execute_read('docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"')

    def docker_stats(self) -> Dict:
        return self.execute_read('docker stats --no-stream --format "table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}"')

    def docker_logs(self, container: str, lines: int = 50) -> Dict:
        if self._is_prod_service(container):
            return {
                "success": False,
                "error": f"'{container}' is a PRODUCTION service. Read-only logs only.",
                "warning": "production_service"
            }
        return self.execute_read(f"docker logs --tail {lines} {container}")

    def system_status(self) -> Dict:
        return {
            "docker_ps": self.docker_ps(),
            "disk": self.execute_read("df -h /"),
            "memory": self.execute_read("free -h"),
            "uptime": self.execute_read("uptime")
        }

    def ollama_status(self) -> Dict:
        try:
            import requests
            host = "http://localhost:11434" if self.local else f"http://{self.ssh_host}:11434"
            r = requests.get(f"{host}/api/tags", timeout=5)
            if r.status_code == 200:
                models = r.json().get("models", [])
                return {
                    "success": True,
                    "status": "running",
                    "models": [m["name"] for m in models],
                    "host": host
                }
            return {"success": False, "status": "unhealthy", "code": r.status_code}
        except Exception as e:
            return {"success": False, "status": "down", "error": str(e)}

    def check_production_health(self) -> Dict:
        cmd = "docker ps --format '{{.Names}}'"
        result = self.execute_read(cmd)
        running = result.get("output", "").strip().split("\n") if result.get("output") else []

        critical = ["portainer", "ollama", "jellyfin", "nextcloud", "homepage"]
        health = {}
        for svc in critical:
            health[svc] = "running" if any(svc in r for r in running) else "stopped"

        return {
            "running_count": len(running),
            "containers": running,
            "critical_health": health
        }


_ops: Optional[ServerOps] = None

def get_ops() -> ServerOps:
    global _ops
    if _ops is None:
        _ops = ServerOps()
    return _ops


if __name__ == "__main__":
    print("Server Operations Test")
    print("=" * 50)
    ops = get_ops()
    print(f"Mode: {'LOCAL' if ops.local else 'REMOTE'}")
    print(f"Host: {ops.ssh_host}")
