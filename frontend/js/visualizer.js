/* ── Audio Waveform Visualizer ── */

window.Visualizer = (function () {
  const canvas = document.getElementById("wave-canvas");
  const ctx = canvas.getContext("2d");

  let animFrame = null;
  let mode = "idle"; // idle | listening | speaking | thinking
  let analyser = null;
  let dataArray = null;
  let micStream = null;

  function resize() {
    canvas.width = canvas.offsetWidth * window.devicePixelRatio;
    canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }

  window.addEventListener("resize", () => { resize(); });
  resize();

  let t = 0;

  function drawIdle() {
    const W = canvas.offsetWidth;
    const H = canvas.offsetHeight;
    ctx.clearRect(0, 0, W, H);

    // Flat idle line with gentle sine wobble
    ctx.beginPath();
    for (let x = 0; x < W; x++) {
      const y = H / 2 + Math.sin((x / W) * Math.PI * 6 + t) * 2;
      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.strokeStyle = "rgba(0, 212, 255, 0.25)";
    ctx.lineWidth = 1;
    ctx.stroke();

    t += 0.03;
  }

  function drawThinking() {
    const W = canvas.offsetWidth;
    const H = canvas.offsetHeight;
    ctx.clearRect(0, 0, W, H);

    // Bouncing dot row
    const dots = 12;
    for (let i = 0; i < dots; i++) {
      const x = (W / (dots + 1)) * (i + 1);
      const phase = t + (i / dots) * Math.PI * 2;
      const y = H / 2 + Math.sin(phase) * (H / 3);
      const alpha = 0.3 + 0.5 * ((Math.sin(phase) + 1) / 2);
      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 212, 255, ${alpha})`;
      ctx.fill();
    }
    t += 0.08;
  }

  function drawListening() {
    const W = canvas.offsetWidth;
    const H = canvas.offsetHeight;
    ctx.clearRect(0, 0, W, H);

    if (analyser && dataArray) {
      analyser.getByteTimeDomainData(dataArray);
      ctx.beginPath();
      const sliceWidth = W / dataArray.length;
      let x = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * H) / 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        x += sliceWidth;
      }
      ctx.strokeStyle = "rgba(0, 255, 204, 0.7)";
      ctx.lineWidth = 1.5;
      ctx.shadowColor = "#00ffcc";
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;
    } else {
      // Fake input wave
      ctx.beginPath();
      for (let x = 0; x < W; x++) {
        const amp = 8 + Math.random() * 4;
        const y = H / 2 + Math.sin((x / W) * Math.PI * 10 + t) * amp * (0.5 + 0.5 * Math.sin(x * 0.1 + t));
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.strokeStyle = "rgba(0, 255, 204, 0.6)";
      ctx.lineWidth = 1.5;
      ctx.shadowColor = "#00ffcc";
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.shadowBlur = 0;
      t += 0.12;
    }
  }

  function drawSpeaking() {
    const W = canvas.offsetWidth;
    const H = canvas.offsetHeight;
    ctx.clearRect(0, 0, W, H);

    // Animated frequency bars
    const bars = 40;
    const barW = (W / bars) - 2;
    for (let i = 0; i < bars; i++) {
      const phase = (i / bars) * Math.PI * 4 + t;
      const h = (H * 0.7) * Math.abs(Math.sin(phase)) * (0.3 + 0.7 * Math.abs(Math.sin(t + i)));
      const x = (W / bars) * i + 1;
      const alpha = 0.3 + 0.6 * Math.abs(Math.sin(phase));

      const grad = ctx.createLinearGradient(x, H, x, H - h);
      grad.addColorStop(0, `rgba(0, 212, 255, ${alpha})`);
      grad.addColorStop(1, `rgba(0, 255, 204, ${alpha * 0.6})`);
      ctx.fillStyle = grad;
      ctx.shadowColor = "#00d4ff";
      ctx.shadowBlur = 6;
      ctx.fillRect(x, H - h, barW, h);
    }
    ctx.shadowBlur = 0;
    t += 0.1;
  }

  function loop() {
    if (mode === "idle") drawIdle();
    else if (mode === "thinking") drawThinking();
    else if (mode === "listening") drawListening();
    else if (mode === "speaking") drawSpeaking();
    animFrame = requestAnimationFrame(loop);
  }

  loop();

  async function connectMic() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStream = stream;
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      dataArray = new Uint8Array(analyser.frequencyBinCount);
      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);
    } catch (e) {
      console.warn("Mic access denied — using synthetic waveform.");
    }
  }

  return {
    setMode(m) {
      mode = m;
      if (m === "listening") connectMic();
    }
  };
})();
