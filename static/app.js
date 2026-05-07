/* ---- State ---- */
let sessionId = null;
let uploadedImages = [];
let jobId = null;
let pollTimer = null;
let aiItems = [];       // [{script, prompt}, ...] from Claude
let autolaunchTimer = null;

/* ---- Init ---- */
document.addEventListener('DOMContentLoaded', async () => {
  const res = await fetch('/api/session', { method: 'POST' });
  sessionId = (await res.json()).session_id;
  setupDropZone();
  setupRadioCards();
  document.getElementById('scripts-input').addEventListener('input', e => {
    document.getElementById('char-count').textContent = `${e.target.value.length} characters`;
  });
});

/* ---- Drop zone ---- */
function setupDropZone() {
  const zone = document.getElementById('drop-zone');
  const fi = document.getElementById('file-input');
  zone.addEventListener('click', () => fi.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('dragover'); handleFiles([...e.dataTransfer.files]); });
  fi.addEventListener('change', () => { handleFiles([...fi.files]); fi.value = ''; });
}

async function handleFiles(files) {
  const toUpload = files.filter(f => f.type.startsWith('image/')).slice(0, 20 - uploadedImages.length);
  for (const file of toUpload) {
    const form = new FormData();
    form.append('image', file);
    try {
      const data = await (await fetch(`/api/upload-image/${sessionId}`, { method: 'POST', body: form })).json();
      if (data.filename) uploadedImages.push({ filename: data.filename, objectUrl: URL.createObjectURL(file) });
      renderGrid();
    } catch (e) { console.error(e); }
  }
}

function renderGrid() {
  const grid = document.getElementById('image-grid');
  grid.innerHTML = '';
  uploadedImages.forEach((img, idx) => {
    const d = document.createElement('div');
    d.className = 'thumb';
    d.innerHTML = `<img src="${img.objectUrl}" loading="lazy"/><button class="del" onclick="removeImage(${idx})">&#10005;</button>`;
    grid.appendChild(d);
  });
  document.getElementById('img-counter').textContent = `${uploadedImages.length} / 20 images`;
  document.getElementById('next-1').disabled = uploadedImages.length === 0;
}

async function removeImage(idx) {
  const img = uploadedImages[idx];
  URL.revokeObjectURL(img.objectUrl);
  await fetch(`/api/upload-image/${sessionId}/${img.filename}`, { method: 'DELETE' });
  uploadedImages.splice(idx, 1);
  renderGrid();
}

/* ---- Tabs ---- */
function switchTab(tab) {
  document.getElementById('pane-ai').style.display = tab === 'ai' ? 'block' : 'none';
  document.getElementById('pane-manual').style.display = tab === 'manual' ? 'block' : 'none';
  document.getElementById('tab-ai').classList.toggle('active', tab === 'ai');
  document.getElementById('tab-manual').classList.toggle('active', tab === 'manual');
}

/* ---- Count control ---- */
function adjustCount(delta) {
  const el = document.getElementById('ai-count');
  const disp = document.getElementById('ai-count-display');
  const val = Math.max(1, Math.min(20, parseInt(el.value) + delta));
  el.value = val;
  disp.textContent = val;
}

/* ---- Radio cards ---- */
function setupRadioCards() {
  document.querySelectorAll('.radio-card input[type=radio]').forEach(r => {
    r.addEventListener('change', () => {
      document.querySelectorAll(`.radio-card input[name="${r.name}"]`).forEach(x => {
        x.closest('.radio-card').classList.toggle('active', x === r);
      });
    });
  });
}

/* ---- Navigation ---- */
document.getElementById('next-1').addEventListener('click', () => goStep(2));

