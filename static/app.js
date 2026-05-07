/* ---- State ---- */
let sessionId = null;
let uploadedImages = [];
let jobId = null;
let pollTimer = null;

/* ---- Init ---- */
document.addEventListener('DOMContentLoaded', async () => {
  const res = await fetch('/api/session', { method: 'POST' });
  const data = await res.json();
  sessionId = data.session_id;
  setupDropZone();
  setupScriptInput();
  setupRadioCards();
});

/* ---- Drop Zone ---- */
function setupDropZone() {
  const zone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('dragover'); handleFiles([...e.dataTransfer.files]); });
  fileInput.addEventListener('change', () => { handleFiles([...fileInput.files]); fileInput.value = ''; });
}

async function handleFiles(files) {
  const imageFiles = files.filter(f => f.type.startsWith('image/'));
  const toUpload = imageFiles.slice(0, 20 - uploadedImages.length);
  for (const file of toUpload) {
    const form = new FormData();
    form.append('image', file);
    try {
      const res = await fetch(`/api/upload-image/${sessionId}`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.filename) {
        uploadedImages.push({ filename: data.filename, original: file.name, objectUrl: URL.createObjectURL(file) });
        renderImageGrid();
      }
    } catch (e) { console.error('Upload failed', e); }
  }
}

function renderImageGrid() {
  const grid = document.getElementById('image-grid');
  grid.innerHTML = '';
  uploadedImages.forEach((img, idx) => {
    const div = document.createElement('div');
    div.className = 'thumb';
    div.innerHTML = `<img src="${img.objectUrl}" alt="${img.original}" loading="lazy" /><button class="del" onclick="removeImage(${idx})">&#10005;</button>`;
    grid.appendChild(div);
  });
  document.getElementById('img-counter').textContent = `${uploadedImages.length} / 20 images`;
  document.getElementById('next-1').disabled = uploadedImages.length === 0;
}

async function removeImage(idx) {
  const img = uploadedImages[idx];
  URL.revokeObjectURL(img.objectUrl);
  await fetch(`/api/upload-image/${sessionId}/${img.filename}`, { method: 'DELETE' });
  uploadedImages.splice(idx, 1);
  renderImageGrid();
}

/* ---- Script input ---- */
function setupScriptInput() {
  const ta = document.getElementById('scripts-input');
  const cc = document.getElementById('char-count');
  ta.addEventListener('input', () => { cc.textContent = `${ta.value.length} characters`; });
}

/* ---- Radio cards ---- */
function setupRadioCards() {
  document.querySelectorAll('.radio-card input[type=radio]').forEach(radio => {
    radio.addEventListener('change', () => {
      const name = radio.name;
      document.querySelectorAll(`.radio-card input[name="${name}"]`).forEach(r => {
        r.closest('.radio-card').classList.toggle('active', r === radio);
      });
    });
  });

  const vc = document.getElementById('video-count');
  vc.addEventListener('input', () => { document.getElementById('vc-display').textContent = vc.value; });
}

/* ---- Navigation ---- */
document.getElementById('next-1').addEventListener('click', () => goStep(2));

