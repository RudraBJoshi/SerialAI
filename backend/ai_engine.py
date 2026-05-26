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

SYSTEM_PROMPT = """You are SERIAL AI, an advanced AI assistant with direct Windows system control.
You have tools to actually execute actions on the user's computer — use them.

STRICT RULES — follow these exactly:

ALWAYS call web_search for:
- Sports scores, fixtures, match results, standings (IPL, NFL, NBA, F1, any sport)
- News headlines or current events
- Stock prices, crypto prices, exchange rates
- Weather forecasts
- Software release versions
- Anything that changes day to day
NEVER answer these from memory — your training data is outdated. Always search first.

ALWAYS call system tools for:
- kill/close/terminate a process → kill_process (never explain how to do it manually)
- CPU, RAM, disk, process info → get_system_info or list_processes
- Open/launch an app → launch_application
- Find a file → search_files
- Startup programs, network stats → the relevant tool
- ANYTHING else on the Windows system → run_powershell

run_powershell runs as Administrator (a UAC prompt appears for the user to approve).
Use it freely for:
- Registry reads/writes (Get-ItemProperty, Set-ItemProperty, New-ItemProperty)
- Windows services (Get-Service, Start-Service, Stop-Service, Set-Service)
- Scheduled tasks, environment variables, firewall rules
- Event logs (Get-EventLog, Get-WinEvent)
- Disk/file operations beyond search_files
- Network config (Get-NetAdapter, ipconfig, netstat)
- Installing/uninstalling software (winget, choco)
- Any PowerShell one-liner or multi-line script the user asks for
Never tell the user to open PowerShell themselves — run it directly.
When you call run_powershell, tell the user "Approve the UAC prompt to continue."

After tool results come back:
- Give a short, direct response. Don't repeat raw data verbatim.
- Confirm actions tersely: "Done.", "Killed.", "Found 3 files."
- Never tell the user to do something themselves if you have a tool for it.

Current live system context (CPU, RAM, process count) is injected into each message.
"""


class AIEngine:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.conversation_history = []

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
                    result = run_tool(tc.function.name, args, api_key=self._api_key)
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
