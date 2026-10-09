/* Bubble-pop relaxation break. Calm by design: no score pressure, no game over.
   Access is limited: each unlock gives one short session (length set by the server). */
(function () {
  const panes = { locked: $('#gLocked'), ready: $('#gReady'), playing: $('#gPlaying'), done: $('#gDone') };
  const area = $('#gArea');
  let spawnTimer = null, clockTimer = null, popped = 0, endAt = 0;

  function show(name) { Object.entries(panes).forEach(([k, el]) => (el.hidden = k !== name)); }
  const fmt = (s) => `${Math.floor(s / 60)}:${pad(s % 60)}`;

  function showFor(g) {
    if (g.active_remaining > 0) return startGame(g.active_remaining);       // resume a running session
    if (g.available > 0) {
      $('#readyText').textContent = `${g.session_seconds / 60} minutes of calm · ${g.available} break${g.available > 1 ? 's' : ''} available`;
      return show('ready');
    }
    const filled = g.unlock_every - g.next_unlock_in;
    $('#lockedText').textContent = `Complete ${g.next_unlock_in} more task${g.next_unlock_in > 1 ? 's' : ''} to unlock a ${g.session_seconds / 60}-minute break.`;
    $('#lockedDots').innerHTML = Array.from({ length: g.unlock_every }, (_, i) => `<i class="${i < filled ? 'on' : ''}"></i>`).join('');
    show('locked');
  }

  function spawn() {
    const size = 46 + Math.random() * 58;
    const b = document.createElement('button');
    b.className = 'bubble';
    b.setAttribute('aria-label', 'Pop bubble');
    b.style.width = b.style.height = size + 'px';
    b.style.left = Math.random() * Math.max(10, area.clientWidth - size) + 'px';
    b.style.animationDuration = 7 + Math.random() * 5 + 's';
    b.style.background = `hsl(${180 + Math.random() * 130} 85% 78% / .55)`;
    b.addEventListener('pointerdown', () => {
      if (b.classList.contains('popped')) return;
      b.classList.add('popped');
      $('#gCount').textContent = ++popped;
      setTimeout(() => b.remove(), 220);
    });
    b.addEventListener('animationend', () => b.remove());
    area.appendChild(b);
  }

  function startGame(seconds) {
    popped = 0;
    $('#gCount').textContent = '0';
    area.innerHTML = '';
    endAt = Date.now() + seconds * 1000;
    show('playing');
    for (let i = 0; i < 5; i++) setTimeout(spawn, i * 250);
    spawnTimer = setInterval(spawn, 650);
    clockTimer = setInterval(tick, 500);
    tick();
  }

  function tick() {
    const left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
    $('#gTime').textContent = fmt(left);
    $('#gBreath').textContent = Math.floor(Date.now() / 4000) % 2 === 0 ? 'Breathe in…' : 'Breathe out…';
    if (left <= 0) finish();
  }

  function finish() {
    clearInterval(spawnTimer); clearInterval(clockTimer);
    area.innerHTML = '';
    $('#doneText').textContent = popped ? `You popped ${popped} bubble${popped > 1 ? 's' : ''}. Ready to get back to it?` : 'Ready to get back to it?';
    show('done');
    refreshHeader();
  }

  $('#gStart').addEventListener('click', async () => {
    try {
      const r = await api('/api/game/play', { method: 'POST' });
      startGame(r.remaining);
      refreshHeader();
    } catch (e) { toast(e.message, 'error'); }
  });
  $('#gEnd').addEventListener('click', finish);

  refreshHeader().then((s) => showFor(s.game));
})();
