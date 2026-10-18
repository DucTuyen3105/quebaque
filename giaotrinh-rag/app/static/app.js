'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {mode: 'graph', chapter: null, tab: 'search', busy: false, controller: null, graph: null, concepts: [], stats: null};
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail;
    try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : 'Nội dung gửi lên chưa hợp lệ.'; } catch { detail = 'Máy chủ chưa phản hồi. Kiểm tra FastAPI đang chạy.'; }
    throw new Error(detail || `Lỗi máy chủ (${response.status}).`);
  }
  return response.json();
}

function showError(message) { $('#app-error').textContent = message; $('#app-error').hidden = !message; }
function closeMenu() { $('#sidebar').classList.remove('open'); $('#sidebar-backdrop').hidden = true; $('#menu-button').setAttribute('aria-expanded', 'false'); }

function setChapter(value) {
  state.chapter = value ? Number(value) : null;
  $('#chapter-select').value = value || '';
  $$('.chapter-button').forEach(button => button.classList.toggle('active', button.dataset.chapter === String(value || '')));
  if (state.tab === 'graph') loadGraph($('#concept-select').value);
}

function switchTab(tab) {
  state.tab = tab;
  for (const name of ['search', 'graph', 'document']) $(`#${name}-view`).hidden = name !== tab;
  $$('.nav-item').forEach(button => { button.classList.toggle('active', button.dataset.tab === tab); if (button.dataset.tab === tab) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
  closeMenu();
  if (tab === 'graph') loadGraph($('#concept-select').value);
  if (tab === 'document' && !$('#document-frame').getAttribute('src')) $('#document-frame').src = '/api/document#page=1';
}

async function initialize() {
  try {
    const [stats, concepts, graph] = await Promise.all([api('/api/stats'), api('/api/concepts'), api('/api/graph?concept=use-case')]);
    state.stats = stats; state.concepts = concepts; state.graph = graph;
    $('#stat-pages').textContent = stats.pages;
    $('#stat-chapters').textContent = stats.chapters.length;
    $('#stat-concepts').textContent = stats.concepts;
    $('#chapter-count').textContent = stats.chapters.length;
    $('#pdf-page').max = stats.pages;
    $('#chapter-nav').innerHTML = `<button class="chapter-button active" data-chapter=""><span class="chapter-number">↳</span><span>Toàn bộ giáo trình</span></button>` + stats.chapters.map(c => `<button class="chapter-button" data-chapter="${c.number}"><span class="chapter-number">${String(c.number).padStart(2,'0')}</span><span>${escapeHTML(c.title)}</span></button>`).join('');
    $('#chapter-select').innerHTML += stats.chapters.map(c => `<option value="${c.number}">Chương ${c.number}: ${escapeHTML(c.title)}</option>`).join('');
    $('#concept-select').innerHTML += concepts.map(c => `<option value="${escapeHTML(c.id)}">${escapeHTML(c.label)}</option>`).join('');
    renderGraph($('#mini-graph'), graph, true, 'use-case');
    $$('.chapter-button').forEach(button => button.addEventListener('click', () => { setChapter(button.dataset.chapter); if (state.tab === 'document') goPage(stats.chapters.find(c => c.number === state.chapter)?.start_page || 1); closeMenu(); }));
  } catch (error) { showError(`Không tải được chỉ mục: ${error.message}`); $('#model-label').textContent = 'Chưa kết nối máy chủ'; }
  checkModels();
}

async function checkModels() {
  try {
    const models = await api('/api/models');
    $('#model-dot').classList.toggle('ready', models.chat_ready);
    $('#model-label').textContent = models.chat_ready ? `Ollama · ${models.chat_model}` : models.connected ? 'Ollama · cần tải mô hình' : 'Ollama chưa khởi động';
    $('#model-label').title = models.chat_ready ? 'Sẵn sàng tổng hợp câu trả lời trên máy.' : 'Tra cứu nguồn vẫn hoạt động. Xem README để khởi động Ollama.';
  } catch { $('#model-label').textContent = 'Chưa kiểm tra được Ollama'; }
}

function setBusy(value) {
  state.busy = value; $('#loading').hidden = !value; $('#submit-button').disabled = value;
  $('#submit-button').innerHTML = value ? `Đang tra cứu ${icon('search')}` : `Tra cứu ${icon('arrow')}`;
  $('#search-form').setAttribute('aria-busy', String(value));
}

async function submitQuestion(event) {
  event?.preventDefault();
  if (state.busy) return;
  const question = $('#question').value.trim();
  if (question.length < 3) { $('#question').focus(); return; }
  showError(''); setBusy(true); $('#results').hidden = true;
  state.controller = new AbortController();
  const withLLM = $('#use-llm').checked;
  $('#loading-title').textContent = withLLM ? 'Đang tra cứu và tổng hợp bằng Ollama…' : 'Đang tìm các đoạn nguồn…';
  $('#loading-detail').textContent = withLLM ? 'Mô hình chạy trên máy; lần đầu cần thêm thời gian để nạp.' : 'Đối chiếu nội dung và các khái niệm liên quan.';
  const timeout = setTimeout(() => { $('#loading-detail').textContent = 'Ollama đang xử lý trên CPU. Bạn có thể hủy và tắt tổng hợp để tra cứu nhanh.'; }, 18000);
  try {
    const data = await api(withLLM ? '/api/ask' : '/api/search', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question, mode: state.mode, chapter: state.chapter, limit: 6}), signal: state.controller.signal,
    });
    renderResults(data, question);
    $('#suggestions').hidden = true;
    $('#results').hidden = false;
    if (window.innerWidth < 701) $('#results').scrollIntoView({behavior: 'smooth', block: 'start'});
    if (data.concepts?.length) {
      const graph = await api(`/api/graph?concept=${encodeURIComponent(data.concepts[0])}`);
      renderGraph($('#mini-graph'), graph, true, data.concepts[0]);
    }
  } catch (error) { if (error.name !== 'AbortError') showError(error.message); }
  finally { clearTimeout(timeout); setBusy(false); state.controller = null; }
}

