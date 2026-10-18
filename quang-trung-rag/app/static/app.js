'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const state = {tab:'search', mode:'graph', category:null, stats:null, records:[], documents:[], entities:[], timeline:[], busy:false, controller:null};
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const fold = value => String(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d');
const safeURL = url => { try {const value=new URL(url,location.origin);return ['http:','https:'].includes(value.protocol)?value.href:'#';}catch{return '#';} };
const kinds = {person:'Nhân vật', place:'Địa điểm', force:'Lực lượng', event:'Sự kiện', tactic:'Chiến thuật'};
const colors = {person:'#9b503f', place:'#a1884c', force:'#657a67', event:'#85718a', tactic:'#9b805e'};

async function api(path,options={}) {
  const response=await fetch(path,options);
  if(!response.ok){let message='Không kết nối được máy chủ.';try{const d=await response.json();if(typeof d.detail==='string')message=d.detail;}catch{}throw new Error(message);}
  return response.json();
}
function showError(message){$('#app-error').textContent=message;$('#app-error').hidden=!message;}
function closeMenu(){$('#sidebar').classList.remove('open');$('#sidebar-backdrop').hidden=true;$('#menu-button').setAttribute('aria-expanded','false');}
function setCategory(value){state.category=value||null;$('#category-select').value=value||'';$$('[data-category]').forEach(b=>b.classList.toggle('active',b.dataset.category===(value||'')));}
function switchTab(tab){state.tab=tab;for(const name of ['search','graph','timeline','documents'])$(`#${name}-view`).hidden=name!==tab;$$('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);if(b.dataset.tab===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});closeMenu();if(tab==='graph')loadGraph($('#entity-select').value);if(tab==='timeline')renderTimeline();if(tab==='documents')renderLibrary();}

async function initialize(){
  try{
    const [stats,entities,documents,records,timeline]=await Promise.all([api('/api/stats'),api('/api/entities'),api('/api/documents'),api('/api/records'),api('/api/timeline')]);
    Object.assign(state,{stats,entities,documents,records,timeline});
    $('#stat-sources').textContent=stats.sources;$('#stat-records').textContent=stats.records;$('#stat-entities').textContent=stats.entities;
    $('#category-nav').innerHTML=`<button class="chapter-button active" data-category=""><span class="chapter-number">↳</span><span>Toàn bộ hồ sơ</span></button>`+stats.categories.map((c,i)=>`<button class="chapter-button" data-category="${esc(c.id)}"><span class="chapter-number">${String(i+1).padStart(2,'0')}</span><span>${esc(c.title)}</span></button>`).join('');
    $('#category-select').innerHTML+=stats.categories.map(c=>`<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('');
    $('#entity-select').innerHTML+=entities.map(e=>`<option value="${esc(e.id)}">${esc(e.label)} · ${kinds[e.kind]}</option>`).join('');
    $('#entity-select').value='quang-trung';
    $('#document-select').innerHTML+=documents.map(d=>`<option value="${esc(d.id)}">${esc(d.title)}</option>`).join('');
    $$('[data-category]').forEach(b=>b.addEventListener('click',()=>{setCategory(b.dataset.category);switchTab('search');}));
    const graph=await api('/api/graph?entity=quang-trung');renderGraph($('#mini-graph'),graph,true,'quang-trung');
  }catch(error){showError(error.message);}
  checkModels();
}
async function checkModels(){try{const d=await api('/api/models');$('#model-dot').classList.toggle('ready',d.chat_ready);$('#model-label').textContent=d.chat_ready?`Ollama · ${d.chat_model}`:d.connected?'Ollama · cần tải mô hình':'Ollama chưa khởi động';}catch{$('#model-label').textContent='Chưa kết nối máy chủ';}}

function setBusy(value){state.busy=value;$('#loading').hidden=!value;$('#submit-button').disabled=value;$('#submit-button').innerHTML=value?`Đang tra cứu ${icon('search')}`:`Tra cứu ${icon('arrow')}`;$('#search-form').setAttribute('aria-busy',String(value));}
async function submitQuestion(event){
  event?.preventDefault();if(state.busy)return;
  const question=$('#question').value.trim();if(question.length<3){$('#question').focus();return;}
  showError('');setBusy(true);$('#results').hidden=true;state.controller=new AbortController();
  const llm=$('#use-llm').checked;
  $('#loading-detail').textContent=llm?'Ollama đang đọc các ghi chép phù hợp. Lần đầu cần nạp mô hình.':'Đối chiếu nội dung và các thực thể liên quan.';
  const timer=setTimeout(()=>{$('#loading-detail').textContent='Mô hình đang xử lý trên CPU. Có thể hủy và tắt tổng hợp để tra cứu nguồn nhanh.';},18000);
  try{
    const data=await api(llm?'/api/ask':'/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,mode:state.mode,category:state.category,limit:6}),signal:state.controller.signal});
    renderResults(data);$('#results').hidden=false;$('#suggestions').hidden=true;
    if(innerWidth<701)$('#results').scrollIntoView({behavior:'smooth',block:'start'});
    if(data.concepts?.length){const graph=await api(`/api/graph?entity=${encodeURIComponent(data.concepts[0])}`);renderGraph($('#mini-graph'),graph,true,data.concepts[0]);}
  }catch(error){if(error.name!=='AbortError')showError(error.message);}
  finally{clearTimeout(timer);setBusy(false);state.controller=null;}
}
function formatAnswer(text,sources){return esc(text).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\[(\d+)\]/g,(m,n)=>sources.some(s=>s.citation===Number(n))?`<button class="citation" data-citation="${n}" aria-label="Xem nguồn ${n}">[${n}]</button>`:m);}
function renderResults(data){
  const sources=data.sources||[];
  if(!sources.length){$('#results').innerHTML='<div class="empty-result">Chưa có bằng chứng phù hợp trong hồ sơ này.<br>Thử nêu rõ nhân vật, địa điểm hoặc chọn “Toàn bộ hồ sơ”.</div>';return;}
  const elapsed=data.elapsed_ms<1000?`${data.elapsed_ms} ms`:`${(data.elapsed_ms/1000).toFixed(1)} giây`;
  let html=`<div class="result-meta"><strong>Kết quả tra cứu</strong><span class="method-badge">${data.mode==='graph'?'RAG + Graph':'RAG cơ bản'}</span><span>${sources.length} ghi chép · ${elapsed}</span></div>`;
  if(data.warnings?.length)html+=`<div class="notice">${data.warnings.map(esc).join('<br>')}</div>`;
  if(data.answer){const generated=data.answer_mode==='generated';html+=`<div class="answer-card"><div class="answer-heading">${icon(generated?'spark':'book')}${generated?'Giải thích từ hồ sơ':'Ghi chép liên quan'}</div>${data.generation_warning?`<div class="notice">${esc(data.generation_warning)}</div>`:''}<div class="answer-content">${formatAnswer(data.answer,sources)}</div><div class="answer-footnote">${generated?`Tổng hợp bởi ${esc(data.model)} · Nhấn số nguồn để đối chiếu.`:'Nội dung ghi chép biên soạn có nguồn; chưa phải phần tổng hợp bằng AI.'}</div></div>`;}
  html+='<h2 class="sources-heading">GHI CHÉP VÀ TÀI LIỆU ĐỐI CHIẾU</h2>';
  html+=sources.map(s=>`<article class="source-card" id="source-${s.citation}"><div class="source-heading"><span class="source-index">${s.citation}</span><div><h3>${esc(s.title)}</h3><small>${esc(s.publisher)} · ${esc(s.category_title)}</small></div></div><p class="source-text" id="text-${s.citation}">${esc(s.text)}</p><div class="source-actions"><button data-record="${esc(s.id)}">Đọc ghi chép ${icon('book')}</button><a class="text-link" href="${esc(safeURL(s.source_url))}" target="_blank" rel="noopener">Bài gốc ${icon('external')}</a><span class="source-score" title="Điểm xếp hạng tương đối, không phải xác suất lịch sử đúng">Điểm ${s.score.toFixed(3)}</span></div>${s.via?.length?`<div class="source-via">${s.graph_expanded?'Mở rộng qua graph':'Thực thể liên quan'}: ${s.via.map(esc).join(' · ')}</div>`:''}</article>`).join('');
  html+=`<div class="result-meta"><span>Truy xuất: ${esc(data.backend)}${data.mode==='graph'?` · ${data.graph_added} ghi chép bổ sung qua graph`:''}</span></div>`;
  $('#results').innerHTML=html;bindRecordButtons($('#results'));
  $$('#results [data-citation]').forEach(b=>b.addEventListener('click',()=>$(`#source-${b.dataset.citation}`).scrollIntoView({behavior:'smooth',block:'center'})));
}
function bindRecordButtons(container){container.querySelectorAll('[data-record]').forEach(b=>b.addEventListener('click',()=>openRecord(b.dataset.record)));}
async function openRecord(id){
  try{const r=await api(`/api/records/${encodeURIComponent(id)}`);$('#source-title').textContent=r.title;$('#source-body').innerHTML=`<div class="source-meta">${esc(r.source.publisher)}${r.source.published_at?` · Bài gốc: ${esc(r.source.published_at)}`:''}<br>Ghi chép biên soạn · Đối chiếu ${esc(state.stats?.compiled_at||'')}</div><p>${esc(r.text)}</p><div class="notice">${esc(r.source.note)}</div><div class="eyebrow">ĐỌC TOÀN VĂN NGUỒN THAM KHẢO</div><a href="${esc(safeURL(r.source.url))}" target="_blank" rel="noopener">${esc(r.source.title)} ↗</a>`;$('#source-dialog').showModal();}catch(error){showError(error.message);}
}

function renderTimeline(){
  $('#timeline-list').innerHTML=state.timeline.map((event,i)=>`<article class="timeline-item"><div class="timeline-date">${esc(event.date_label)}${event.lunar?`<small>${esc(event.lunar)}</small>`:''}</div><div class="timeline-card"><div class="eyebrow">MỐC ${String(i+1).padStart(2,'0')}${event.gregorian?' · NGÀY DƯƠNG LỊCH THEO NGUỒN':''}</div><h2>${esc(event.title)}</h2><p>${event.record_ids.map(id=>state.records.find(r=>r.id===id)?.text||'').map(esc).join(' ')}</p><div class="timeline-records">${event.record_ids.map(id=>`<button data-record="${esc(id)}">Xem ghi chép ${icon('external')}</button>`).join('')}</div></div></article>`).join('');bindRecordButtons($('#timeline-list'));
}
function renderLibrary(){
  const sourceId=$('#document-select').value;const query=fold($('#document-query').value);
  const docs=state.documents.filter(d=>!sourceId||d.id===sourceId);
  $('#source-collection').innerHTML=docs.map(d=>`<article class="library-source"><span class="eyebrow">${esc(d.publisher)}</span><h2>${esc(d.title)}</h2><p>${esc(d.note)}</p><div class="library-actions"><a href="${esc(safeURL(d.url))}" target="_blank" rel="noopener">Đọc bài gốc ↗</a><a href="/api/documents/${encodeURIComponent(d.id)}/download">Tải ghi chép ↓</a><button data-library-source="${esc(d.id)}">Lọc ghi chép</button></div></article>`).join('');
  const records=state.records.filter(r=>(!sourceId||r.source_id===sourceId)&&(!query||fold(`${r.title} ${r.text}`).includes(query)));
  $('#record-count').textContent=`${records.length} ghi chép`;
  $('#record-list').innerHTML=records.length?records.map(r=>`<article class="record-item"><h3>${esc(r.title)}</h3><p>${esc(r.text)}</p><small>${esc(r.publisher)}</small><button class="text-link" data-record="${esc(r.id)}">Đối chiếu nguồn ${icon('arrow')}</button></article>`).join(''):'<div class="empty-result">Không có ghi chép khớp bộ lọc.</div>';
  bindRecordButtons($('#record-list'));$$('[data-library-source]').forEach(b=>b.addEventListener('click',()=>{$('#document-select').value=b.dataset.librarySource;renderLibrary();}));
}

let graphRequest=0;
async function loadGraph(entity=''){
  const request=++graphRequest;const params=new URLSearchParams();if(entity)params.set('entity',entity);if(state.category)params.set('category',state.category);
  try{const graph=await api(`/api/graph?${params}`);if(request!==graphRequest)return;renderGraph($('#full-graph'),graph,false,entity);showEntity(entity,graph);}catch(error){$('#full-graph').textContent=error.message;}
}
function showEntity(id,graph){
  const node=graph.nodes.find(n=>n.id===id);
  if(!node){$('#graph-detail').innerHTML=`<span class="eyebrow">${graph.nodes.length} THỰC THỂ</span><h2>Chọn một nút<br>để lần theo dấu sử.</h2><p>Các mũi tên có thể được kiểm chứng bằng ghi chép tương ứng.</p>`;return;}
  const relations=graph.edges.filter(e=>e.relation!=='co_occurs'&&(e.source===id||e.target===id));
  const name=key=>graph.nodes.find(n=>n.id===key)?.label||key;
  $('#graph-detail').innerHTML=`<span class="eyebrow">${kinds[node.kind]}</span><h2>${esc(node.label)}</h2><p>Có trong ${node.mentions} ghi chép.</p>${relations.map(e=>`<div class="graph-relation"><strong>${esc(name(e.source))}</strong><br>→ ${esc(e.label.toLowerCase())} →<br><strong>${esc(name(e.target))}</strong><br>${e.evidence.map(rid=>`<button data-record="${esc(rid)}">Đối chiếu bằng chứng ↗</button>`).join('')}</div>`).join('')}<button class="text-link" id="ask-entity">Tra cứu thực thể này ${icon('arrow')}</button>`;
  bindRecordButtons($('#graph-detail'));$('#ask-entity').addEventListener('click',()=>{switchTab('search');$('#question').value=`${node.label} có vai trò gì trong chiến dịch năm 1789?`;submitQuestion();});
}

function renderGraph(container,graph,mini=false,focus=''){
  const width=mini?270:760,height=mini?215:510;
  const nodes=graph.nodes.slice(0,mini?8:24).map((n,i,all)=>{const angle=i/all.length*Math.PI*2-1.3;return {...n,x:n.id===focus?width/2:width/2+Math.cos(angle)*(mini?70:160),y:n.id===focus?height/2:height/2+Math.sin(angle)*(mini?70:160),vx:0,vy:0};});
  const byId=new Map(nodes.map(n=>[n.id,n]));const edges=graph.edges.filter(e=>byId.has(e.source)&&byId.has(e.target));
  for(let iteration=0;iteration<150;iteration++)for(const n of nodes){let fx=(width/2-n.x)*.008,fy=(height/2-n.y)*.008;for(const other of nodes){if(other===n)continue;const dx=n.x-other.x,dy=n.y-other.y,d=Math.max(15,Math.hypot(dx,dy)),force=(mini?1100:3600)/(d*d);fx+=dx/d*force;fy+=dy/d*force;}for(const e of edges){const other=e.source===n.id?byId.get(e.target):e.target===n.id?byId.get(e.source):null;if(!other)continue;const dx=other.x-n.x,dy=other.y-n.y,d=Math.max(1,Math.hypot(dx,dy)),force=(d-(mini?80:135))*.006;fx+=dx/d*force;fy+=dy/d*force;}n.vx=(n.vx+fx)*.65;n.vy=(n.vy+fy)*.65;if(n.id===focus){n.x=width/2;n.y=height/2;}else{n.x=Math.min(width-(mini?35:85),Math.max(mini?35:85,n.x+n.vx));n.y=Math.min(height-35,Math.max(30,n.y+n.vy));}}
  if(!nodes.length){container.innerHTML='<p class="empty-result">Không có thực thể trong phạm vi đang chọn.</p>';return;}
  const marker=mini?'mini-arrow':'full-arrow';
  container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="group" aria-label="Đồ thị lịch sử"><defs><marker id="${marker}" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 6 3 0 6Z" fill="#aa8259"/></marker></defs>${edges.map(e=>{const a=byId.get(e.source),b=byId.get(e.target),dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),r=b.id===focus?(mini?14:19):11;return `<line x1="${a.x}" y1="${a.y}" x2="${b.x-dx/d*r}" y2="${b.y-dy/d*r}" stroke="${e.relation==='co_occurs'?'#c7b69a':'#a58158'}" stroke-width="${e.relation==='co_occurs'?.7:1.2}" stroke-dasharray="${e.relation==='co_occurs'?'3 5':'none'}" ${e.relation==='co_occurs'?'':`marker-end="url(#${marker})"`} opacity=".65"><title>${esc(e.label)}</title></line>`;}).join('')}${nodes.map(n=>{const chosen=n.id===focus,r=chosen?(mini?10:14):(mini?5:7);return `<g class="graph-node" tabindex="0" role="button" aria-label="${esc(n.label)}" data-node="${esc(n.id)}"><circle cx="${n.x}" cy="${n.y}" r="${r+6}" fill="${chosen?'#eee1cb':'transparent'}"/><circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${colors[n.kind]}"/><text x="${n.x}" y="${n.y+r+16}" text-anchor="middle" font-size="${mini?8:11}" font-weight="${chosen?600:400}">${esc(n.label)}</text><title>${esc(n.label)} · ${kinds[n.kind]}</title></g>`;}).join('')}</svg>`;
  container.querySelectorAll('[data-node]').forEach(el=>{const action=()=>{$('#entity-select').value=el.dataset.node;if(mini)switchTab('graph');else loadGraph(el.dataset.node);};el.addEventListener('click',action);el.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();action();}});});
}

$('#search-form').addEventListener('submit',submitQuestion);$('#question').addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter')submitQuestion(event);});
$$('[data-mode]').forEach(b=>b.addEventListener('click',()=>{state.mode=b.dataset.mode;$$('[data-mode]').forEach(item=>{item.classList.toggle('selected',item===b);item.setAttribute('aria-pressed',String(item===b));});$('#mode-hint').textContent=state.mode==='graph'?'Kết nối các ghi chép':'Không mở rộng graph';}));
$$('[data-tab]').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));$$('[data-question]').forEach(b=>b.addEventListener('click',()=>{$('#question').value=b.dataset.question;submitQuestion();}));
$('#category-select').addEventListener('change',event=>setCategory(event.target.value));$('#explore-graph').addEventListener('click',()=>switchTab('graph'));$('#entity-select').addEventListener('change',event=>loadGraph(event.target.value));$('#reset-graph').addEventListener('click',()=>{setCategory('');$('#entity-select').value='';loadGraph();});
$('#document-select').addEventListener('change',renderLibrary);$('#document-query').addEventListener('input',renderLibrary);$('#cancel-button').addEventListener('click',()=>state.controller?.abort());$('#close-source').addEventListener('click',()=>$('#source-dialog').close());$('#source-dialog').addEventListener('click',event=>{if(event.target===$('#source-dialog'))$('#source-dialog').close();});
$('#menu-button').addEventListener('click',()=>{const open=$('#sidebar').classList.toggle('open');$('#sidebar-backdrop').hidden=!open;$('#menu-button').setAttribute('aria-expanded',String(open));});$('#sidebar-backdrop').addEventListener('click',closeMenu);document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
initialize();
