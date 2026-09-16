/*
 * chamber.js: lean personal cabinet. core.js + wallet.js first.
 */
const REGIONS=['frontal','parietal','temporal','occipital','cingulate','insula','hippocampus','cerebellum'];
const MYTH={
  frontal:['the asking edge','Questions arrive here first.'],
  parietal:['the map of touch','Shape without names.'],
  temporal:['the shore of names','Sound and story pool here.'],
  occipital:['the light well','Pictures collect here.'],
  cingulate:['the inner seam','Two feelings can sit at once.'],
  insula:['the hidden weather','Mood shifts before the room notices.'],
  hippocampus:['the room of returns','What you sent comes back thinner.'],
  cerebellum:['the quiet timing','Rhythm without speech.']
};
const pad=n=>'#'+String(n).padStart(3,'0');
const short=a=>a&&a.length>12?a.slice(0,6)+'…'+a.slice(-4):a||'';
const emptySigil=()=>Array.from({length:8},()=>Array(8).fill(0));
let token=localStorage.getItem('ganglia_token')||'';
let address=localStorage.getItem('ganglia_address')||'';
let connected=!!token;
let mine=null;
let occupancy=Array(128).fill(false);
let selected=null;
let chamber=null;

function errEl(){
  return document.getElementById('err')||document.getElementById('errguest');
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
    token=''; address=''; connected=false; mine=null; chamber=null;
    localStorage.removeItem('ganglia_token');
    localStorage.removeItem('ganglia_address');
    clearSessionKind();
    paintConnect();
  }
  if(!res.ok){
    const d=data.detail;
    const msg=typeof d==='string'?d: Array.isArray(d)?d.map(x=>x.msg||x).join(' '):(d&&JSON.stringify(d))||res.statusText;
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
    }
  }else{
    if(b){ b.hidden=false; b.disabled=!!_walletBusy; b.textContent=_walletBusy?'Connecting…':'Enter browser'; b.classList.remove('ghost'); }
    if(leave) leave.hidden=true;
    if(profile) profile.hidden=true;
  }
}

function drawSigil(grid){
  const cv=document.getElementById('sigil');
  if(!cv) return;
  const g=cv.getContext('2d');
  const acc=css('--acc')||'#4D7CFF', cell=css('--cell')||'#161616';
  const mark=grid&&grid.length?grid:emptySigil();
  for(let y=0;y<8;y++) for(let x=0;x<8;x++){
    g.fillStyle=mark[y][x] ? acc : cell;
    g.fillRect(x,y,1,1);
  }
}

function setMode(mode){
  document.getElementById('guestsec').hidden = mode!=='guest';
  document.getElementById('claimsec').hidden = mode!=='doorway';
  document.getElementById('roomsec').hidden = mode!=='seated';
}

function renderCta(mode){
  const cta=document.getElementById('cta');
  if(mode==='doorway'){
    cta.innerHTML='<button class="btn acc" id="ctafree">Take a free seat</button>';
    document.getElementById('ctafree').onclick=()=>takeFree().catch(e=>showErr(e.message));
  }else if(mode==='seated'){
    cta.innerHTML='<a class="btn ghost" href="/index.html#archive" style="text-decoration:none">Public archive</a><button class="btn ghost" id="ctaleave">Leave</button>';
    document.getElementById('ctaleave').onclick=()=>disconnect().catch(e=>showErr(e.message));
  }else{
    cta.innerHTML='';
  }
}

function firstFree(){
  const i=occupancy.findIndex(taken=>!taken);
  return i<0?null:i;
}

function renderGrid(){
  const grid=document.getElementById('seatgrid');
  if(!grid) return;
  grid.innerHTML='';
  occupancy.forEach((taken,i)=>{
    if(taken && i!==mine) return;
    const b=document.createElement('button');
    b.type='button';
    b.className='cell'+(i===mine?' yours':taken?' claimed':'')+(i===selected?' sel':'');
    b.title=pad(i)+' · '+REGIONS[Math.floor(i/16)];
    b.onclick=()=>{selected=i; renderGrid();};
    if(!taken) grid.appendChild(b);
  });
  if(!grid.children.length){
    grid.innerHTML='<p class="sub">No free seats left.</p>';
  }
}