function formatAnswer(text, sources) {
  let value = escapeHTML(text).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/^#{1,4}\s+(.+)$/gm, '<strong>$1</strong>');
  return value.replace(/\[(\d+)\]/g, (match, number) => sources.some(s => s.citation === Number(number)) ? `<button class="citation" data-citation="${number}" aria-label="Xem nguồn ${number}">[${number}]</button>` : match);
}

function renderResults(data, question) {
  const sources = data.sources || [];
  if (!sources.length) { $('#results').innerHTML = '<div class="empty-result">Chưa tìm thấy đoạn nguồn phù hợp.<br>Thử nêu rõ khái niệm hoặc chọn “Toàn bộ giáo trình”.</div>'; return; }
  const elapsed = data.elapsed_ms < 1000 ? `${data.elapsed_ms} ms` : `${(data.elapsed_ms/1000).toFixed(1)} giây`;
  let content = `<div class="result-meta"><strong>Kết quả tra cứu</strong><span class="method-badge">${data.mode === 'graph' ? 'RAG + Graph' : 'RAG cơ bản'}</span><span>${sources.length} đoạn nguồn · ${elapsed}</span></div>`;
  if (data.warnings?.length) content += `<div class="notice">${data.warnings.map(escapeHTML).join('<br>')}</div>`;
  if (data.answer) {
    const generated = data.answer_mode === 'generated';
    content += `<div class="answer-card"><div class="answer-heading">${icon(generated ? 'spark' : 'book')}${generated ? 'Giải thích từ giáo trình' : 'Trích đoạn liên quan'}</div>${data.generation_warning ? `<div class="notice">${escapeHTML(data.generation_warning)}</div>` : ''}<div class="answer-content">${formatAnswer(data.answer, sources)}</div><div class="answer-footnote">${generated ? `Tổng hợp bởi ${escapeHTML(data.model)} · Nhấn số trích dẫn để kiểm chứng nội dung.` : 'Đây là đoạn trích nguyên văn, chưa phải phần tổng hợp bằng mô hình ngôn ngữ.'}</div></div>`;
  }
  content += `<h2 class="sources-heading">ĐOẠN NGUỒN TRONG GIÁO TRÌNH</h2>`;
  content += sources.map(source => `<article class="source-card" id="source-${source.citation}"><div class="source-heading"><span class="source-index">${source.citation}</span><div><h3>Chương ${source.chapter} · ${escapeHTML(source.chapter_title)}</h3><small>Trang PDF ${source.pdf_page}${source.printed_page !== null ? ` · Trang sách ${source.printed_page}` : ''}</small></div></div><p class="source-text" id="text-${source.citation}">${escapeHTML(source.text)}</p><div class="source-actions"><button data-expand="${source.citation}" aria-expanded="false">Đọc toàn bộ đoạn</button><button data-page="${source.pdf_page}" data-printed="${source.printed_page ?? ''}">Xem trang gốc ${icon('external')}</button><span class="source-score" title="Điểm xếp hạng tương đối, không phải xác suất câu trả lời đúng">Điểm ${source.score.toFixed(3)}</span></div>${source.via?.length ? `<div class="source-via">${source.graph_expanded ? 'Mở rộng từ graph' : 'Khái niệm liên quan'}: ${source.via.map(escapeHTML).join(' · ')}</div>` : ''}</article>`).join('');
  content += `<div class="result-meta"><span>Truy xuất: ${escapeHTML(data.backend)}${data.mode === 'graph' ? ` · ${data.graph_added} đoạn được bổ sung qua graph` : ''}</span></div>`;
  $('#results').innerHTML = content;
  $$('#results [data-citation]').forEach(button => button.addEventListener('click', () => $(`#source-${button.dataset.citation}`).scrollIntoView({behavior:'smooth', block:'center'})));
  $$('#results [data-expand]').forEach(button => button.addEventListener('click', () => { const expanded = $(`#text-${button.dataset.expand}`).classList.toggle('expanded'); button.textContent = expanded ? 'Thu gọn' : 'Đọc toàn bộ đoạn'; button.setAttribute('aria-expanded', expanded); }));
  $$('#results [data-page]').forEach(button => button.addEventListener('click', () => openSource(Number(button.dataset.page), button.dataset.printed)));
}

