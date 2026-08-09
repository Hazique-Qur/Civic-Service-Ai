/**
 * CivicAI Motion Graphics Engine
 * Provides: particle constellation, 3D tilt cards, scroll reveal,
 *           animated counters, Three.js city background, typing effects
 */

// ─── Particle Constellation ───────────────────────────────────────────────────
(function initParticles() {
  const canvas = document.getElementById('particles-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, particles = [], mouse = { x: -9999, y: -9999 };
  const COUNT = 70, CONNECT_DIST = 140, MOUSE_DIST = 120;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener('mouseleave', () => { mouse.x = -9999; mouse.y = -9999; });

  for (let i = 0; i < COUNT; i++) {
    particles.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 2 + 1,
      opacity: Math.random() * 0.5 + 0.2,
      color: Math.random() > 0.5 ? '99,102,241' : '6,182,212',
    });
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    particles.forEach((p, i) => {
      // Mouse repulsion
      const mdx = mouse.x - p.x, mdy = mouse.y - p.y;
      const md = Math.sqrt(mdx * mdx + mdy * mdy);
      if (md < MOUSE_DIST) {
        const force = (MOUSE_DIST - md) / MOUSE_DIST * 0.8;
        p.vx -= (mdx / md) * force * 0.05;
        p.vy -= (mdy / md) * force * 0.05;
      }

      // Speed cap
      const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (speed > 1.5) { p.vx *= 0.98; p.vy *= 0.98; }

      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;

      // Draw particle
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.color},${p.opacity})`;
      ctx.fill();

      // Draw connections
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j];
        const dx = p.x - q.x, dy = p.y - q.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < CONNECT_DIST) {
          const alpha = (1 - d / CONNECT_DIST) * 0.18;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = `rgba(99,102,241,${alpha})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    });
    requestAnimationFrame(draw);
  }
  draw();
})();

// ─── 3D Tilt Card Effect ──────────────────────────────────────────────────────
(function initTiltCards() {
  function applyTilt(el) {
    let shine = el.querySelector('.tilt-shine');
    if (!shine) {
      shine = document.createElement('div');
      shine.className = 'tilt-shine';
      el.style.position = 'relative';
      el.appendChild(shine);
    }
    el.addEventListener('mousemove', e => {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top  + rect.height / 2;
      const dx = (e.clientX - cx) / (rect.width / 2);
      const dy = (e.clientY - cy) / (rect.height / 2);
      const rotX = -dy * 10;
      const rotY =  dx * 10;
      const mx = ((e.clientX - rect.left) / rect.width * 100).toFixed(1);
      const my = ((e.clientY - rect.top) / rect.height * 100).toFixed(1);
      el.style.transform = `perspective(900px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale(1.02)`;
      el.style.setProperty('--mx', `${mx}%`);
      el.style.setProperty('--my', `${my}%`);
    });
    el.addEventListener('mouseleave', () => {
      el.style.transform = 'perspective(900px) rotateX(0deg) rotateY(0deg) scale(1)';
    });
  }

  document.querySelectorAll('.tilt-card').forEach(applyTilt);

  // Re-apply when DOM mutates (for dynamic content)
  const observer = new MutationObserver(() => {
    document.querySelectorAll('.tilt-card:not([data-tilt-init])').forEach(el => {
      el.dataset.tiltInit = '1';
      applyTilt(el);
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();

// ─── Scroll-Reveal ────────────────────────────────────────────────────────────
(function initScrollReveal() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });

  document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale').forEach(el => {
    io.observe(el);
  });
})();

// ─── Animated Counter ─────────────────────────────────────────────────────────
window.animateCounter = function(el, target, duration = 1800, suffix = '') {
  const start = performance.now();
  const from = parseFloat(el.textContent) || 0;
  function step(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
    const current = from + (target - from) * eased;
    el.textContent = Number.isInteger(target)
      ? Math.round(current).toLocaleString()
      : current.toFixed(1);
    if (el.dataset.suffix) el.textContent += el.dataset.suffix;
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = target.toLocaleString() + suffix;
  }
  requestAnimationFrame(step);
};

// Auto-animate all [data-count] elements when they scroll into view
(function initCounters() {
  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting && !entry.target.dataset.counted) {
        entry.target.dataset.counted = '1';
        const target = parseFloat(entry.target.dataset.count);
        const suffix = entry.target.dataset.suffix || '';
        const duration = parseInt(entry.target.dataset.duration) || 1800;
        animateCounter(entry.target, target, duration, suffix);
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });
  document.querySelectorAll('[data-count]').forEach(el => io.observe(el));
})();

