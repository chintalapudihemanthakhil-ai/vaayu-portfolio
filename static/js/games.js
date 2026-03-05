(() => {
  // SPIN
  const spinBtn = document.getElementById("spinBtn");
  const spinImg = document.getElementById("spinImg");
  const spinCountEl = document.getElementById("spinCount");
  let spins = 0;

  function doSpin() {
    if (!spinImg) return;
    spinImg.classList.remove("spinAnim");
    void spinImg.offsetWidth;
    spinImg.classList.add("spinAnim");

    spins += 1;
    if (spinCountEl) spinCountEl.textContent = `Spins: ${spins}`;
  }

  spinBtn?.addEventListener("click", doSpin);
  spinImg?.addEventListener("click", doSpin);

  // FETCH
  const throwBtn = document.getElementById("throwBtn");
  const resetFetchBtn = document.getElementById("resetFetchBtn");
  const ball = document.getElementById("ball");
  const dog = document.getElementById("dog");
  const arena = document.getElementById("fetchArena");
  const fetchScoreEl = document.getElementById("fetchScore");

  let fetchScore = 0;
  let isThrowing = false;

  function setTransform(el, x, y) {
    el.style.transform = `translate(${x}px, ${y}px)`;
  }

  function resetFetch() {
    if (!ball || !dog) return;
    isThrowing = false;
    setTransform(ball, 0, 0);
    setTransform(dog, 0, 0);
  }

  function throwBall() {
    if (!arena || !ball || !dog || isThrowing) return;
    isThrowing = true;

    const w = arena.clientWidth;
    const targetX = Math.max(240, w - 210);
    const arcTop = -120;

    ball.animate(
      [
        { transform: "translate(0px, 0px)" },
        { transform: `translate(${targetX * 0.55}px, ${arcTop}px)` },
        { transform: `translate(${targetX}px, 0px)` }
      ],
      { duration: 900, easing: "cubic-bezier(.2,.9,.2,1)" }
    );
    setTimeout(() => setTransform(ball, targetX, 0), 880);

    dog.animate(
      [
        { transform: "translate(0px, 0px)" },
        { transform: `translate(${targetX}px, 0px)` },
        { transform: "translate(0px, 0px)" }
      ],
      { duration: 1650, easing: "cubic-bezier(.2,.9,.2,1)" }
    );

    setTimeout(() => {
      fetchScore += 1;
      if (fetchScoreEl) fetchScoreEl.textContent = `Fetch: ${fetchScore}`;
      resetFetch();
    }, 1700);
  }

  throwBtn?.addEventListener("click", throwBall);
  resetFetchBtn?.addEventListener("click", resetFetch);
  ball?.addEventListener("click", throwBall);

  // HERDING (Canvas)
  const herdStartBtn = document.getElementById("herdStartBtn");
  const herdResetBtn = document.getElementById("herdResetBtn");
  const herdScoreEl = document.getElementById("herdScore");
  const canvas = document.getElementById("herdCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const W = canvas.width;
  const H = canvas.height;

  const pen = { x: W - 170, y: H/2 - 90, w: 140, h: 180 };
  const keys = new Set();
  window.addEventListener("keydown", (e) => keys.add(e.key.toLowerCase()));
  window.addEventListener("keyup", (e) => keys.delete(e.key.toLowerCase()));

  function clamp(v, min, max){ return Math.max(min, Math.min(max, v)); }
  function dist(ax, ay, bx, by){ const dx=ax-bx, dy=ay-by; return Math.hypot(dx,dy); }

  const state = {
    running: false,
    inPen: 0,
    vaayu: { x: 120, y: H/2, r: 14, speed: 3.8 },
    sheep: []
  };

  function makeSheep(n=5){
    const arr = [];
    for(let i=0;i<n;i++){
      arr.push({
        x: 260 + Math.random()*260,
        y: 80 + Math.random()*(H-160),
        r: 10,
        vx: (Math.random()*2-1)*1.2,
        vy: (Math.random()*2-1)*1.2,
        inPen: false
      });
    }
    return arr;
  }

  function roundRect(ctx, x, y, w, h, r){
    const rr = Math.min(r, w/2, h/2);
    ctx.beginPath();
    ctx.moveTo(x+rr, y);
    ctx.arcTo(x+w, y, x+w, y+h, rr);
    ctx.arcTo(x+w, y+h, x, y+h, rr);
    ctx.arcTo(x, y+h, x, y, rr);
    ctx.arcTo(x, y, x+w, y, rr);
    ctx.closePath();
  }

  function resetHerd(){
    state.running = false;
    state.inPen = 0;
    state.vaayu.x = 120; state.vaayu.y = H/2;
    state.sheep = makeSheep(5);
    if (herdScoreEl) herdScoreEl.textContent = `In Pen: 0`;
    draw();
  }

  function updateVaayu(){
    const v = state.vaayu;
    let dx=0, dy=0;
    const up = keys.has("w") || keys.has("arrowup");
    const down = keys.has("s") || keys.has("arrowdown");
    const left = keys.has("a") || keys.has("arrowleft");
    const right = keys.has("d") || keys.has("arrowright");

    if (up) dy -= 1;
    if (down) dy += 1;
    if (left) dx -= 1;
    if (right) dx += 1;

    if (dx !== 0 || dy !== 0){
      const len = Math.hypot(dx, dy);
      dx /= len; dy /= len;
      v.x += dx * v.speed;
      v.y += dy * v.speed;
    }

    v.x = clamp(v.x, v.r + 8, W - v.r - 8);
    v.y = clamp(v.y, v.r + 8, H - v.r - 8);
  }

  function updateSheep(){
    const v = state.vaayu;
    for (const s of state.sheep){
      if (s.inPen) continue;

      const d = dist(s.x, s.y, v.x, v.y);
      if (d < 150){
        const fx = (s.x - v.x) / (d + 0.0001);
        const fy = (s.y - v.y) / (d + 0.0001);
        s.vx += fx * 0.22;
        s.vy += fy * 0.22;
      } else {
        s.vx += (Math.random()*2 - 1) * 0.04;
        s.vy += (Math.random()*2 - 1) * 0.04;
      }

      const maxV = 2.2;
      const vlen = Math.hypot(s.vx, s.vy);
      if (vlen > maxV){ s.vx = (s.vx/vlen)*maxV; s.vy = (s.vy/vlen)*maxV; }

      s.x += s.vx;
      s.y += s.vy;

      if (s.x < s.r + 8){ s.x = s.r + 8; s.vx *= -0.8; }
      if (s.x > W - s.r - 8){ s.x = W - s.r - 8; s.vx *= -0.8; }
      if (s.y < s.r + 8){ s.y = s.r + 8; s.vy *= -0.8; }
      if (s.y > H - s.r - 8){ s.y = H - s.r - 8; s.vy *= -0.8; }

      const inside =
        s.x > pen.x && s.x < pen.x + pen.w &&
        s.y > pen.y && s.y < pen.y + pen.h;

      if (inside){
        s.inPen = true;
        state.inPen += 1;
        if (herdScoreEl) herdScoreEl.textContent = `In Pen: ${state.inPen}`;
      }
    }
  }

  function draw(){
    ctx.clearRect(0,0,W,H);

    ctx.save();
    ctx.globalAlpha = 0.08;
    ctx.strokeStyle = "#ffffff";
    for(let x=0;x<W;x+=40){
      ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke();
    }
    for(let y=0;y<H;y+=40){
      ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke();
    }
    ctx.restore();

    ctx.save();
    ctx.fillStyle = "rgba(160,190,255,0.10)";
    ctx.strokeStyle = "rgba(160,190,255,0.45)";
    ctx.lineWidth = 2;
    roundRect(ctx, pen.x, pen.y, pen.w, pen.h, 16);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "rgba(245,247,255,0.75)";
    ctx.font = "700 14px Arial";
    ctx.fillText("PEN", pen.x + 12, pen.y + 24);
    ctx.restore();

    const v = state.vaayu;
    ctx.save();
    ctx.fillStyle = "rgba(160,190,255,0.95)";
    ctx.beginPath();
    ctx.arc(v.x, v.y, v.r, 0, Math.PI*2);
    ctx.fill();
    ctx.fillStyle = "rgba(7,10,18,0.9)";
    ctx.font = "900 12px Arial";
    ctx.fillText("V", v.x - 4, v.y + 4);
    ctx.restore();

    for(const s of state.sheep){
      ctx.save();
      ctx.fillStyle = s.inPen ? "rgba(170,255,210,0.95)" : "rgba(245,247,255,0.92)";
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI*2);
      ctx.fill();
      ctx.restore();
    }

    if (state.inPen >= 5){
      ctx.save();
      ctx.fillStyle = "rgba(170,255,210,0.95)";
      ctx.font = "900 28px Arial";
      ctx.fillText("Vaayu wins! 🐾", 26, 42);
      ctx.restore();
    }
  }

  function loop(){
    if (!state.running) return;
    updateVaayu();
    updateSheep();
    draw();
    requestAnimationFrame(loop);
  }

  herdStartBtn?.addEventListener("click", () => {
    if (!state.running){
      state.running = true;
      loop();
    }
  });
  herdResetBtn?.addEventListener("click", resetHerd);

  resetHerd();
})();