function goStep(n) {
  document.querySelectorAll('.panel').forEach((p, i) => p.classList.toggle('active', i + 1 === n));
  document.querySelectorAll('.step').forEach((s, i) => {
    s.classList.remove('active', 'done');
    if (i + 1 === n) s.classList.add('active');
    if (i + 1 < n) s.classList.add('done');
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ---- AI Generate ---- */
async function aiGenerate() {
  const desc = document.getElementById('ai-description').value.trim();
  if (!desc) { alert('Please describe the type of content you want.'); return; }

  const count = parseInt(document.getElementById('ai-count').value);
  const anthropicKey = document.getElementById('anthropic-key').value.trim();

  const btn = document.getElementById('ai-generate-btn');
  const status = document.getElementById('ai-status');
  const preview = document.getElementById('ai-preview');

  btn.disabled = true;
  btn.textContent = '⏳ Writing scripts...';
  status.className = 'loading';
  status.textContent = `Claude is writing ${count} scripts for "${desc}"...`;
  status.style.display = 'block';
  preview.style.display = 'none';

  const form = new FormData();
  form.append('description', desc);
  form.append('count', count);
  form.append('anthropic_key', anthropicKey);

  try {
    const res = await fetch('/api/generate-scripts', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    aiItems = data.items;
    status.style.display = 'none';
    showPreviewAndAutolaunch(aiItems, count);
  } catch (err) {
    status.className = 'error';
    status.textContent = `Error: ${err.message}`;
    btn.disabled = false;
    btn.textContent = '⚡ Generate Scripts & Launch';
  }
}

function showPreviewAndAutolaunch(items, count) {
  const preview = document.getElementById('ai-preview');
  const cards = document.getElementById('preview-cards');
  const cdEl = document.getElementById('countdown');

  cards.innerHTML = '';
  items.forEach((item, i) => {
    const d = document.createElement('div');
    d.className = 'preview-card';
    d.innerHTML = `
      <div class="pc-num">Video ${i + 1}</div>
      <div class="pc-script">${escHtml(item.script)}</div>
      <div class="pc-prompt">&#127916; ${escHtml(item.prompt)}</div>
    `;
    cards.appendChild(d);
  });

  preview.style.display = 'block';

  let secs = 3;
  cdEl.textContent = secs;
  autolaunchTimer = setInterval(() => {
    secs--;
    cdEl.textContent = secs;
    if (secs <= 0) {
      clearInterval(autolaunchTimer);
      autolaunchTimer = null;
      launchWithAiContent(items, count);
    }
  }, 1000);
}

function cancelAutolaunch() {
  if (autolaunchTimer) { clearInterval(autolaunchTimer); autolaunchTimer = null; }
  // Copy generated content into manual fields
  document.getElementById('scripts-input').value = aiItems.map(i => i.script).join('\n\n---\n\n');
  document.getElementById('prompts-input').value = aiItems.map(i => i.prompt).join('\n');
  switchTab('manual');
  document.getElementById('ai-preview').style.display = 'none';
  document.getElementById('ai-generate-btn').disabled = false;
  document.getElementById('ai-generate-btn').textContent = '⚡ Generate Scripts & Launch';
}

async function launchWithAiContent(items, count) {
  const scriptsText = items.map(i => i.script).join('\n\n---\n\n');
  const promptsText = items.map(i => i.prompt).join('\n');
  goStep(4);
  await submitGeneration(scriptsText, promptsText, count, 'separate');
}

/* ---- Manual submit (from Step 3) ---- */
async function submitManualGeneration() {
  const scripts = document.getElementById('scripts-input').value.trim();
  if (!scripts) { alert('Please enter at least one script.'); return; }
  const prompts = document.getElementById('prompts-input').value;
  const sm = document.querySelector('input[name="script-mode"]:checked').value;
  // Estimate count from script blocks
  const count = scripts.split(/\n\s*-{3,}\s*\n/).length;
  goStep(4);
  await submitGeneration(scripts, prompts, count, sm);
}

/* ---- Core generation call ---- */
async function submitGeneration(scripts, prompts, videoCount, scriptMode) {
  const im = document.querySelector('input[name="image-mode"]:checked').value;
  const cd = document.querySelector('input[name="clip-duration"]:checked').value;
  const km = document.querySelector('input[name="kling-mode"]:checked').value;
  const klingAccess = document.getElementById('kling-access').value;
  const klingSecret = document.getElementById('kling-secret').value;

  resetProgressUI(videoCount);

  const form = new FormData();
  form.append('session_id', sessionId);
  form.append('scripts', scripts);
  form.append('prompts', prompts);
  form.append('video_count', videoCount);
  form.append('image_mode', im);
  form.append('script_mode', scriptMode);
  form.append('clip_duration', cd);
  form.append('kling_mode', km);
  form.append('kling_access_key', klingAccess);
  form.append('kling_secret_key', klingSecret);

  try {
    const data = await (await fetch('/api/generate', { method: 'POST', body: form })).json();
    if (data.error) { showGenError(data.error); return; }
    jobId = data.job_id;
    startPolling(videoCount);
  } catch (e) { showGenError(String(e)); }
}

function resetProgressUI(total) {
  document.getElementById('progress-fill').style.width = '0%';
  document.getElementById('progress-label').textContent = `Starting generation of ${total} video${total !== 1 ? 's' : ''}...`;
  document.getElementById('video-list').innerHTML = '';
  document.getElementById('gen-complete').style.display = 'none';
  document.getElementById('gen-error').style.display = 'none';
  document.getElementById('gen-progress').style.display = 'block';
}

function startPolling(total) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const data = await (await fetch(`/api/status/${jobId}`)).json();
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
      ? `Done! ${data.videos.length} video${data.videos.length !== 1 ? 's' : ''} ready.`
      : `Animating video ${done + 1} of ${total} with Kling...`;

  const list = document.getElementById('video-list');
  if (data.videos) {
    for (let i = list.children.length; i < data.videos.length; i++) {
      const name = data.videos[i];
      const item = document.createElement('div');
      item.className = 'video-item';
      item.innerHTML = `
        <div><div class="vi-name">${name}</div><div class="vi-status">&#10003; Ready</div></div>
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

  if (data.status === 'error') showGenError(data.error || 'Generation failed.');
}

function showGenError(msg) {
  document.getElementById('gen-progress').style.display = 'none';
  document.getElementById('gen-error').style.display = 'block';
  document.getElementById('error-msg').textContent = `Error: ${msg}`;
}

/* ---- Reset ---- */
function resetWizard() {
  if (pollTimer) clearInterval(pollTimer);
  if (autolaunchTimer) clearInterval(autolaunchTimer);
  jobId = null; aiItems = [];
  uploadedImages = [];
  document.getElementById('image-grid').innerHTML = '';
  document.getElementById('img-counter').textContent = '0 / 20 images';
  document.getElementById('next-1').disabled = true;
  document.getElementById('ai-description').value = '';
  document.getElementById('ai-count').value = 5;
  document.getElementById('ai-count-display').textContent = 5;
  document.getElementById('ai-status').style.display = 'none';
  document.getElementById('ai-preview').style.display = 'none';
  document.getElementById('ai-generate-btn').disabled = false;
  document.getElementById('ai-generate-btn').textContent = '⚡ Generate Scripts & Launch';
  document.getElementById('scripts-input').value = '';
  document.getElementById('prompts-input').value = '';
  fetch('/api/session', { method: 'POST' }).then(r => r.json()).then(d => { sessionId = d.session_id; });
  switchTab('ai');
  goStep(1);
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
