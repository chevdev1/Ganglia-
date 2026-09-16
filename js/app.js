/*
 * app.js: live character state against the Ganglia API
 * Classic script (no modules/build). Files share global scope; load order matters:
 * core.js -> wallet.js -> brain.js -> app.js
 */
const labels=['frontal','parietal','temporal','occipital','cingulate','insula','hippocampus','cerebellum'];
const state={curiosity:7,intensity:4,warmth:6,focus:5,restlessness:4};
const owners=Array.from({length:128},()=>null);
const scenarioCounts=Array.from({length:128},()=>0);
let mine=null, selected=null, connected=false, address='', claimInProgress=false;
let token=localStorage.getItem('ganglia_token')||'';
let lastThoughtId=0;
const seen=new Set();
const grid=document.getElementById('grid'), panel=document.getElementById('panel');
const feed=document.getElementById('feed');
const scn=document.getElementById('scn'), send=document.getElementById('send');
const pad=n=>'#'+String(n).padStart(3,'0');
const short=a=>a&&a.length>12?a.slice(0,6)+'…'+a.slice(-4):a||'';

function renderStates(){
  const keys=['curiosity','intensity','warmth'];
  document.getElementById('states').innerHTML=keys.map(n=>{
    const v=state[n]??0;
    return `<div class="state"><span>${n}</span><div class="meter" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${v}" aria-label="${n}">${Array.from({length:10},(_,i)=>`<b class="${i<v?'on':''}"></b>`).join('')}</div></div>`;
  }).join('');
}

function headers(){
  const h={'Content-Type':'application/json'};
  if(token) h.Authorization='Bearer '+token;
  return h;
}

async function api(path, opts={}){
  const res=await fetch(path,{...opts, headers:{...headers(), ...(opts.headers||{})}});
  const data=await res.json().catch(()=>({detail:res.statusText}));
  if(res.status===401){
    token=''; address=''; connected=false; mine=null; window.myAlias='';
    localStorage.removeItem('ganglia_token');
    localStorage.removeItem('ganglia_address');
    clearSessionKind();
    paintConnect(); lockComposer();
  }
  if(!res.ok){
    const d=data.detail;
    const msg=typeof d==='string'?d: Array.isArray(d)?d.map(x=>x.msg||x).join(' '): (d&&JSON.stringify(d))||res.statusText;
    throw new Error(msg);
  }
  return data;
}

function paintConnect(){
  const b=document.getElementById('connect');
  const leave=document.getElementById('leave');
  const profile=document.getElementById('profile');
  if(connected&&address){
    if(b){ b.hidden=true; b.disabled=false; }
    if(leave) leave.hidden=false;
    if(profile){
      profile.hidden=false;
      profile.textContent=short(address);
      if('href' in profile) profile.href='/me.html';
      profile.title='Open cabinet';
    }
  }else{
    if(b){ b.hidden=false; b.disabled=!!_walletBusy; b.textContent=_walletBusy?'Connecting…':'Enter browser'; b.classList.remove('ghost'); }
    if(leave) leave.hidden=true;
    if(profile) profile.hidden=true;
  }
}

function unlock(){
  if(!scn||!send) return;
  scn.disabled=false;
  send.disabled=!scn.value.trim();
}

function lockComposer(){
  if(!scn||!send) return;
  if(mine!==null){ unlock(); return; }
  scn.disabled=true;
  send.disabled=true;
}

function renderGrid(){
  grid.innerHTML='';
  owners.forEach((o,i)=>{
    const b=document.createElement('button');
    b.className='cell'+(i===mine?' yours':o?' claimed':'')+(i===selected?' sel':'');
    b.setAttribute('aria-label',`Node ${i}, ${i===mine?'yours':o?'claimed':'free'}`);
    b.dataset.i=i; b.onclick=()=>{selected=i;renderGrid();renderPanel();brain.target(i);};
    b.onmouseenter=()=>{ brain.target(i); blip(1400,0.02,0.03); };
    grid.appendChild(b);
  });
  const taken=owners.filter(Boolean).length;
  document.getElementById('count').textContent=`${taken} of 128 claimed`;
}

