/* ── SERIAL AI — Main Frontend Application ── */

const API = "http://127.0.0.1:5000";

// ── State ──────────────────────────────────────────────────────────────────────
let socket = null;
let isListening = false;
let msgCount = 0;
let voiceCount = 0;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const chatWindow    = document.getElementById("chat-window");
const textInput     = document.getElementById("text-input");
const sendBtn       = document.getElementById("send-btn");
const micBtn        = document.getElementById("mic-btn");
const connectionDot = document.getElementById("connection-dot");
const connectionLabel = document.getElementById("connection-label");
const aiStatusLabel = document.getElementById("ai-status-label");
const msgCountEl    = document.getElementById("msg-count");
const voiceCountEl  = document.getElementById("voice-count");
const procCountEl   = document.getElementById("proc-count");

// ── SocketIO connection ────────────────────────────────────────────────────────
let _reconnectTimer = null;

function connectSocket() {
  // Tear down any existing socket before creating a new one so we never
  // end up with two live connections both calling appendMessage.
  if (socket) {
    socket.removeAllListeners();
    socket.disconnect();
    socket = null;
  }
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }

  socket = io(API, { transports: ["websocket", "polling"] });

  socket.on("connect", () => {
    setConnectionState("online");
  });

  socket.on("disconnect", () => {
    setConnectionState("offline");
  });

  socket.on("connect_error", () => {
    setConnectionState("offline");
    // Only schedule a reconnect if this socket hasn't connected yet
    if (!socket.connected) {
      _reconnectTimer = setTimeout(connectSocket, 3000);
    }
  });

  socket.on("user_message", (data) => {
    appendMessage("user", data.text);
    msgCount++;
    msgCountEl.textContent = msgCount;
  });

  socket.on("ai_message", (data) => {
    appendMessage("ai", data.text);
  });

  socket.on("ai_status", (data) => {
    setAIState(data.status);
  });

  socket.on("ai_tool_status", (data) => {
    aiStatusLabel.textContent = data.label;
  });

  socket.on("stt_status", (data) => {
    const map = {
      calibrating: "CALIBRATING",
      listening:   "LISTENING",
      processing:  "PROCESSING",
      error:       "MIC ERROR",
      idle:        "STANDBY",
    };
    aiStatusLabel.textContent = map[data.status] || data.status.toUpperCase();
    if (data.status === "listening") {
      micBtn.classList.add("active");
      Visualizer.setMode("listening");
      ReactorAnim.setState("listening");
    } else if (data.status === "processing") {
      Visualizer.setMode("thinking");
    } else {
      micBtn.classList.remove("active");
    }
  });

  socket.on("stt_result", (data) => {
    voiceCount++;
    voiceCountEl.textContent = voiceCount;
  });

  socket.on("shutdown", () => {
    // Brief goodbye flash, then close the window
    document.body.style.transition = "opacity 0.6s";
    document.body.style.opacity = "0";
    setTimeout(() => {
      if (window.pywebview) window.pywebview.api.close_window();
      else window.close();
    }, 700);
  });
}

// ── UI State Helpers ──────────────────────────────────────────────────────────
function setConnectionState(state) {
  connectionDot.className = "status-dot" + (state === "offline" ? " offline" : "");
  connectionLabel.textContent = state === "online" ? "CONNECTED" : "OFFLINE";
}

function setAIState(state) {
  const labels = {
    idle:      "STANDBY",
    thinking:  "PROCESSING",
    speaking:  "TRANSMITTING",
    listening: "LISTENING",
  };
  aiStatusLabel.textContent = labels[state] || state.toUpperCase();

  if (state === "thinking") {
    connectionDot.classList.add("thinking");
    Visualizer.setMode("thinking");
    ReactorAnim.setState("thinking");
  } else if (state === "speaking") {
    connectionDot.classList.remove("thinking");
    Visualizer.setMode("speaking");
    ReactorAnim.setState("speaking");
  } else {
    connectionDot.classList.remove("thinking");
    Visualizer.setMode("idle");
    ReactorAnim.setState("idle");
  }
}

// ── Markdown renderer config ──────────────────────────────────────────────────
marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
  return marked.parse(text);
}

// ── Chat UI ───────────────────────────────────────────────────────────────────
function appendMessage(role, text) {
  const welcome = chatWindow.querySelector(".chat-welcome");
  if (welcome) welcome.remove();

  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;

  const roleEl = document.createElement("div");
  roleEl.className = "msg-role";
  roleEl.textContent = role === "user" ? "YOU" : "SERIAL AI";

  const textEl = document.createElement("div");
  textEl.className = "msg-text";

  div.appendChild(roleEl);
  div.appendChild(textEl);
  chatWindow.appendChild(div);

  if (role === "ai") {
    // Typewriter on raw text, then render markdown when done
    let i = 0;
    const speed = Math.max(8, Math.min(25, 2500 / text.length));
    textEl.classList.add("typing");

    const interval = setInterval(() => {
      i = Math.min(i + 2, text.length); // advance 2 chars per tick for speed
      textEl.textContent = text.slice(0, i);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      if (i >= text.length) {
        clearInterval(interval);
        textEl.classList.remove("typing");
        textEl.innerHTML = renderMarkdown(text);
        chatWindow.scrollTop = chatWindow.scrollHeight;
      }
    }, speed);
  } else {
    textEl.textContent = text;
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }
}

