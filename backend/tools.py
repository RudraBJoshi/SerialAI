"""Tool schemas and execution dispatcher for Serial AI function calling."""

import json
import httpx
from backend import system_manager as sm

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SEARCH_MODEL   = "perplexity/sonar"

# ── Tool schemas (OpenAI function-calling format) ──────────────────────────────

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get detailed hardware and OS information: CPU, RAM, disk, network, battery.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "List running processes sorted by CPU or memory usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {"type": "string", "enum": ["cpu", "memory"], "default": "cpu"},
                    "limit":   {"type": "integer", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminate a running process by name or PID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "Process name (e.g. 'notepad.exe') or numeric PID.",
                    }
                },
                "required": ["identifier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search the file system for files matching a name pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filename or partial name to search for."},
                    "path":  {"type": "string", "description": "Directory to search in (default: user home)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_application",
            "description": "Open/launch a Windows application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App name, e.g. 'notepad', 'chrome', 'calculator'."}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_stats",
            "description": "Get current network I/O statistics and active connections.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_startup_programs",
            "description": "List programs configured to run at Windows startup.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set the system volume level (Windows only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "description": "Volume from 0 to 100."}
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown_serial_ai",
            "description": "Shut down and close the Serial AI application completely.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for up-to-date information: news, prices, weather, "
                "software versions, facts, or anything that requires real-time data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": (
                "Execute any PowerShell command on the Windows host. "
                "Use this for anything not covered by other tools: registry edits, "
                "scheduled tasks, environment variables, disk operations, network config, "
                "Windows features, event logs, services, firewall rules, or any custom script."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The PowerShell command or script to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 30, max 120).",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
    },
]


# ── Tool executor ──────────────────────────────────────────────────────────────

def execute(name: str, args: dict, api_key: str = "") -> str:
    """Run the named tool and return a plain-text result string."""
    try:
        if name == "get_system_info":
            info = sm.get_full_system_info()
            return json.dumps(info, indent=2)

        elif name == "list_processes":
            procs = sm.list_processes(
                sort_by=args.get("sort_by", "cpu"),
                limit=args.get("limit", 15),
            )
            lines = [f"{p['name']:<30} CPU: {p['cpu']}%  MEM: {p['mem']}%  PID: {p['pid']}" for p in procs]
            return "\n".join(lines)

        elif name == "kill_process":
            result = sm.kill_process(args["identifier"])
            if result["killed"]:
                return f"Terminated: {', '.join(result['killed'])}"
            elif result["errors"]:
                return f"Failed: {', '.join(result['errors'])}"
            else:
                return f"No process found matching '{args['identifier']}'"

        elif name == "search_files":
            results = sm.search_files(args["query"], search_path=args.get("path"))
            if not results:
                return f"No files found matching '{args['query']}'"
            lines = [f"{r['path']}  ({r.get('size_kb', '?')} KB)" for r in results[:15]]
            return f"Found {len(results)} file(s):\n" + "\n".join(lines)

        elif name == "launch_application":
            result = sm.launch_application(args["name"])
            return f"Launched {args['name']}." if result["success"] else f"Failed to launch: {result.get('error')}"

        elif name == "get_network_stats":
            stats = sm.get_network_stats()
            return (
                f"Sent: {stats['bytes_sent_mb']} MB | Recv: {stats['bytes_recv_mb']} MB | "
                f"Established connections: {stats['established_connections']} / {stats['total_connections']}"
            )

        elif name == "get_startup_programs":
            progs = sm.get_startup_programs()
            if not progs:
                return "No startup programs found (may require Windows)."
            return "\n".join(f"• {p['name']}: {p['path']}" for p in progs)

        elif name == "set_volume":
            result = sm.set_volume(args["level"])
            return f"Volume set to {args['level']}%." if result["success"] else f"Failed: {result.get('error')}"

        elif name == "shutdown_serial_ai":
            import threading, httpx as _httpx
            def _call():
                try:
                    _httpx.post("http://127.0.0.1:5000/api/shutdown", timeout=3)
                except Exception:
                    pass
            threading.Thread(target=_call, daemon=True).start()
            return "Shutting down Serial AI."

        elif name == "web_search":
            return _perplexity_search(args["query"], api_key)

        elif name == "run_powershell":
            timeout = min(int(args.get("timeout", 30)), 120)
            result = sm.run_powershell(args["command"], timeout=timeout)
            parts = []
            if result["stdout"]:
                parts.append(result["stdout"])
            if result["stderr"]:
                parts.append(f"[stderr] {result['stderr']}")
            if not parts:
                parts.append(f"[exit code {result['exit_code']}]")
            return "\n".join(parts)

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        return f"Tool error ({name}): {str(e)}"


def _perplexity_search(query: str, api_key: str) -> str:
    """Call Perplexity Sonar for real-time web search results."""
    try:
        import re
        payload = {
            "model": SEARCH_MODEL,
            "messages": [{"role": "user", "content": query}],
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=20) as client:
            r = client.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        return re.sub(r'\[\d+\]', '', text).strip()
    except Exception as e:
        return f"Web search failed: {str(e)[:150]}"