function renderTraces(traces){
  const el=document.getElementById('traces');
  if(!el) return;
  el.innerHTML='';
  if(!traces||!traces.length){
    el.innerHTML='<p class="sub">Nothing yet. Send a scenario — the mind answers here.</p>';
    return;
  }
  traces.forEach(t=>{
    const card=document.createElement('article'); card.className='thought';
    const when=t.created_at?new Date(t.created_at).toTimeString().slice(0,5):'';
    card.innerHTML=`<div class="meta"><span class="tag acc">${t.trigger}</span><span>${when}</span><span class="tag">${t.writer||'?'}</span><button type="button" class="speak">speak</button></div>
      ${t.scenario?`<div class="scn"></div>`:''}<p></p>`;
    if(t.scenario) card.querySelector('.scn').textContent=t.scenario;
    card.querySelector('p').textContent=t.text;
    card.querySelector('.speak').onclick=()=>speakTrace(t);
    el.appendChild(card);
  });
}

function speakTrace(t){
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

function speak(text){
  if(!window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(text);
  u.lang='en-US'; u.rate=.92; u.pitch=.85;
  speechSynthesis.speak(u);
}

function paintMind(ready, writer){
  const badge=document.getElementById('mindbadge');
  if(!badge) return;
  if(ready){
    badge.textContent='mind · live · '+(writer||'model');
    badge.classList.add('on');
  }else{
    badge.textContent='mind · local writer';
    badge.classList.remove('on');
  }
}

function renderChamber(data){
  chamber=data;
  occupancy=data.occupancy&&data.occupancy.length===128?data.occupancy:occupancy;
  mine=data.node_id;
  connected=true; address=data.address;
  if(!sessionKind()) setSessionKind('local');
  paintConnect();
  document.getElementById('title').textContent=data.title;
  document.getElementById('standing').textContent=data.standing_line;
  document.getElementById('kicker').textContent=data.node_id===null?'doorway':'your seat';
  document.getElementById('sigilcap').textContent=data.alias||short(data.address);
  document.getElementById('sigilcard').classList.toggle('lit', data.node_id!==null);
  drawSigil(data.sigil);
  paintMind(data.model_ready!==false, data.writer);

  const region=data.region;
  const myth=region&&MYTH[region]?MYTH[region][0]:'the doorway';
  document.getElementById('meta').textContent=data.node_id===null
    ? short(data.address)+' · waiting for a seat'
    : pad(data.node_id)+' · '+region+' · '+myth+(data.days_standing!=null?' · day '+data.days_standing:'');

  const alias=document.getElementById('alias');
  if(alias && document.activeElement!==alias) alias.value=data.alias||'';

  const cd=document.getElementById('cooldown');
  if(cd){
    cd.textContent=data.cooldown_seconds>0
      ? 'Wait '+data.cooldown_seconds+'s before the next scenario.'
      : (data.node_id===null?'':'Ready to send.');
  }

  if(data.node_id===null){
    setMode('doorway');
    renderCta('doorway');
    selected=firstFree();
    renderGrid();
  }else{
    setMode('seated');
    renderCta('seated');
    renderTraces(data.traces);
    const scnEl=document.getElementById('scn');
    const sendEl=document.getElementById('send');
    if(scnEl) scnEl.disabled=false;
    if(sendEl) sendEl.disabled=!(scnEl&&scnEl.value.trim());
  }
  showErr('');
}

function guestView(state){
  chamber=null; mine=null; connected=false;
  if(!token) address='';
  occupancy=(state.nodes||[]).reduce((acc,n)=>{ acc[n.id]=!!n.owner; return acc; }, Array(128).fill(false));
  document.getElementById('title').textContent='the doorway';
  document.getElementById('standing').textContent='Enter to open your seat in the shared mind.';
  document.getElementById('kicker').textContent='cabinet';
  document.getElementById('sigilcap').textContent='unsigned';
  document.getElementById('meta').textContent='';
  document.getElementById('sigilcard').classList.remove('lit');
  drawSigil(emptySigil());
  paintMind(state.model_ready!==false, state.writer);
  setMode('guest');
  renderCta('guest');
  paintConnect();
}

async function connect(){
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
    token=me.token; address=me.address; connected=true; mine=me.node_id;
    localStorage.setItem('ganglia_token',token);
    localStorage.setItem('ganglia_address',address);
    paintConnect();
    await load();
  }catch(err){
    showErr(err.message);
  }finally{
    setConnectBusy(false);
    paintConnect();
  }
}

async function disconnect(){
  try{ if(token) await api('/api/auth/logout',{method:'POST', body:'{}'}); }catch(_e){}
  token=''; address=''; connected=false; mine=null; chamber=null; selected=null;
  localStorage.removeItem('ganglia_token');
  localStorage.removeItem('ganglia_address');
  clearSessionKind();
  showErr('');
  paintConnect();
  await loadGuest();
}

async function takeFree(){
  showErr('');
  if(!connected) await connect();
  if(mine!==null){ await load(); return; }
  const i=selected!==null&&!occupancy[selected]?selected:firstFree();
  if(i===null) throw new Error('No free seats left.');
  const btn=document.getElementById('takefree')||document.getElementById('ctafree');
  if(btn){ btn.disabled=true; btn.textContent='Claiming…'; }
  try{
    await api('/api/nodes/'+i+'/claim',{method:'POST', body:'{}'});
    mine=i; occupancy[i]=true;
    await load();
  }finally{
    if(btn){ btn.disabled=false; btn.textContent='Take a free seat'; }
  }
}

async function loadGuest(){
  const state=await api('/api/state');
  guestView(state);
}

async function load(){
  paintConnect();
  if(!token){ await loadGuest(); return; }
  try{
    const data=await api('/api/me/chamber');
    renderChamber(data);
  }catch(err){
    showErr(err.message);
    await loadGuest().catch(()=>{});
  }
}

document.getElementById('connect').onclick=()=>{
  if(connected) return;
  connect().catch(err=>showErr(err.message));
};
const leaveBtn=document.getElementById('leave');
if(leaveBtn) leaveBtn.onclick=()=>disconnect().catch(err=>showErr(err.message));
document.getElementById('enter')&&(document.getElementById('enter').onclick=()=>connect().catch(err=>showErr(err.message)));
document.getElementById('takefree').onclick=()=>takeFree().catch(err=>showErr(err.message));
document.getElementById('savealias').onclick=async()=>{
  showErr('');
  if(!connected){ showErr('Enter first.'); return; }
  try{
    await api('/api/me/alias',{method:'POST', body:JSON.stringify({alias:document.getElementById('alias').value})});
    await load();
  }catch(err){ showErr(err.message); }
};
const scn=document.getElementById('scn');
scn.oninput=()=>{
  document.getElementById('chars').textContent=`${scn.value.length} / 280`;
  document.getElementById('send').disabled=!scn.value.trim()||mine===null;
};
document.getElementById('send').onclick=async()=>{
  const v=scn.value.trim(); if(!v||mine===null) return;
  showErr('');
  scn.value=''; scn.oninput();
  document.getElementById('send').disabled=true;
  try{
    await api('/api/scenarios',{method:'POST', body:JSON.stringify({text:v})});
    await load();
  }catch(err){
    showErr(err.message);
    document.getElementById('send').disabled=false;
  }
};
document.getElementById('theme').onclick=()=>{
  const r=document.documentElement; const dark = r.dataset.theme ? r.dataset.theme==='dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  r.dataset.theme = dark?'light':'dark'; drawLogo();
  if(chamber) drawSigil(chamber.sigil); else drawSigil(emptySigil());
};
bindAccountWatch(()=>address, ()=>{
  disconnect();
});

if(location.protocol==='file:'){
  showErr('Open through the Ganglia server, not as a file.');
}else{
  drawLogo(); paintConnect(); load().catch(err=>showErr(err.message));
  setInterval(()=>{
    if(document.activeElement&&['alias','scn'].includes(document.activeElement.id)) return;
    if(!token) return;
    load().catch(()=>{});
  }, 5000);
}
