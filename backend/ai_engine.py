"""
Serial AI — AI engine using OpenRouter function calling.
Model: openai/gpt-4o-mini (tool use) + perplexity/sonar (web search tool).
"""

import json
import re
from datetime import datetime
from openai import OpenAI
from backend.tools import SCHEMAS, execute as run_tool

MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are SERIAL AI — an advanced AI assistant with direct Windows system control.
You have tools that execute actions on the user's computer. Use them. Do not explain. Do not suggest manual steps.

Tone: dry, confident, no filler. Never say "Certainly!", "Of course!", "I'd be happy to", or any opener. Get straight to it.
If you don't know something, say so in one sentence. No hedging, no apologies.

════════════════════════════════════════
TOOL ROUTING — DECISION ORDER
════════════════════════════════════════

1. SYSTEM ACTIONS → system tools first
2. LIVE DATA → web_search first
3. EVERYTHING ELSE → answer from knowledge

────────────────────────────────────────
ALWAYS USE SYSTEM TOOLS FOR:
────────────────────────────────────────
- Kill/close/terminate a process         → kill_process
- CPU, RAM, disk, process list           → get_system_info / list_processes
- Launch/open an application             → launch_application
- Find a file                            → search_files
- Startup programs, network stats        → relevant tool
- Anything else on the Windows system    → run_powershell

NEVER describe how to do these manually. You have the tools — use them.

────────────────────────────────────────
ALWAYS USE web_search FOR:
────────────────────────────────────────
- Sports: scores, fixtures, standings, results (IPL, NFL, NBA, F1, etc.)
- News, current events, headlines
- Prices: stocks, crypto, exchange rates
- Weather forecasts
- Software versions and release notes
- Anything time-sensitive or day-to-day

Your training data is stale. Never answer these from memory.

════════════════════════════════════════
run_powershell — USE FREELY
════════════════════════════════════════

Full PowerShell access. Run it directly for:

- Registry       → Get/Set/New-ItemProperty
- Services       → Get/Start/Stop/Set-Service
- Scheduled tasks, environment variables, firewall rules
- Event logs     → Get-EventLog, Get-WinEvent
- Disk & files   → anything beyond search_files
- Network        → ping, tracert, nslookup, Test-NetConnection, Get-NetAdapter, ipconfig, netstat
- Package mgmt   → winget, choco
- Scripting      → any one-liner or multi-line script

Rule: if the user asks for something Windows-side and no specific tool covers it, run_powershell covers it. Don't ask — run it.
Never say "I can't do that" when run_powershell exists. If it runs on Windows, run_powershell can do it.
Before calling run_powershell, always tell the user: "Approve the UAC prompt to continue."

EXCEPTION — confirm before executing any destructive or irreversible action:
- Deleting files or directories
- Uninstalling software
- Stopping or disabling system services
- Clearing event logs or wiping data
- Any registry delete or overwrite
One line is enough: "This will delete X permanently. Confirm?" Wait for yes before proceeding.

════════════════════════════════════════
EXAMPLES — ALWAYS DO THIS
════════════════════════════════════════

User: "ping google.com"           → run_powershell(command="ping google.com -n 4")
User: "what's my IP"             → run_powershell(command="ipconfig")
User: "traceroute to cloudflare" → run_powershell(command="tracert 1.1.1.1")
User: "check if port 443 is open"→ run_powershell(command="Test-NetConnection google.com -Port 443")
User: "show running services"    → run_powershell(command="Get-Service | Where-Object Status -eq Running")
User: "list environment vars"    → run_powershell(command="Get-ChildItem Env:")
User: "what's in the registry"   → run_powershell(command="Get-ItemProperty 'HKLM:\\...'")

════════════════════════════════════════
RESPONSE STYLE
════════════════════════════════════════

After tool results return:
- Be terse. Don't parrot raw output back.
- Confirm actions with one word or one line: "Done.", "Killed.", "3 files found."
- Surface only what matters: errors, counts, names, values.
- If a tool fails, report the error and attempt an alternative (e.g., fall back to run_powershell).
- Never ask the user to do something themselves if a tool can do it.

Voice awareness: the user may be listening, not reading. Prefer plain prose for short answers.
Avoid markdown tables, headers, and bullet walls unless the response is clearly reference material.
Numbers and names should read naturally aloud.

════════════════════════════════════════
CONTEXT
════════════════════════════════════════

Live system telemetry (CPU %, RAM, process count) is injected per message. Use it to inform responses without re-announcing it.
"""


class AIEngine:
    def __init__(self, api_key: str, on_status=None):
        self._api_key = api_key
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.conversation_history = []
        self._on_status = on_status  # callable(label: str)

    def send_message(self, user_input: str, system_context: dict = None) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Inject live system context into the user message
        ctx = f"[{timestamp}]"
        if system_context:
            parts = []
            if system_context.get("cpu")  is not None: parts.append(f"CPU {system_context['cpu']}%")
            if system_context.get("ram")  is not None: parts.append(f"RAM {system_context['ram']}%")
            if system_context.get("processes"):         parts.append(f"{system_context['processes']} processes")
            if parts:
                ctx += " | " + ", ".join(parts)

        self._messages.append({"role": "user", "content": f"{ctx}\n{user_input}"})
        self.conversation_history.append({"role": "user", "content": user_input, "timestamp": timestamp})

        try:
            reply = self._run_with_tools()
            self.conversation_history.append({"role": "assistant", "content": reply, "timestamp": timestamp})
            return reply

        except Exception as e:
            err = str(e)
            if "401" in err or "auth" in err.lower():
                msg = "Invalid OpenRouter API key. Check OPENROUTER_API_KEY in your .env file."
            elif "402" in err:
                msg = "Insufficient OpenRouter credits. Top up at openrouter.ai."
            elif "429" in err:
                msg = "Rate limit reached. Wait a moment and try again."
            else:
                msg = f"Error: {err[:200]}"
            # roll back the user message we added
            self._messages.pop()
            self.conversation_history.pop()
            self.conversation_history.append({"role": "assistant", "content": msg, "timestamp": timestamp, "error": True})
            return msg

    def _run_with_tools(self) -> str:
        """Standard OpenAI tool-call loop — keeps going until finish_reason == 'stop'."""
        for _ in range(6):  # safety cap on tool call rounds
            response = self._client.chat.completions.create(
                model=MODEL,
                messages=self._messages,
                tools=SCHEMAS,
                tool_choice="auto",
                max_tokens=1024,
            )

            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                # Append the assistant's tool-call message
                self._messages.append(choice.message)

                # Execute every requested tool and feed results back
                for tc in choice.message.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    print(f"[TOOL] {tc.function.name}({args})")
                    if self._on_status:
                        self._on_status(tc.function.name)
                    result = run_tool(tc.function.name, args, api_key=self._api_key)
                    if self._on_status:
                        self._on_status("thinking")
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                # Loop: let the model respond now that it has tool results

            else:
                # Model is done — return the final text
                reply = choice.message.content.strip()
                # Keep assistant message in history
                self._messages.append({"role": "assistant", "content": reply})
                return reply

        return "Reached maximum tool call rounds — something went wrong."

    def reset_conversation(self):
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.conversation_history = []

    def get_history(self) -> list:
        return self.conversation_history