// ─── Typing Effect ────────────────────────────────────────────────────────────
window.typeWriter = function(el, phrases, speed = 80, pause = 2000) {
  let pi = 0, ci = 0, deleting = false;
  el.classList.add('typing-cursor');
  function tick() {
    const phrase = phrases[pi];
    if (!deleting) {
      el.textContent = phrase.substring(0, ci + 1);
      ci++;
      if (ci === phrase.length) { deleting = true; setTimeout(tick, pause); return; }
    } else {
      el.textContent = phrase.substring(0, ci - 1);
      ci--;
      if (ci === 0) { deleting = false; pi = (pi + 1) % phrases.length; }
    }
    setTimeout(tick, deleting ? speed / 2 : speed);
  }
  tick();
};

// ─── 3D Hero Background (Three.js) ───────────────────────────────────────────
window.initHeroCanvas = function() {
  const canvas = document.getElementById('hero-canvas');
  if (!canvas) return;
  if (typeof THREE === 'undefined') return;

  const scene    = new THREE.Scene();
  const camera   = new THREE.PerspectiveCamera(60, canvas.offsetWidth / canvas.offsetHeight, 0.1, 1000);
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
  renderer.setClearColor(0x000000, 0);

  camera.position.set(0, 12, 28);
  camera.lookAt(0, 0, 0);

  // Grid of city buildings
  const buildings = new THREE.Group();
  const matGlow = new THREE.MeshBasicMaterial({
    color: 0x6366f1, wireframe: true, transparent: true, opacity: 0.18
  });
  const matCyan = new THREE.MeshBasicMaterial({
    color: 0x06b6d4, wireframe: true, transparent: true, opacity: 0.14
  });
  const COLS = 9, ROWS = 9;
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const h = Math.random() * 5 + 0.5;
      const geo = new THREE.BoxGeometry(0.6, h, 0.6);
      const mat = Math.random() > 0.5 ? matGlow : matCyan;
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set((c - COLS / 2) * 2.2, h / 2 - 2, (r - ROWS / 2) * 2.2);
      buildings.add(mesh);
    }
  }
  scene.add(buildings);

  // Floating connection lines
  const lineMat = new THREE.LineBasicMaterial({
    color: 0x6366f1, transparent: true, opacity: 0.08
  });
  for (let i = 0; i < 30; i++) {
    const points = [
      new THREE.Vector3((Math.random() - 0.5) * 20, Math.random() * 10, (Math.random() - 0.5) * 20),
      new THREE.Vector3((Math.random() - 0.5) * 20, Math.random() * 10, (Math.random() - 0.5) * 20),
    ];
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), lineMat);
    scene.add(line);
  }

  // Floating dots / stars
  const dotGeo = new THREE.BufferGeometry();
  const dotPos = [];
  for (let i = 0; i < 200; i++) {
    dotPos.push((Math.random() - 0.5) * 60, Math.random() * 30 - 5, (Math.random() - 0.5) * 60);
  }
  dotGeo.setAttribute('position', new THREE.Float32BufferAttribute(dotPos, 3));
  const dots = new THREE.Points(dotGeo, new THREE.PointsMaterial({
    color: 0xa5b4fc, size: 0.12, transparent: true, opacity: 0.6
  }));
  scene.add(dots);

  // Mouse parallax
  let mx = 0, my = 0;
  window.addEventListener('mousemove', e => {
    mx = (e.clientX / window.innerWidth  - 0.5) * 2;
    my = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  // Resize
  window.addEventListener('resize', () => {
    camera.aspect = canvas.offsetWidth / canvas.offsetHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
  });

  let t = 0;
  function animate() {
    requestAnimationFrame(animate);
    t += 0.004;
    buildings.rotation.y = Math.sin(t * 0.3) * 0.12 + mx * 0.08;
    buildings.rotation.x = Math.sin(t * 0.2) * 0.04 - my * 0.04;
    dots.rotation.y = t * 0.015;
    camera.position.y = 12 + Math.sin(t * 0.4) * 1.5;
    renderer.render(scene, camera);
  }
  animate();
};

// Load Three.js dynamically then init hero canvas
(function loadThree() {
  if (document.getElementById('hero-canvas')) {
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
    s.onload = () => window.initHeroCanvas();
    document.head.appendChild(s);
  }
})();

// ─── Floating Hero Orbs Parallax ─────────────────────────────────────────────
(function initParallaxOrbs() {
  window.addEventListener('mousemove', e => {
    const nx = (e.clientX / window.innerWidth  - 0.5);
    const ny = (e.clientY / window.innerHeight - 0.5);
    document.querySelectorAll('.orb').forEach((orb, i) => {
      const depth = (i + 1) * 12;
      orb.style.transform = `translate(${nx * depth}px, ${ny * depth}px)`;
    });
  });
})();

// ─── Scan Line on stat/kpi cards ─────────────────────────────────────────────
document.querySelectorAll('.stat-card, .kpi-card, .holo-card').forEach(el => {
  el.classList.add('scan-line');
});
