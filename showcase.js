// Interactive Simulator Logic for Showcase
(function() {
  const island = document.getElementById('sim-island');
  const simCover = document.getElementById('sim-pill-cover');
  const simMiniBars = document.getElementById('sim-mini-bars');
  const simBtnPlay = document.getElementById('sim-btn-play');
  const simProgressFill = document.getElementById('sim-progress-fill');
  const simProgressThumb = document.getElementById('sim-progress-thumb');
  const simProgressTrack = document.getElementById('sim-progress-track');
  const simTimeCurrent = document.getElementById('sim-time-current');
  const simSpectrum = document.getElementById('sim-spectrum');
  const screenBox = document.querySelector('.screen-simulation');
  const toolPin = document.getElementById('tool-pin');
  const toolCollapse = document.getElementById('tool-collapse');

  // Generate 24 Spectrum Bars
  const BARS_COUNT = 24;
  const bars = [];
  for (let i = 0; i < BARS_COUNT; i++) {
    const bar = document.createElement('div');
    bar.className = 'sim-vis-bar';
    simSpectrum.appendChild(bar);
    bars.push(bar);
  }

  // State
  let isPlaying = true;
  let isExpanded = false;
  let isPinned = false;
  let collapseTimeout = null;
  let trackSec = 84;
  const totalSec = 230;

  // Format Time
  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m < 10 ? '0' : ''}${m}:${sec < 10 ? '0' : ''}${sec}`;
  }

  // Expand / Collapse Island
  function expand() {
    if (collapseTimeout) {
      clearTimeout(collapseTimeout);
      collapseTimeout = null;
    }
    if (!isExpanded) {
      isExpanded = true;
      island.classList.remove('collapsed');
      island.classList.add('expanded');
    }
  }

  function collapse() {
    if (isPinned) return;
    if (collapseTimeout) clearTimeout(collapseTimeout);
    collapseTimeout = setTimeout(() => {
      isExpanded = false;
      island.classList.remove('expanded');
      island.classList.add('collapsed');
    }, 380);
  }

  island.addEventListener('mouseenter', expand);
  island.addEventListener('mouseleave', collapse);

  toolPin.addEventListener('click', (e) => {
    e.stopPropagation();
    isPinned = !isPinned;
    toolPin.style.background = isPinned ? '#ff2d75' : '';
    toolPin.style.color = isPinned ? '#fff' : '';
    if (isPinned) expand();
  });

  toolCollapse.addEventListener('click', (e) => {
    e.stopPropagation();
    isPinned = false;
    toolPin.style.background = '';
    isExpanded = false;
    island.classList.remove('expanded');
    island.classList.add('collapsed');
  });

  // Play / Pause Toggle
  simBtnPlay.addEventListener('click', (e) => {
    e.stopPropagation();
    isPlaying = !isPlaying;
    simBtnPlay.textContent = isPlaying ? '⏸' : '▶';
    simCover.style.animationPlayState = isPlaying ? 'running' : 'paused';
    simMiniBars.style.opacity = isPlaying ? '1' : '0.3';
  });

  // Audio Spectrum & Timeline Animation Loop
  let tick = 0;
  function updateAnimation() {
    tick += 0.08;

    if (isPlaying) {
      trackSec += 0.05;
      if (trackSec > totalSec) trackSec = 0;

      const pct = (trackSec / totalSec) * 100;
      simProgressFill.style.width = `${pct}%`;
      simProgressThumb.style.left = `${pct}%`;
      simTimeCurrent.textContent = formatTime(trackSec);

      // Animate 24 bars
      for (let i = 0; i < BARS_COUNT; i++) {
        const fi = i * 0.45;
        const wave = Math.sin(tick * 2.5 + fi) * 0.35 + Math.cos(tick * 1.8 - fi) * 0.35 + 0.35;
        const beat = Math.pow(Math.sin(tick * 3.5), 4) * 0.35 * (1 - i / BARS_COUNT);
        const h = Math.max(3, Math.min(24, (wave + beat) * 24));
        bars[i].style.height = `${h}px`;
      }
    } else {
      for (let i = 0; i < BARS_COUNT; i++) {
        bars[i].style.height = '3px';
      }
    }

    requestAnimationFrame(updateAnimation);
  }
  requestAnimationFrame(updateAnimation);

  // Timeline Click / Seek
  simProgressTrack.addEventListener('click', (e) => {
    e.stopPropagation();
    const rect = simProgressTrack.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, clickX / rect.width));
    trackSec = ratio * totalSec;
  });

  // Dock Position Controls
  const dockButtons = document.querySelectorAll('.btn-dock');
  dockButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      dockButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const dock = btn.getAttribute('data-dock');

      if (dock === 'right') {
        screenBox.style.justifyContent = 'flex-end';
        screenBox.style.alignItems = 'center';
      } else if (dock === 'left') {
        screenBox.style.justifyContent = 'flex-start';
        screenBox.style.alignItems = 'center';
      } else if (dock === 'top') {
        screenBox.style.justifyContent = 'center';
        screenBox.style.alignItems = 'flex-start';
      } else if (dock === 'center') {
        screenBox.style.justifyContent = 'center';
        screenBox.style.alignItems = 'center';
      }
    });
  });

  // Copy Command Button
  const btnCopy = document.getElementById('btn-copy-cmd');
  const codeText = document.getElementById('code-text');
  btnCopy.addEventListener('click', () => {
    navigator.clipboard.writeText(codeText.textContent.trim()).then(() => {
      btnCopy.textContent = 'Скопировано!';
      setTimeout(() => { btnCopy.textContent = 'Копировать'; }, 2000);
    });
  });

})();