function goStep(n) {
  if (n === 4) buildSummary();
  document.querySelectorAll('.panel').forEach((p, i) => p.classList.toggle('active', i + 1 === n));
  document.querySelectorAll('.step').forEach((s, i) => {
    s.classList.remove('active', 'done');
    if (i + 1 === n) s.classList.add('active');
    if (i + 1 < n) s.classList.add('done');
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function buildSummary() {
  const vc = document.getElementById('video-count').value;
  const im = document.querySelector('input[name="image-mode"]:checked').value;
  const sm = document.querySelector('input[name="script-mode"]:checked').value;
  const cd = document.querySelector('input[name="clip-duration"]:checked').value;
  const km = document.querySelector('input[name="kling-mode"]:checked').value;
  const scripts = document.getElementById('scripts-input').value.trim();
  const scriptCount = scripts.split(/\n\s*-{3,}\s*\n/).length;
  const hasKeys = document.getElementById('kling-access').value || document.getElementById('kling-secret').value;

  document.getElementById('gen-summary').innerHTML = `
    <strong>${uploadedImages.length}</strong> image${uploadedImages.length !== 1 ? 's' : ''}
    &nbsp;&middot;&nbsp; <strong>${vc}</strong> videos
    &nbsp;&middot;&nbsp; <strong>${scriptCount}</strong> script${scriptCount !== 1 ? 's' : ''}
    &nbsp;&middot;&nbsp; Image: <strong>${im}</strong>
    &nbsp;&middot;&nbsp; Script: <strong>${sm}</strong><br/>
    Clip: <strong>${cd}s</strong>
    &nbsp;&middot;&nbsp; Quality: <strong>${km}</strong>
    &nbsp;&middot;&nbsp; Kling: <strong>${hasKeys ? 'API key set (UI)' : 'from .env / fallback to static'}</strong>
  `;
}

/* ---- Generation ---- */
async function startGeneration() {
  const scripts = document.getElementById('scripts-input').value.trim();
  if (!scripts) { alert('Please enter at least one script.'); return; }

  const vc = parseInt(document.getElementById('video-count').value);
  const im = document.querySelector('input[name="image-mode"]:checked').value;
  const sm = document.querySelector('input[name="script-mode"]:checked').value;
  const cd = document.querySelector('input[name="clip-duration"]:checked').value;
  const km = document.querySelector('input[name="kling-mode"]:checked').value;
  const prompts = document.getElementById('prompts-input').value;
  const klingAccess = document.getElementById('kling-access').value;
  const klingSecret = document.getElementById('kling-secret').value;

  document.getElementById('gen-idle').style.display = 'none';
  document.getElementById('gen-progress').style.display = 'block';
  document.getElementById('video-list').innerHTML = '';
  document.getElementById('gen-complete').style.display = 'none';

  const form = new FormData();
  form.append('session_id', sessionId);
  form.append('scripts', scripts);
  form.append('prompts', prompts);
  form.append('video_count', vc);
  form.append('image_mode', im);
  form.append('script_mode', sm);
  form.append('clip_duration', cd);
  form.append('kling_mode', km);
  form.append('kling_access_key', klingAccess);
  form.append('kling_secret_key', klingSecret);

  try {
    const res = await fetch('/api/generate', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) { showError(data.error); return; }
    jobId = data.job_id;
    pollStatus(vc);
  } catch (e) { showError(String(e)); }
}

function pollStatus(total) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${jobId}`);
      const data = await res.json();
      updateProgress(data, total);
      if (data.status === 'complete' || data.status === 'error') clearInterval(pollTimer);
    } catch (e) { console.error(e); }
  }, 3000);
}

function updateProgress(data, total) {
  const done = data.progress || 0;
  const pct = Math.round((done / Math.max(total, 1)) * 100);
  document.getElementById('progress-fill').style.width = `${pct}%`;
  document.getElementById('progress-label').textContent =
    data.status === 'complete'
      ? `Done! Generated ${data.videos.length} video${data.videos.length !== 1 ? 's' : ''}.`
      : `Generating video ${done + 1} of ${total}...`;

  const list = document.getElementById('video-list');
  if (data.videos && data.videos.length > list.children.length) {
    for (let i = list.children.length; i < data.videos.length; i++) {
      const name = data.videos[i];
      const item = document.createElement('div');
      item.className = 'video-item';
      item.innerHTML = `
        <div>
          <div class="vi-name">${name}</div>
          <div class="vi-status">&#10003; Ready</div>
        </div>
        <a class="btn" href="/api/download/${jobId}/${name}" download="${name}">&#8595; Download</a>
      `;
      list.appendChild(item);
    }
  }

  if (data.status === 'complete') {
    document.getElementById('progress-fill').style.width = '100%';
    document.getElementById('gen-complete').style.display = 'flex';
    document.getElementById('download-all-btn').onclick = () => { window.location.href = `/api/download-all/${jobId}`; };
  }

  if (data.status === 'error') showError(data.error || 'Generation failed.');
}

function showError(msg) {
  document.getElementById('gen-progress').style.display = 'none';
  document.getElementById('gen-idle').style.display = 'flex';
  const s = document.getElementById('gen-summary');
  s.style.color = '#f04';
  s.textContent = `Error: ${msg}`;
}

function resetWizard() {
  if (pollTimer) clearInterval(pollTimer);
  jobId = null;
  uploadedImages = [];
  document.getElementById('image-grid').innerHTML = '';
  document.getElementById('img-counter').textContent = '0 / 20 images';
  document.getElementById('next-1').disabled = true;
  document.getElementById('scripts-input').value = '';
  document.getElementById('prompts-input').value = '';
  document.getElementById('char-count').textContent = '0 characters';
  document.getElementById('video-count').value = 5;
  document.getElementById('vc-display').textContent = '5';
  document.getElementById('gen-idle').style.display = 'flex';
  document.getElementById('gen-progress').style.display = 'none';
  document.getElementById('gen-complete').style.display = 'none';
  document.getElementById('video-list').innerHTML = '';
  const s = document.getElementById('gen-summary');
  s.style.color = '';
  fetch('/api/session', { method: 'POST' }).then(r => r.json()).then(d => { sessionId = d.session_id; });
  goStep(1);
}