function renderPanel(){
  if(selected===null){ panel.innerHTML=`<div class="id">—</div><p class="note" style="font-size:14px">Select a node on the map to see who holds it, or claim a free one.</p>`; return; }
  const i=selected,o=owners[i], alias=window.nodeAliases&&window.nodeAliases[i];
  const status=i===mine?'Yours':o?'Claimed':'Free';
  const who=i===mine?(window.myAlias||short(address)): (alias||o||'nobody yet');
  panel.innerHTML=`<div class="id">${pad(i)}</div>
  <dl><dt>Status</dt><dd>${status}</dd><dt>Region</dt><dd>${labels[Math.floor(i/16)]}</dd>  <dt>Owner</dt><dd>${who}</dd><dt>Scenarios</dt><dd>${scenarioCounts[i]||0}</dd></dl>
  ${ i===mine ? `<a class="btn acc" href="/me.html" style="display:block;text-align:center;text-decoration:none;margin-bottom:10px">Open cabinet</a><a class="btn ghost" href="#archive" style="display:block;text-align:center;text-decoration:none">Send a scenario</a>`
    : o ? `<button class="btn ghost" disabled>Already claimed</button>`
    : `<button class="btn" id="claim">${connected?'Claim this node':'Connect wallet to claim'}</button><p class="note">One owner per node, tied to your wallet. Reconnect later and this seat is still yours.</p>`}`;
  const c=document.getElementById('claim'); if(c) c.onclick=()=>{ claimNode(); };
}

function renderClaimProgress(step){
  const labels=['Connecting…','Claiming node…','Node is yours'];
  panel.innerHTML=`<div class="id">${pad(selected)}</div>
  <div class="claimstep">${[0,1,2].map(i=>`<b class="${i<step?'done':i===step?'on':''}"></b>`).join('')}</div>
  <p class="note" style="font-family:var(--px);font-size:14px;margin:10px 0 4px;color:var(--fg)">${labels[Math.min(step,2)]}</p>`;
}