// ── Send Message ──────────────────────────────────────────────────────────────
async function sendMessage(text) {
  if (!text.trim()) return;
  textInput.value = "";

  try {
    await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
  } catch (e) {
    appendMessage("ai", "Connection error. Check that the server is running.");
  }
}

// ── Voice Control (Web Speech API) ────────────────────────────────────────────
let _recognition = null;

function toggleVoice() {
  if (isListening) {
    _stopVoice();
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    appendMessage("ai", "Speech recognition is not supported in this browser. Try Chrome or Edge.");
    return;
  }

  _recognition = new SpeechRecognition();
  _recognition.lang = "en-US";
  _recognition.interimResults = false;
  _recognition.continuous = false;

  _recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add("active");
    aiStatusLabel.textContent = "LISTENING";
    Visualizer.setMode("listening");
    ReactorAnim.setState("listening");
  };

  _recognition.onspeechend = () => {
    aiStatusLabel.textContent = "PROCESSING";
    Visualizer.setMode("thinking");
  };

  _recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    voiceCount++;
    voiceCountEl.textContent = voiceCount;
    sendMessage(text);
  };

  _recognition.onerror = (event) => {
    if (event.error === "not-allowed") {
      appendMessage("ai", "Microphone access denied. Allow mic permission and try again.");
    } else if (event.error !== "aborted" && event.error !== "no-speech") {
      appendMessage("ai", `Mic error: ${event.error}`);
    }
    _stopVoice();
  };

  _recognition.onend = () => {
    _stopVoice();
  };

  _recognition.start();
}

function _stopVoice() {
  isListening = false;
  micBtn.classList.remove("active");
  Visualizer.setMode("idle");
  ReactorAnim.setState("idle");
  aiStatusLabel.textContent = "STANDBY";
  if (_recognition) {
    try { _recognition.stop(); } catch (_) {}
    _recognition = null;
  }
}

// ── System Stats Polling ───────────────────────────────────────────────────────
async function pollSystemStats() {
  try {
    const [snapRes, netRes, procRes] = await Promise.all([
      fetch(`${API}/api/system/snapshot`),
      fetch(`${API}/api/system/network`),
      fetch(`${API}/api/system/processes?limit=6&sort=cpu`),
    ]);

    if (snapRes.ok) {
      const snap = await snapRes.json();
      setBar("cpu-bar", "cpu-val", snap.cpu, "%");
      setBar("ram-bar", "ram-val", snap.ram, "%");
      setBar("disk-bar", "disk-val", snap.disk_percent, "%");

      document.getElementById("footer-cpu").textContent = `CPU: ${snap.cpu}%`;
      document.getElementById("footer-ram").textContent = `RAM: ${snap.ram}%`;
      document.getElementById("footer-proc").textContent = `PROC: ${snap.processes}`;
      procCountEl.textContent = snap.processes;
    }

    if (netRes.ok) {
      const net = await netRes.json();
      document.getElementById("net-sent").textContent = `${net.bytes_sent_mb} MB`;
      document.getElementById("net-recv").textContent = `${net.bytes_recv_mb} MB`;
      document.getElementById("net-conn").textContent = net.established_connections;
    }

    if (procRes.ok) {
      const procs = await procRes.json();
      renderProcessList(procs);
    }
  } catch (e) {
    // Server not up yet
  }
}

function setBar(barId, valId, value, suffix) {
  const bar = document.getElementById(barId);
  const val = document.getElementById(valId);
  if (!bar || !val) return;

  const clamped = Math.max(0, Math.min(100, value));
  bar.style.width = `${clamped}%`;
  val.textContent = `${value}${suffix}`;

  bar.className = "stat-bar";
  if (clamped > 85) bar.classList.add("danger");
  else if (clamped > 65) bar.classList.add("warn");
}

function renderProcessList(procs) {
  const list = document.getElementById("process-list");
  if (!list) return;
  list.innerHTML = "";
  for (const p of procs.slice(0, 6)) {
    const item = document.createElement("div");
    item.className = "proc-item";
    item.innerHTML = `<span class="proc-name" title="${p.name}">${p.name}</span><span class="proc-cpu">${p.cpu}%</span>`;
    list.appendChild(item);
  }
}

// ── Quick Actions ──────────────────────────────────────────────────────────────
document.querySelectorAll(".qa-btn[data-cmd]").forEach((btn) => {
  btn.addEventListener("click", () => sendMessage(btn.dataset.cmd));
});

async function resetConversation() {
  try {
    await fetch(`${API}/api/conversation/reset`, { method: "POST" });
    chatWindow.innerHTML = `
      <div class="chat-welcome">
        <span class="welcome-line">CONVERSATION RESET</span>
        <span class="welcome-sub">Ready for new session</span>
      </div>`;
    msgCount = 0;
    voiceCount = 0;
    msgCountEl.textContent = "0";
    voiceCountEl.textContent = "0";
  } catch (e) {}
}

// ── Event Listeners ───────────────────────────────────────────────────────────
sendBtn.addEventListener("click", () => sendMessage(textInput.value));
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(textInput.value);
  }
});
micBtn.addEventListener("click", toggleVoice);

// ── Boot ──────────────────────────────────────────────────────────────────────
connectSocket();
pollSystemStats();
setInterval(pollSystemStats, 3000);

// Initial greeting animation
setTimeout(() => {
  setConnectionState("online");
}, 500);
