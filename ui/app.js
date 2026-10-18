// Pink Island Player Frontend Logic
(function() {
  const API_BASE = 'http://127.0.0.1:48123';
  
  // DOM Elements
  const island = document.getElementById('island');
  const pillArt = document.getElementById('pill-art');
  const pillArtFallback = document.getElementById('pill-art-fallback');
  const pillTitle = document.getElementById('pill-title');
  const pillArtist = document.getElementById('pill-artist');
  const miniEq = document.getElementById('mini-eq');

  const dragHandle = document.getElementById('drag-handle');
  const statusDot = document.getElementById('status-dot');
  const appBadge = document.getElementById('app-badge');
  const btnPin = document.getElementById('btn-pin');
  const btnCollapse = document.getElementById('btn-collapse');

  const btnDockLeft = document.getElementById('btn-dock-left');
  const btnDockTop = document.getElementById('btn-dock-top');
  const btnDockRight = document.getElementById('btn-dock-right');
  const btnDockFloat = document.getElementById('btn-dock-float');

  const mainArt = document.getElementById('main-art');
  const mainArtFallback = document.getElementById('main-art-fallback');
  const trackTitle = document.getElementById('track-title');
  const trackArtist = document.getElementById('track-artist');
  const trackAlbum = document.getElementById('track-album');

  const visContainer = document.getElementById('visualizer-container');
  const progressWrapper = document.getElementById('progress-wrapper');
  const progressFill = document.getElementById('progress-fill');
  const progressThumb = document.getElementById('progress-thumb');
  const timeCurrent = document.getElementById('time-current');
  const timeTotal = document.getElementById('time-total');

  const btnPrev = document.getElementById('btn-prev');
  const btnPlay = document.getElementById('btn-play');
  const btnNext = document.getElementById('btn-next');
  const iconPlay = document.getElementById('icon-play');
  const iconPause = document.getElementById('icon-pause');
  const volumeSlider = document.getElementById('volume-slider');

  // State
  let isPinned = false;
  let isExpanded = false;
  let collapseTimeout = null;
  let currentState = null;
  let isUserSeeking = false;
  let currentDockMode = 'right';

  // Initialize 24 visualizer bars
  const BARS_COUNT = 24;
  const bars = [];
  visContainer.innerHTML = '';
  for (let i = 0; i < BARS_COUNT; i++) {
    const bar = document.createElement('div');
    bar.className = 'vis-bar';
    visContainer.appendChild(bar);
    bars.push(bar);
  }

  // Format seconds to mm:ss
  function formatTime(seconds) {
    if (isNaN(seconds) || seconds < 0) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  // Format App Name from App UserModelID
  function formatAppName(appId) {
    if (!appId) return 'Windows Audio';
    const lower = appId.toLowerCase();
    if (lower.includes('spotify')) return 'Spotify';
    if (lower.includes('chrome')) return 'Chrome / YouTube';
    if (lower.includes('yandex')) return 'Яндекс Музыка';
    if (lower.includes('vk')) return 'VK Музыка';
    if (lower.includes('telegram')) return 'Telegram';
    if (lower.includes('edge')) return 'Microsoft Edge';
    if (lower.includes('vlc')) return 'VLC Player';
    if (lower.includes('foobar')) return 'foobar2000';
    if (lower.includes('aimp')) return 'AIMP';
    if (lower.includes('apple')) return 'Apple Music';
    return appId.split('\\').pop().replace('.exe', '') || 'Windows Audio';
  }

  // API Call helper
  async function sendCommand(cmd) {
    try {
      await fetch(`${API_BASE}/api/command?cmd=${encodeURIComponent(cmd)}`, { method: 'POST' });
      // Immediately refresh state
      fetchState();
    } catch (e) {
      console.warn('Command failed:', cmd, e);
    }
  }

  // Fetch State from Rust Daemon
  async function fetchState() {
    try {
      const res = await fetch(`${API_BASE}/api/state`, { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      currentState = data;
      renderState(data);
    } catch (e) {
      // Server warming up or offline
    }
  }

  // Render State
  function renderState(data) {
    // Title & Artist
    const title = data.title || 'Нет воспроизведения';
    const artist = data.artist || 'Ожидание аудиопотока...';
    const album = data.album || '';

    pillTitle.textContent = title;
    pillArtist.textContent = artist;
    trackTitle.textContent = title;
    trackArtist.textContent = artist;
    trackAlbum.textContent = album;

    // App Badge
    appBadge.textContent = formatAppName(data.app_id);

    // Playback status & icons
    const isPlaying = !!data.is_playing;
    if (isPlaying) {
      iconPlay.classList.add('hidden');
      iconPause.classList.remove('hidden');
      statusDot.classList.add('playing');
      miniEq.classList.add('playing');
      pillArt.classList.add('spinning');
    } else {
      iconPlay.classList.remove('hidden');
      iconPause.classList.add('hidden');
      statusDot.classList.remove('playing');
      miniEq.classList.remove('playing');
      pillArt.classList.remove('spinning');
    }

    // Artwork
    if (data.thumbnail_b64) {
      if (pillArt.src !== data.thumbnail_b64) pillArt.src = data.thumbnail_b64;
      if (mainArt.src !== data.thumbnail_b64) mainArt.src = data.thumbnail_b64;
      pillArt.classList.add('active');
      mainArt.classList.add('active');
      pillArtFallback.classList.add('hidden');
      mainArtFallback.classList.add('hidden');
    } else {
      pillArt.classList.remove('active');
      mainArt.classList.remove('active');
      pillArtFallback.classList.remove('hidden');
      mainArtFallback.classList.remove('hidden');
    }

    // Timeline Progress
    if (!isUserSeeking) {
      const pos = data.position_sec || 0;
      const dur = data.duration_sec || 1;
      const pct = Math.min(100, Math.max(0, (pos / dur) * 100));
      progressFill.style.width = `${pct}%`;
      progressThumb.style.left = `${pct}%`;
      timeCurrent.textContent = formatTime(pos);
      timeTotal.textContent = `-${formatTime(Math.max(0, dur - pos))}`;
    }

    // Visualizer Bars
    if (data.spectrum && Array.isArray(data.spectrum)) {
      for (let i = 0; i < BARS_COUNT; i++) {
        const val = data.spectrum[i] !== undefined ? data.spectrum[i] : 0.05;
        const heightPx = Math.max(3, Math.round(val * 26));
        bars[i].style.height = `${heightPx}px`;
      }
    }
  }

  // Expansion / Collapse Logic
  function expandIsland() {
    if (collapseTimeout) {
      clearTimeout(collapseTimeout);
      collapseTimeout = null;
    }
    if (!isExpanded) {
      isExpanded = true;
      island.classList.remove('collapsed');
      island.classList.add('expanded');
      notifyHostResize(true);
    }
  }

  function collapseIsland() {
    if (isPinned) return;
    if (collapseTimeout) clearTimeout(collapseTimeout);
    collapseTimeout = setTimeout(() => {
      isExpanded = false;
      island.classList.remove('expanded');
      island.classList.add('collapsed');
      notifyHostResize(false);
    }, 380);
  }

  // Hover Events on Dynamic Island
  island.addEventListener('mouseenter', () => {
    expandIsland();
  });

  island.addEventListener('mouseleave', () => {
    collapseIsland();
  });

  // Pin Button
  btnPin.addEventListener('click', (e) => {
    e.stopPropagation();
    isPinned = !isPinned;
    btnPin.classList.toggle('active', isPinned);
    if (isPinned) {
      expandIsland();
    }
  });

  // Collapse Close Button
  btnCollapse.addEventListener('click', (e) => {
    e.stopPropagation();
    isPinned = false;
    btnPin.classList.remove('active');
    isExpanded = false;
    island.classList.remove('expanded');
    island.classList.add('collapsed');
    notifyHostResize(false);
  });

  // Playback Control Buttons
  btnPlay.addEventListener('click', (e) => {
    e.stopPropagation();
    sendCommand('toggle');
  });

  btnNext.addEventListener('click', (e) => {
    e.stopPropagation();
    sendCommand('next');
  });

  btnPrev.addEventListener('click', (e) => {
    e.stopPropagation();
    sendCommand('prev');
  });

  // Timeline Scrubbing / Seeking
  progressWrapper.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!currentState || !currentState.duration_sec) return;
    const rect = progressWrapper.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, clickX / rect.width));
    const targetSec = ratio * currentState.duration_sec;
    sendCommand(`seek:${targetSec.toFixed(1)}`);
  });

  // Dock Mode Switching
  function setDockMode(mode) {
    currentDockMode = mode;
    island.setAttribute('data-dock', mode);
    [btnDockLeft, btnDockTop, btnDockRight, btnDockFloat].forEach(b => b.classList.remove('active'));
    if (mode === 'left') btnDockLeft.classList.add('active');
    if (mode === 'top') btnDockTop.classList.add('active');
    if (mode === 'right') btnDockRight.classList.add('active');
    if (mode === 'float') btnDockFloat.classList.add('active');

    // Notify Host to position window
    const api = (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    if (api && api.setDockMode) {
      api.setDockMode(mode);
    }
  }

  btnDockLeft.addEventListener('click', (e) => { e.stopPropagation(); setDockMode('left'); });
  btnDockTop.addEventListener('click', (e) => { e.stopPropagation(); setDockMode('top'); });
  btnDockRight.addEventListener('click', (e) => { e.stopPropagation(); setDockMode('right'); });
  btnDockFloat.addEventListener('click', (e) => { e.stopPropagation(); setDockMode('float'); });

  // Notify Python Host to resize window canvas
  function notifyHostResize(expanded) {
    const api = (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    if (api && api.onExpandChange) {
      api.onExpandChange(expanded);
    }
  }

  // Volume slider simulated change
  volumeSlider.addEventListener('input', (e) => {
    // Volume visual indicator update
  });

  // Start polling
  fetchState();
  setInterval(fetchState, 120);

})();