let liveBarInited=false, lastThoughtAt=null;
function relTime(iso){
  if(!iso) return 'no thoughts yet';
  const s=Math.max(0, Math.floor((Date.now()-new Date(iso).getTime())/1000));
  if(s<60) return 'just now';
  const m=Math.floor(s/60); if(m<60) return `${m}m ago`;
  const h=Math.floor(m/60); if(h<24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
}
function renderLiveBar(){
  const claimedEl=document.getElementById('lb-claimed'), scnEl=document.getElementById('lb-scn'), lastEl=document.getElementById('lb-last');
  if(!claimedEl) return;
  const claimed=owners.filter(Boolean).length;
  const totalScn=scenarioCounts.reduce((a,b)=>a+b,0);
  if(!liveBarInited){
    liveBarInited=true;
    claimedEl.textContent='0'; scnEl.textContent='0';
    countUp(claimedEl, claimed, {format:n=>`${n}/128 claimed`});
    countUp(scnEl, totalScn, {format:n=>`${n} scenario${n===1?'':'s'}`});
  }else{
    claimedEl.textContent=`${claimed}/128 claimed`;
    scnEl.textContent=`${totalScn} scenario${totalScn===1?'':'s'}`;
  }
  if(lastEl) lastEl.textContent=relTime(lastThoughtAt);
}
setInterval(()=>{ const lastEl=document.getElementById('lb-last'); if(lastEl&&lastThoughtAt) lastEl.textContent=relTime(lastThoughtAt); }, 15000);

function applyMeters(s){
  if(!s) return;
  state.curiosity=s.curiosity; state.intensity=s.intensity; state.warmth=s.warmth;
  if(s.focus!=null) state.focus=s.focus;
  if(s.restlessness!=null) state.restlessness=s.restlessness;
  renderStates();
}

function applyWorld(data){
  document.getElementById('writer').textContent='writer: '+(data.writer||'software');
  document.getElementById('sig').textContent='signal source: '+(data.signal_source||'software');
  document.getElementById('cycle').textContent=data.cycle;
  document.getElementById('status').textContent=data.busy?data.status:'thinking';
  applyMeters(data.state);
  const warn=document.getElementById('modelwarn');
  if(warn){
    if(data.model_ready===false){
      warn.hidden=false;
      warn.textContent='The mind is offline until OPENAI_API_KEY is set in .env and the server is restarted.';
    }else warn.hidden=true;
  }
  data.nodes.forEach(n=>{ owners[n.id]=n.owner; scenarioCounts[n.id]=n.scenarios; window.nodeAliases=window.nodeAliases||{}; window.nodeAliases[n.id]=n.alias||null; });
  if(data.thoughts&&data.thoughts.length){
    const latest=data.thoughts.reduce((a,b)=> (!a||(b.created_at&&b.created_at>a))?b.created_at:a, null);
    if(latest) lastThoughtAt=latest;
  }
  renderLiveBar();
  if(data.me){
    connected=true; address=data.me.address; mine=data.me.node_id; window.myAlias=data.me.alias||'';
    if(data.me.token){ token=data.me.token; localStorage.setItem('ganglia_token',token); localStorage.setItem('ganglia_address',address); }
    if(!sessionKind()) setSessionKind('local');
    paintConnect();
    if(mine!==null) unlock(); else lockComposer();
  }else if(token){
    token=''; address=''; connected=false; mine=null; window.myAlias='';
    localStorage.removeItem('ganglia_token');
    localStorage.removeItem('ganglia_address');
    clearSessionKind();
    paintConnect(); lockComposer();
  }
  renderGrid();
  if(!claimInProgress) renderPanel();
}

function speak(text){
  if(!window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(text);
  u.lang='en-US'; u.rate=.92; u.pitch=.85;
  speechSynthesis.speak(u);
}

function speakThought(t){
  if(window._gAudio){ window._gAudio.pause(); window._gAudio=null; }
  if(window.speechSynthesis) speechSynthesis.cancel();
  if(t.voice_url){
    const audio=new Audio(t.voice_url);
    window._gAudio=audio;
    audio.play().catch(()=>speak(t.text));
    return;
  }
  speak(t.text);
}

function deltaChip(label, cur, prevVal){
  if(prevVal==null||cur==null) return '';
  const d=cur-prevVal;
  if(!d) return '';
  return `<span class="tag${d>0?' acc':''}">${label} ${d>0?'+':''}${d}</span>`;
}

function renderThought(t, animate, prev){
  if(seen.has(t.id)) return;
  seen.add(t.id);
  lastThoughtId=Math.max(lastThoughtId,t.id);
  const el=document.createElement('article'); el.className='thought'; el.id='t'+t.id;
  el.dataset.trigger=t.trigger||'autonomous';
  if(t.node_id!==null&&t.node_id!==undefined) el.dataset.node=String(t.node_id);
  const tag=t.trigger==='scenario'?`<span class="tag acc">scenario</span>`: t.trigger==='claim'?`<span class="tag acc">claim</span>`:`<span class="tag">autonomous</span>`;
  const when=t.created_at?new Date(t.created_at).toTimeString().slice(0,5):'';
  const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
  const deltas=prev?[deltaChip('curiosity',t.curiosity,prev.curiosity),deltaChip('intensity',t.intensity,prev.intensity),deltaChip('warmth',t.warmth,prev.warmth)].join(''):'';
  el.innerHTML=`<div class="meta">${tag}${t.node_id!==null&&t.node_id!==undefined?`<span class="tag">node ${pad(t.node_id)}</span>`:''}<span>${when}</span><span>signal: ${esc(t.signal_source||'software')}</span><span>writer: ${esc(t.writer||'software')}</span><button type="button" class="speak" data-speak="1">speak</button><button type="button" class="speak" data-copy="1">copy link</button></div>
   ${t.scenario?`<div class="scn">${esc(t.scenario)}</div>`:''}<p class="${animate?'caret':''}"></p>
   <div class="thought-state">curiosity ${t.curiosity} · intensity ${t.intensity} · warmth ${t.warmth} · spikes ${t.spike_count}${deltas?' '+deltas:''}</div>`;
  const p=el.querySelector('p');
  feed.prepend(el);
  el.querySelector('.speak[data-speak]').onclick=()=>speakThought(t);
  const copyBtn=el.querySelector('.speak[data-copy]');
  copyBtn.onclick=()=>{
    const url=location.href.split('#')[0]+'#t'+t.id;
    navigator.clipboard?.writeText(url).catch(()=>{});
    const orig=copyBtn.textContent; copyBtn.textContent='copied';
    setTimeout(()=>{ copyBtn.textContent=orig; },1200);
  };
  if(!animate||reduce){ p.textContent=t.text; p.classList.remove('caret'); return; }
  document.getElementById('status').textContent='writing';
  let i=0;
  const tick=setInterval(()=>{ p.textContent=t.text.slice(0,++i); if(i>=t.text.length){ p.classList.remove('caret'); clearInterval(tick); document.getElementById('status').textContent='thinking'; } }, 18);
}

let lastMeters=null;
function ingestThoughts(list, animate){
  const fresh=[...list].sort((a,b)=>a.id-b.id).filter(t=>!seen.has(t.id));
  fresh.forEach(t=>{
    renderThought(t, animate, lastMeters);
    lastMeters={curiosity:t.curiosity, intensity:t.intensity, warmth:t.warmth};
    applyMeters(t);
    if(t.node_id!==null&&t.node_id!==undefined){
      if(t.trigger==='scenario'||t.trigger==='claim'){ brain.target(t.node_id, true); const cell=grid.children[t.node_id]; if(cell){ cell.classList.remove('pulse'); void cell.offsetWidth; cell.classList.add('pulse'); } }
    } else if(animate) brain.ripple();
  });
  if(fresh.length) applyFeedFilter();
}

let feedFilter='all';
function applyFeedFilter(){
  [...feed.children].forEach(el=>{
    let show=true;
    if(feedFilter==='scenario') show=el.dataset.trigger==='scenario';
    else if(feedFilter==='autonomous') show=el.dataset.trigger!=='scenario'&&el.dataset.trigger!=='claim';
    else if(feedFilter==='mine') show=mine!==null&&el.dataset.node===String(mine);
    el.hidden=!show;
  });
}
document.querySelectorAll('#feedfilters .chip').forEach(btn=>{
  btn.onclick=()=>{
    feedFilter=btn.dataset.filter;
    document.querySelectorAll('#feedfilters .chip').forEach(b=>b.classList.toggle('active', b===btn));
    applyFeedFilter();
  };
});

async function loadState(animateNew){
  const data=await api('/api/state');
  applyWorld(data);
  ingestThoughts(data.thoughts, !!animateNew);
}

async function burst(){
  for(let n=0;n<20;n++){
    await new Promise(r=>setTimeout(r,250));
    try{ await loadState(true); }catch(_e){}
  }
}

async function connect(openCabinet){
  showErr('');
  if(_walletBusy) return;
  let choice;
  try{
    choice=await pickWallet();
  }catch(err){
    showErr(err.message);
    return;
  }
  if(!choice){ showErr(''); paintConnect(); return; }
  setConnectBusy(true);
  try{
    const me=await loginWithChoice(api, choice);
    if(!me) return;
    token=me.token; address=me.address; mine=me.node_id; connected=true;
    localStorage.setItem('ganglia_token',token);
    localStorage.setItem('ganglia_address',address);
    paintConnect();
    if(mine!==null) unlock();
    renderPanel();
    await loadState(true);
    if(openCabinet) openSeat();
  }catch(err){
    showErr(err.message);
  }finally{
    setConnectBusy(false);
    paintConnect();
  }
}

async function disconnect(){
  try{ if(token) await api('/api/auth/logout',{method:'POST', body:'{}'}); }catch(_e){}
  token=''; address=''; connected=false; mine=null;
  localStorage.removeItem('ganglia_token');
  localStorage.removeItem('ganglia_address');
  clearSessionKind();
  showErr('');
  paintConnect(); lockComposer(); renderGrid(); renderPanel();
}

async function claimNode(){
  showErr('');
  const i=selected;
  claimInProgress=true;
  try{
    renderClaimProgress(connected?1:0);
    if(!connected) await connect(false);
    renderClaimProgress(1);
    await api('/api/nodes/'+i+'/claim',{method:'POST', body:'{}'});
    mine=i; unlock();
    renderClaimProgress(2);
    blip(500,0.1,0.07); setTimeout(()=>blip(900,0.08,0.06),90);
    await loadState(true);
    burst();
    brain.target(i,true);
    claimInProgress=false;
    renderPanel();
    showShareCard(i);
  }catch(err){
    claimInProgress=false;
    showErr(err.message);
    renderPanel();
  }
}

scn.oninput=()=>{ document.getElementById('chars').textContent=`${scn.value.length} / 280`; send.disabled=!scn.value.trim()||mine===null; };

send.onclick=async()=>{
  const v=scn.value.trim(); if(!v||mine===null) return;
  showErr('');
  scn.value=''; scn.oninput(); send.disabled=true;
  brain.target(mine,true);
  const cell=grid.children[mine]; if(cell){ cell.classList.remove('pulse'); void cell.offsetWidth; cell.classList.add('pulse'); }
  document.getElementById('status').textContent='reading your scenario';
  try{
    await api('/api/scenarios',{method:'POST', body:JSON.stringify({text:v})});
    blip(700,0.05,0.05);
    burst();
  }catch(err){
    showErr(err.message);
    send.disabled=false;
    document.getElementById('status').textContent='thinking';
  }
};

document.getElementById('connect').onclick=()=>{
  connect(false).catch(err=>showErr(err.message));
};
const leaveBtn=document.getElementById('leave');
if(leaveBtn) leaveBtn.onclick=()=>disconnect().catch(err=>showErr(err.message));
bindAccountWatch(()=>address, ()=>{
  disconnect();
});

document.getElementById('theme').onclick=()=>{
  themeWipe(()=>{
    const r=document.documentElement; const dark = r.dataset.theme ? r.dataset.theme==='dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    r.dataset.theme = dark?'light':'dark'; drawLogo(); renderStates(); brain.colors();
  });
};

/* sound: off by default, WebAudio blips on interaction, ~short */
let audioCtx=null, soundOn=localStorage.getItem('ganglia_sound')==='1';
function updateSoundBtn(){ const b=document.getElementById('sound'); if(b) b.setAttribute('aria-pressed', String(soundOn)); }
function blip(freq=880, dur=0.05, vol=0.05){
  if(!soundOn) return;
  try{
    audioCtx=audioCtx||new (window.AudioContext||window.webkitAudioContext)();
    const o=audioCtx.createOscillator(), g=audioCtx.createGain();
    o.type='square'; o.frequency.value=freq; g.gain.value=vol;
    o.connect(g); g.connect(audioCtx.destination);
    o.start();
    g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime+dur);
    o.stop(audioCtx.currentTime+dur);
  }catch(_e){}
}
const soundBtn=document.getElementById('sound');
if(soundBtn) soundBtn.onclick=()=>{
  soundOn=!soundOn;
  localStorage.setItem('ganglia_sound', soundOn?'1':'0');
  updateSoundBtn();
  if(soundOn) blip(880,0.06,0.06);
};
updateSoundBtn();

function seededRandom(seed){
  let s=(seed%2147483647)||1; if(s<=0) s+=2147483646;
  return ()=>{ s=(s*16807)%2147483647; return (s-1)/2147483646; };
}

function drawShareCard(nodeId){
  const cv=document.getElementById('sharecanvas');
  if(!cv) return;
  const ctx=cv.getContext('2d');
  const W=cv.width, H=cv.height;
  const bg=css('--bg'), fg=css('--fg'), acc=css('--acc'), dim=css('--dim'), cell=css('--cell');
  ctx.fillStyle=bg; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle=dim; ctx.lineWidth=2; ctx.strokeRect(20,20,W-40,H-40);

  ctx.textBaseline='top';
  ctx.fillStyle=fg;
  ctx.font='700 40px Silkscreen, monospace';
  ctx.fillText('GANGLIA', 60, 58);
  ctx.fillStyle=dim;
  ctx.font='16px "Geist Mono", monospace';
  ctx.fillText('one mind. 128 nodes.', 60, 108);

  ctx.fillStyle=acc;
  ctx.font='700 140px Silkscreen, monospace';
  ctx.fillText(pad(nodeId), 60, 210);

  ctx.fillStyle=dim;
  ctx.font='20px "Geist Mono", monospace';
  ctx.fillText('region: '+(labels[Math.floor(nodeId/16)]||''), 60, 400);
  ctx.fillText('node holder since '+new Date().toISOString().slice(0,10), 60, 430);

  const rnd=seededRandom(nodeId+1);
  const N=5, size=26, ox=W-60-N*size, oy=60;
  for(let y=0;y<N;y++){
    for(let x=0;x<Math.ceil(N/2);x++){
      const on=rnd()>0.55;
      ctx.fillStyle=on?acc:cell;
      ctx.fillRect(ox+x*size, oy+y*size, size-2, size-2);
      const mx=N-1-x;
      if(mx!==x) ctx.fillRect(ox+mx*size, oy+y*size, size-2, size-2);
    }
  }
}

function showShareCard(nodeId){
  const sheet=document.getElementById('sharesheet');
  if(!sheet) return;
  drawShareCard(nodeId);
  sheet.hidden=false;
  const dl=document.getElementById('sharedownload');
  if(dl) dl.onclick=()=>{
    const cv=document.getElementById('sharecanvas');
    const a=document.createElement('a');
    a.href=cv.toDataURL('image/png');
    a.download='ganglia-node-'+String(nodeId).padStart(3,'0')+'.png';
    a.click();
  };
  const post=document.getElementById('sharepost');
  if(post){
    const text=encodeURIComponent(`I hold node ${pad(nodeId)} of Ganglia — one shared mind, 128 people.`);
    const url=encodeURIComponent(location.origin+location.pathname);
    post.href=`https://twitter.com/intent/tweet?text=${text}&url=${url}`;
  }
  const close=()=>{ sheet.hidden=true; };
  const x=document.getElementById('sharex'); if(x) x.onclick=close;
  sheet.onclick=e=>{ if(e.target===sheet) close(); };
}

setInterval(()=>{ loadState(true).catch(()=>{}); }, 3000);

drawLogo(); renderStates(); renderGrid(); selected=null; renderPanel(); paintConnect();
brain.start(); window.brain=brain;
if(location.protocol==='file:'){
  showErr('Open the app through the Ganglia server (uvicorn), not as a local file.');
}else{
  loadState(false).catch(err=>showErr(err.message||'Could not reach the Ganglia server. Run it with uvicorn.'));
}
