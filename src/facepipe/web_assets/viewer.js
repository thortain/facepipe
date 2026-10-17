const canvas = document.getElementById('mesh');
const ctx = canvas.getContext('2d');
const bars = document.getElementById('bars');
const meta = document.getElementById('meta');
const token = document.getElementById('token');
async function tick() {
  try {
    const response = await fetch('/frame.json', {
      headers: {'X-FacePipe-Token': token.value}, cache: 'no-store'
    });
    if (!response.ok) throw Error(response.status === 403 ? 'Enter the pairing token' : `HTTP ${response.status}`);
    const frame = await response.json();
    meta.textContent = `frames: ${frame.count}  tracking: ${frame.tracking}  head: ${frame.head.map(v => v.toFixed(1)).join(', ')}`;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (frame.landmarks) {
      ctx.fillStyle = '#7de';
      for (const [x, y] of frame.landmarks) ctx.fillRect(x * canvas.width - 1, y * canvas.height - 1, 2, 2);
    }
    bars.replaceChildren();
    for (const [name, value] of Object.entries(frame.blend)) {
      const div = document.createElement('div'); div.className = 'bar';
      const label = document.createElement('b'); label.textContent = name;
      const bar = document.createElement('span'); bar.style.width = `${Math.max(0, Math.min(100, value * 100))}%`;
      div.append(label, bar); bars.append(div);
    }
  } catch (error) { meta.textContent = error.message; }
  setTimeout(tick, 100);
}
tick();