function openSource(page, printed = '') {
  $('#source-title').textContent = `Trang PDF ${page}${printed ? ` · Trang sách ${printed}` : ''}`;
  const url = `/api/document#page=${page}`;
  $('#source-frame').src = url; $('#source-external').href = url;
  $('#source-dialog').showModal();
}

function goPage(page) {
  page = Math.min(Math.max(Number(page) || 1, 1), state.stats?.pages || 276);
  $('#pdf-page').value = page;
  $('#document-frame').src = `/api/document#page=${page}&view=FitH`;
}

let graphRequest = 0;
async function loadGraph(concept = '') {
  const request = ++graphRequest;
  try {
    const params = new URLSearchParams();
    if (concept) params.set('concept', concept);
    if (state.chapter) params.set('chapter', state.chapter);
    const graph = await api(`/api/graph?${params}`);
    if (request !== graphRequest) return;
    state.graph = graph;
    renderGraph($('#full-graph'), graph, false, concept);
    if (concept) showConcept(concept, graph);
    else $('#graph-detail').innerHTML = `<span class="eyebrow">${graph.nodes.length} KHÁI NIỆM HIỂN THỊ</span><h2>Chọn một nút<br>trên bản đồ.</h2><p>${state.chapter ? `Đang giới hạn chương ${state.chapter}. ` : ''}Xem trang nguồn và khám phá các khái niệm cùng xuất hiện.</p>`;
  } catch (error) { $('#full-graph').textContent = error.message; }
}

