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
        # In container-with-host-mount mode, commands like `free`, `nproc`, `df`
        # see the container's own /proc — which is useless for host stats.
        # CHERRY_HOST_PROC points to the mounted host /proc (e.g. /host-proc).
        # When set, we redirect those commands to read from the host procfs.
        self.host_proc = os.getenv("CHERRY_HOST_PROC", "") if self.local else ""

    def _host_command(self, command: str) -> str:
        """
        Rewrite a command so that, when running inside a container with
        CHERRY_HOST_PROC mounted, it reports HOST (not container) stats.

        - `free -h`       -> reads /proc/meminfo from host-proc
        - `nproc`         -> counts host CPU cores from host-proc/cpuinfo
        - `df -h`         -> works as-is (already queries mount points)
        - `uptime`        -> reads host-proc/uptime + loadavg
        - everything else -> unchanged
        """
        if not self.host_proc:
            return command

        cmd = command.strip()
        lower = cmd.lower()

        # free -h
        if lower.startswith("free "):
            return (
                f"awk 'BEGIN{{print \"              total        used        free      shared  buff/cache   available\"}} "
                f"/^MemTotal:/{{m=$2}} /^MemFree:/{{f=$2}} /^MemAvailable:/{{a=$2}} /^Buffers:/{{b=$2}} /^Cached:/{{c=$2}} "
                f"END{{u=m-f-b-c; printf \"%-14s %10s %10s %10s %10s %10s %10s\\n\", \"Mem:\", m, u, f, b+c, a, \"\"; "
                f"printf \"%-14s %10s %10s %10s\\n\", \"Swap:\", 0, 0, 0}}' "
                f"{self.host_proc}/meminfo"
            )

        # nproc
        if lower == "nproc" or lower.startswith("nproc "):
            return f"grep -c ^processor {self.host_proc}/cpuinfo"

        # uptime
        if lower.startswith("uptime"):
            up_file = f"{self.host_proc}/uptime"
            load_file = f"{self.host_proc}/loadavg"
            return (
                f"awk -F. '{{printf \"up %d days, %d:%02d, \", $1/86400, ($1%86400)/3600, ($1%3600)/60}}' {up_file}; "
                f"awk '{{printf \"load average: %s, %s, %s\\n\", $1, $2, $3}}' {load_file}"
            )

        # df -h
        if lower.startswith("df "):
            # df works against /proc/self/mountinfo; on the host's view we
            # just need to drop the container's overlay mounts. Simplest:
            # filter out the container's own rootfs (overlay on /).
            return f"{command} -x overlay -x tmpfs -x devtmpfs 2>/dev/null || {command}"

        return command

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
                # If we're inside a container with host /proc mounted,
                # rewrite host-stat commands to read from that mount.
                effective_cmd = self._host_command(command)
                proc = subprocess.run(effective_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
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
        return self.execute_read('docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\\t{{.Image}}"')

    def docker_stats(self) -> Dict:
        # `docker stats --no-stream` can fail with cgroup permission issues
        # even when the socket is mounted. Try it first; if it returns no
        # output, fall back to a table built from `docker inspect` (memory
        # limit) + status — still useful for capacity planning.
        r = self.execute_read(
            'docker stats --no-stream --format "table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.MemPerc}}"'
        )
        if r.get("success") and r.get("output", "").strip():
            return r

        # Fallback: assemble stats from inspect
        try:
            ps = self.execute_read('docker ps --format "{{.Names}}"')
            if not ps.get("success"):
                return r
            names = [n for n in ps["output"].splitlines() if n.strip()]
            lines = ["NAME\tCPU%\tMEM_USAGE / LIMIT\tMEM%"]
            for name in names:
                inspect = self.execute_read(
                    f"docker inspect --format "
                    f"'{{{{.Name}}}}|{{{{.HostConfig.Memory}}}}|{{{{.State.Status}}}}' {name}"
                )
                mem = "n/a"
                if inspect.get("success") and inspect["output"].strip():
                    parts = inspect["output"].strip().split("|")
                    if len(parts) >= 2 and parts[1] not in ("0", "", "<no value>"):
                        try:
                            limit_bytes = int(parts[1])
                            limit_mb = limit_bytes / 1024 / 1024
                            mem = f"n/a / {limit_mb:.0f}MiB"
                        except Exception:
                            pass
                lines.append(f"{name}\tn/a\t{mem}\tn/a")
            return {
                "success": True,
                "output": "\n".join(lines),
                "error": "",
                "command": "docker stats (fallback)",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "error": f"docker stats fallback failed: {e}", "command": "docker stats"}

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
