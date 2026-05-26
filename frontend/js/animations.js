/* ── Background Grid + Arc Reactor Animations ── */

// ── Animated Grid Background ──────────────────────────────────────────────────
(function initGrid() {
  const canvas = document.getElementById("grid-canvas");
  const ctx = canvas.getContext("2d");

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  const GRID_SIZE = 50;
  let offset = 0;

  // Floating particles
  const particles = Array.from({ length: 40 }, () => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    vx: (Math.random() - 0.5) * 0.3,
    vy: (Math.random() - 0.5) * 0.3,
    r: Math.random() * 1.5 + 0.5,
    alpha: Math.random() * 0.5 + 0.1,
  }));

  function drawGrid() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Perspective grid lines
    ctx.strokeStyle = "rgba(0, 212, 255, 0.055)";
    ctx.lineWidth = 0.5;

    const off = (offset % GRID_SIZE);
    for (let x = -GRID_SIZE + off; x < canvas.width + GRID_SIZE; x += GRID_SIZE) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
    }
    for (let y = -GRID_SIZE + off; y < canvas.height + GRID_SIZE; y += GRID_SIZE) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.stroke();
    }

    // Diagonal accent lines
    ctx.strokeStyle = "rgba(0, 212, 255, 0.025)";
    ctx.lineWidth = 0.5;
    for (let i = -canvas.height; i < canvas.width + canvas.height; i += GRID_SIZE * 4) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i + canvas.height, canvas.height);
      ctx.stroke();
    }

    // Particles
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = canvas.width;
      if (p.x > canvas.width) p.x = 0;
      if (p.y < 0) p.y = canvas.height;
      if (p.y > canvas.height) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 212, 255, ${p.alpha})`;
      ctx.fill();
    }

    offset += 0.15;
    requestAnimationFrame(drawGrid);
  }

  drawGrid();
})();


// ── Arc Reactor / Radar HUD ───────────────────────────────────────────────────
window.ReactorAnim = (function () {
  const canvas = document.getElementById("reactor-canvas");
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const CX = W / 2;
  const CY = H / 2;

  let angle1 = 0;
  let angle2 = 0;
  let angle3 = 0;
  let pulseT = 0;
  let state = "idle"; // idle | thinking | speaking | listening

  const CYAN = "#00d4ff";
  const CYAN_DIM = "#0088aa";
  const ACCENT = "#00ffcc";
  const BLUE = "#1a7fff";

  function glow(color, blur) {
    ctx.shadowColor = color;
    ctx.shadowBlur = blur;
  }
  function noGlow() { ctx.shadowBlur = 0; }

  function drawRing(radius, lineWidth, color, alpha, dash = []) {
    ctx.beginPath();
    ctx.arc(CX, CY, radius, 0, Math.PI * 2);
    ctx.strokeStyle = color.replace(")", `, ${alpha})`).replace("rgb(", "rgba(") || color;
    ctx.lineWidth = lineWidth;
    ctx.setLineDash(dash);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function drawArc(radius, lineWidth, color, startAngle, endAngle, clockwise = true) {
    ctx.beginPath();
    ctx.arc(CX, CY, radius, startAngle, endAngle, !clockwise);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }

  function drawHexagon(cx, cy, r, color, lineWidth) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i - Math.PI / 6;
      const x = cx + r * Math.cos(a);
      const y = cy + r * Math.sin(a);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }

  function drawTick(angle, innerR, outerR, color, lineWidth) {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(CX + innerR * cos, CY + innerR * sin);
    ctx.lineTo(CX + outerR * cos, CY + outerR * sin);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }

  function drawRadarSweep(angle, radius) {
    const grad = ctx.createConicalGradient
      ? null
      : null;

    // Simulate conical gradient with arc sector
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.arc(CX, CY, radius, angle - 0.8, angle, false);
    ctx.closePath();
    const g = ctx.createRadialGradient(CX, CY, 0, CX, CY, radius);
    g.addColorStop(0, "rgba(0,212,255,0.0)");
    g.addColorStop(1, "rgba(0,212,255,0.18)");
    ctx.fillStyle = g;
    ctx.fill();
  }

  function render() {
    ctx.clearRect(0, 0, W, H);

    pulseT += 0.04;
    const pulse = 0.5 + 0.5 * Math.sin(pulseT);

    // ── Outer decorative rings ──
    glow(CYAN_DIM, 4);
    ctx.strokeStyle = "rgba(0,212,255,0.12)";
    ctx.lineWidth = 0.5;
    drawRing(138, 0.5, "rgba(0,212,255,0.08)", 1);
    drawRing(130, 0.5, "rgba(0,212,255,0.12)", 1);

    // Tick marks around outer ring
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2;
      const isMain = i % 5 === 0;
      glow(CYAN, isMain ? 6 : 2);
      drawTick(a, 122, isMain ? 130 : 126, isMain ? CYAN : CYAN_DIM, isMain ? 1.5 : 0.7);
    }

    // ── Rotating outer arc ──
    glow(CYAN, 12);
    ctx.strokeStyle = CYAN;
    ctx.lineWidth = 2;
    drawArc(118, 2, CYAN, angle1, angle1 + Math.PI * 1.4);
    drawArc(118, 1, "rgba(0,212,255,0.3)", angle1 + Math.PI * 1.4, angle1 + Math.PI * 2);

    // ── Counter-rotating arc ──
    glow("#1a7fff", 10);
    drawArc(105, 1.5, BLUE, -angle2, -angle2 + Math.PI * 1.1);

    // ── Radar sweep ──
    if (state === "listening" || state === "thinking") {
      drawRadarSweep(angle3, 95);
      glow(ACCENT, 8);
      drawArc(95, 1, ACCENT, angle3 - 0.05, angle3 + 0.05);
    }

    // ── Inner rings ──
    noGlow();
    ctx.strokeStyle = "rgba(0,212,255,0.15)";
    ctx.lineWidth = 0.5;
    drawRing(90, 0.5, "rgba(0,212,255,0.10)", 1, [3, 6]);
    drawRing(70, 0.5, "rgba(0,212,255,0.15)", 1);

    // ── Cross hairs ──
    glow(CYAN_DIM, 4);
    ctx.strokeStyle = "rgba(0,212,255,0.2)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(CX - 90, CY); ctx.lineTo(CX + 90, CY);
    ctx.moveTo(CX, CY - 90); ctx.lineTo(CX, CY + 90);
    ctx.stroke();

    // ── Hexagonal core ──
    glow(CYAN, 18);
    drawHexagon(CX, CY, 38, CYAN, 1.5);
    glow(CYAN, 8);
    drawHexagon(CX, CY, 28, "rgba(0,212,255,0.5)", 1);

    // ── Inner glow core ──
    const coreGrad = ctx.createRadialGradient(CX, CY, 0, CX, CY, 26);
    const coreAlpha = state === "speaking" ? 0.4 + 0.2 * pulse
                    : state === "thinking" ? 0.2 + 0.15 * pulse
                    : state === "listening" ? 0.3 + 0.2 * pulse
                    : 0.08 + 0.04 * pulse;
    coreGrad.addColorStop(0, `rgba(0,212,255,${coreAlpha})`);
    coreGrad.addColorStop(0.5, `rgba(0,100,200,${coreAlpha * 0.5})`);
    coreGrad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(CX, CY, 26, 0, Math.PI * 2);
    ctx.fill();

    // ── Center dot ──
    glow(CYAN, 20);
    ctx.beginPath();
    ctx.arc(CX, CY, 5, 0, Math.PI * 2);
    ctx.fillStyle = CYAN;
    ctx.fill();

    // ── State-specific overlays ──
    if (state === "thinking") {
      // Faster rotation during thinking
      glow(CYAN, 16);
      drawArc(80, 2, CYAN, angle3 * 3, angle3 * 3 + Math.PI * 0.5);
      drawArc(80, 2, CYAN, angle3 * 3 + Math.PI, angle3 * 3 + Math.PI * 1.5);
    }
    if (state === "speaking") {
      // Pulsing outer ring
      glow(ACCENT, 20 * pulse);
      ctx.strokeStyle = `rgba(0,255,204,${0.4 * pulse})`;
      ctx.lineWidth = 2 + pulse * 2;
      ctx.beginPath();
      ctx.arc(CX, CY, 115 + pulse * 8, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Update angles
    const speed = state === "thinking" ? 2.0 : state === "speaking" ? 1.5 : 1.0;
    angle1 += 0.008 * speed;
    angle2 += 0.005 * speed;
    angle3 += 0.012 * speed;

    requestAnimationFrame(render);
  }

  render();

  return {
    setState(s) {
      state = s;
      const label = document.getElementById("reactor-sublabel");
      const map = { idle: "READY", thinking: "PROCESSING", speaking: "TRANSMITTING", listening: "LISTENING" };
      if (label) label.textContent = map[s] || s.toUpperCase();
    }
  };
})();


// ── Live DateTime ─────────────────────────────────────────────────────────────
(function updateDateTime() {
  const el = document.getElementById("hud-datetime");
  function tick() {
    const now = new Date();
    el.innerHTML = now.toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "short", day: "numeric" })
      + " &nbsp; " + now.toLocaleTimeString("en-US", { hour12: false });
  }
  tick();
  setInterval(tick, 1000);
})();