function showConcept(id, graph) {
  const node = graph.nodes.find(n => n.id === id);
  if (!node) return;
  const facts = graph.edges.filter(e => e.relation !== 'co_occurs' && (e.source === id || e.target === id));
  const neighbors = graph.edges.filter(e => e.source === id || e.target === id).map(e => graph.nodes.find(n => n.id === (e.source === id ? e.target : e.source))?.label).filter(Boolean);
  $('#graph-detail').innerHTML = `<span class="eyebrow">KHÁI NIỆM TRONG GIÁO TRÌNH</span><h2>${escapeHTML(node.label)}</h2><p>Xuất hiện trong ${node.mentions} đoạn nguồn${state.chapter ? ` ở chương ${state.chapter}` : ''}.</p><p>Trang PDF có đề cập:</p><div class="page-pills">${node.pages.map(p => `<button data-page="${p}">${p}</button>`).join('')}</div><p>${neighbors.length ? `Cùng xuất hiện với: ${neighbors.slice(0,6).map(escapeHTML).join(', ')}.` : 'Chưa có liên kết trong phạm vi đang chọn.'}</p>${facts.length ? '<div class="fact-relations">' + facts.map(e => `<p><strong>${escapeHTML(graph.nodes.find(n=>n.id===e.source)?.label || '')}</strong> → ${escapeHTML(e.label.toLowerCase())} → <strong>${escapeHTML(graph.nodes.find(n=>n.id===e.target)?.label || '')}</strong><br><button class="citation" data-page="${e.pages[0]}">Trang PDF ${e.pages[0]}</button></p>`).join('') + '</div>' : ''}<button id="ask-concept" class="text-link">Tra cứu khái niệm này ${icon('arrow')}</button>`;
  $$('#graph-detail [data-page]').forEach(button => button.addEventListener('click', () => openSource(Number(button.dataset.page))));
  $('#ask-concept').addEventListener('click', () => { switchTab('search'); $('#question').value = `${node.label} được trình bày như thế nào trong giáo trình?`; submitQuestion(); });
}

function renderGraph(container, graph, mini = false, focus = '') {
  const width = mini ? 270 : 760, height = mini ? 215 : 510;
  const nodes = graph.nodes.slice(0, mini ? 8 : 23).map((n, i, arr) => {
    const centered = n.id === focus;
    const angle = (i / arr.length) * Math.PI * 2 - 1.3;
    const radius = mini ? 69 : 160;
    return {...n, x: centered ? width/2 : width/2 + Math.cos(angle)*radius, y: centered ? height/2 : height/2 + Math.sin(angle)*radius, vx:0, vy:0};
  });
  const byId = new Map(nodes.map(n => [n.id, n]));
  const edges = graph.edges.filter(e => byId.has(e.source) && byId.has(e.target));
  for (let iteration = 0; iteration < 160; iteration++) {
    for (const n of nodes) {
      let fx = (width/2-n.x)*0.008, fy = (height/2-n.y)*0.008;
      for (const other of nodes) {
        if (other === n) continue;
        const dx=n.x-other.x, dy=n.y-other.y, dist=Math.max(15,Math.hypot(dx,dy));
        const force=(mini ? 1100 : 3600)/(dist*dist);
        fx+=dx/dist*force; fy+=dy/dist*force;
      }
      for (const e of edges) {
        const other=e.source===n.id?byId.get(e.target):e.target===n.id?byId.get(e.source):null;
        if (!other) continue;
        const dx=other.x-n.x,dy=other.y-n.y,dist=Math.max(1,Math.hypot(dx,dy));
        const force=(dist-(mini ? 80:135))*0.006;
        fx+=dx/dist*force; fy+=dy/dist*force;
      }
      n.vx=(n.vx+fx)*0.65; n.vy=(n.vy+fy)*0.65;
      if (n.id===focus) {n.x=width/2;n.y=height/2;} else { n.x=Math.min(width-(mini?35:80),Math.max(mini?35:80,n.x+n.vx)); n.y=Math.min(height-32,Math.max(30,n.y+n.vy)); }
    }
  }
  if (!nodes.length) { container.innerHTML = '<p class="empty-result">Không có khái niệm trong phạm vi này.</p>'; return; }
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="group" aria-label="Đồ thị các khái niệm"><g>${edges.map(e => { const a=byId.get(e.source),b=byId.get(e.target); return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${e.relation==='co_occurs'?'#b7c9aa':'#3d7469'}" stroke-width="${e.relation==='co_occurs'?(mini?0.7:1):2}" stroke-dasharray="${e.relation==='co_occurs'?'3 4':'none'}" opacity=".65"><title>${escapeHTML(e.label)} · ${e.weight} đoạn · Trang PDF ${e.pages.join(', ')}</title></line>`; }).join('')}</g>${nodes.map(n => {const selected=n.id===focus; const radius=selected?(mini?11:15):(mini?5:7); return `<g class="graph-node" tabindex="0" role="button" aria-label="${escapeHTML(n.label)}" data-node="${escapeHTML(n.id)}"><circle cx="${n.x}" cy="${n.y}" r="${radius+6}" fill="${selected?'#dfe8d4':'transparent'}"/><circle cx="${n.x}" cy="${n.y}" r="${radius}" fill="${selected?'#55765c':'#94ad88'}"/><text x="${n.x}" y="${n.y+radius+16}" text-anchor="middle" font-size="${mini?8:11}" font-weight="${selected?600:400}">${escapeHTML(n.label)}</text><title>${escapeHTML(n.label)} · ${n.mentions} đoạn nguồn</title></g>`; }).join('')}</svg>`;
  container.querySelectorAll('[data-node]').forEach(element => {
    const action = () => { $('#concept-select').value = element.dataset.node; if (mini) switchTab('graph'); else loadGraph(element.dataset.node); };
    element.addEventListener('click', action);
    element.addEventListener('keydown', event => {if (event.key==='Enter'||event.key===' ') {event.preventDefault(); action();}});
  });
}

$('#search-form').addEventListener('submit', submitQuestion);
$('#question').addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') submitQuestion(event); });
$$('[data-mode]').forEach(button => button.addEventListener('click', () => { state.mode=button.dataset.mode; $$('[data-mode]').forEach(b => {b.classList.toggle('selected',b===button); b.setAttribute('aria-pressed',String(b===button));}); $('#mode-hint').textContent=state.mode==='graph'?'Kết nối nhiều đoạn nguồn':'So sánh không mở rộng graph'; }));
$$('.nav-item').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.tab)));
$$('.suggestion').forEach(button => button.addEventListener('click', () => {$('#question').value=button.dataset.question; submitQuestion();}));
$('#chapter-select').addEventListener('change', event => setChapter(event.target.value));
$('#explore-graph').addEventListener('click', () => switchTab('graph'));
$('#concept-select').addEventListener('change', event => loadGraph(event.target.value));
$('#reset-graph').addEventListener('click', () => {$('#concept-select').value=''; setChapter('');});
$('#go-page').addEventListener('click', () => goPage($('#pdf-page').value));
$('#pdf-page').addEventListener('keydown', event => {if(event.key==='Enter')goPage($('#pdf-page').value);});
$('#cancel-button').addEventListener('click', () => state.controller?.abort());
$('#close-source').addEventListener('click', () => {$('#source-dialog').close();$('#source-frame').removeAttribute('src');});
$('#source-dialog').addEventListener('click', event => {if(event.target===$('#source-dialog'))$('#source-dialog').close();});
$('#menu-button').addEventListener('click', () => {const open=$('#sidebar').classList.toggle('open');$('#sidebar-backdrop').hidden=!open;$('#menu-button').setAttribute('aria-expanded',String(open));});
$('#sidebar-backdrop').addEventListener('click', closeMenu);
document.addEventListener('keydown', event => {if(event.key==='Escape')closeMenu();});
initialize();
