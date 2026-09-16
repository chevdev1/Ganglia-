/*
 * motion.js: shared animation primitives (dither reveal, scramble, line reveal,
 * count up, draw path, magnetic hover). Pure vanilla, no build step.
 * Load order: core.js -> motion.js -> wallet.js -> brain.js -> app.js
 * `reduce` (prefers-reduced-motion) comes from core.js.
 */
'use strict';

const BAYER8 = [
  [ 0,32, 8,40, 2,34,10,42],
  [48,16,56,24,50,18,58,26],
  [12,44, 4,36,14,46, 6,38],
  [60,28,52,20,62,30,54,22],
  [ 3,35,11,43, 1,33, 9,41],
  [51,19,59,27,49,17,57,25],
  [15,47, 7,39,13,45, 5,37],
  [63,31,55,23,61,29,53,21]
];

/* dither reveal: an 8x8 Bayer-ordered mask over `el` peels away to reveal it */
function ditherReveal(el, {duration=480}={}){
  if (reduce) return Promise.resolve();
  return new Promise(resolve=>{
    const N=8;
    const pos = getComputedStyle(el).position;
    if (pos==='static') el.style.position='relative';
    const overlay=document.createElement('div');
    overlay.className='dither-overlay';
    overlay.style.cssText=`position:absolute;inset:0;display:grid;grid-template-columns:repeat(${N},1fr);grid-template-rows:repeat(${N},1fr);pointer-events:none;z-index:5`;
    const bg=css('--bg');
    const cells=[];
    for(let y=0;y<N;y++)for(let x=0;x<N;x++){
      const d=document.createElement('div');
      d.style.gridColumn=String(x+1);
      d.style.gridRow=String(y+1);
      d.style.background=bg;
      overlay.appendChild(d);
      cells.push({el:d, v:BAYER8[y][x]});
    }
    el.appendChild(overlay);
    cells.sort((a,b)=>a.v-b.v);
    const steps=16, per=Math.ceil(cells.length/steps), stepDur=duration/steps;
    let step=0;
    const iv=setInterval(()=>{
      step++;
      const upto=Math.min(step*per, cells.length);
      for(let i=0;i<upto;i++) cells[i].el.style.visibility='hidden';
      if(step>=steps){ clearInterval(iv); overlay.remove(); resolve(); }
    }, stepDur);
  });
}

/* scramble: text "decodes" left to right through a glyph set, once, fast */
function scramble(el, {duration=700, charset='░▒▓█01'}={}){
  if (reduce) return Promise.resolve();
  return new Promise(resolve=>{
    const original = el.innerHTML;
    if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', el.textContent);
    const parts = original.split(/(<br\s*\/?>)/gi);
    const isBreak = parts.map(p=>/^<br/i.test(p));
    const totalLen = parts.reduce((n,p,i)=> n + (isBreak[i]?0:p.length), 0);
    const steps=14, stepDur=duration/steps;
    let frame=0;
    const iv=setInterval(()=>{
      frame++;
      const revealCount = Math.floor((frame/steps)*totalLen);
      let counted=0;
      const out = parts.map((p,i)=>{
        if (isBreak[i]) return p;
        return [...p].map(ch=>{
          if (ch===' ') return ch;
          counted++;
          return counted<=revealCount ? ch : charset[(Math.random()*charset.length)|0];
        }).join('');
      }).join('');
      el.innerHTML = out;
      if (frame>=steps){ clearInterval(iv); el.innerHTML = original; resolve(); }
    }, stepDur);
  });
}

/* lineReveal: each rendered line of `el` rises out of a mask, staggered */
function lineReveal(el, {stagger=60, duration=480}={}){
  if (reduce) return Promise.resolve();
  return new Promise(resolve=>{
    const text = el.textContent;
    el.setAttribute('aria-label', text);
    const tokens = text.split(/(\s+)/).filter(t=>t.length);
    el.innerHTML='';
    const wordSpans=[];
    tokens.forEach(t=>{
      if (/^\s+$/.test(t)){ el.appendChild(document.createTextNode(t)); return; }
      const s=document.createElement('span');
      s.textContent=t;
      s.style.display='inline-block';
      el.appendChild(s);
      wordSpans.push(s);
    });
    const lines = new Map();
    wordSpans.forEach(s=>{
      const top = s.offsetTop;
      if (!lines.has(top)) lines.set(top, []);
      lines.get(top).push(s);
    });
    el.innerHTML='';
    const groups = [...lines.values()];
    groups.forEach((lineSpans,i)=>{
      const wrap=document.createElement('span');
      wrap.style.cssText='display:block;overflow:hidden';
      const inner=document.createElement('span');
      inner.style.cssText=`display:block;transform:translateY(110%);opacity:0;transition:transform ${duration}ms var(--ease-out),opacity ${duration}ms var(--ease-out);transition-delay:${i*stagger}ms`;
      lineSpans.forEach((s,j)=>{
        inner.appendChild(s);
        if (j<lineSpans.length-1) inner.appendChild(document.createTextNode(' '));
      });
      wrap.appendChild(inner);
      el.appendChild(wrap);
      requestAnimationFrame(()=>requestAnimationFrame(()=>{
        inner.style.transform='translateY(0)';
        inner.style.opacity='1';
      }));
    });
    setTimeout(resolve, duration + groups.length*stagger);
  });
}

/* countUp: pixel-styled stepped counter from current value to `to` */
function countUp(el, to, {duration=900, steps=20, format=n=>String(n)}={}){
  const from = parseInt(el.textContent.replace(/[^\d-]/g,''),10) || 0;
  if (reduce){ el.textContent = format(to); return Promise.resolve(); }
  return new Promise(resolve=>{
    let step=0;
    const stepDur=duration/steps;
    const iv=setInterval(()=>{
      step++;
      const v = Math.round(from + (to-from)*(step/steps));
      el.textContent = format(v);
      if (step>=steps){
        clearInterval(iv);
        el.textContent = format(to);
        el.style.transition='transform .12s var(--ease-snap)';
        el.style.transform='scale(1.12)';
        setTimeout(()=>{ el.style.transform='scale(1)'; }, 120);
        resolve();
      }
    }, stepDur);
  });
}

/* drawPath: stroke-dashoffset animated in discrete 4px steps */
function drawPath(pathEl, {duration=480, step=4}={}){
  if (reduce){ pathEl.style.strokeDasharray='none'; return Promise.resolve(); }
  return new Promise(resolve=>{
    const len = pathEl.getTotalLength();
    pathEl.style.strokeDasharray=String(len);
    pathEl.style.strokeDashoffset=String(len);
    const steps = Math.max(1, Math.round(len/step));
    const stepDur = duration/steps;
    let i=0;
    const iv=setInterval(()=>{
      i++;
      pathEl.style.strokeDashoffset = String(Math.max(0, len - i*step));
      if (i>=steps){ clearInterval(iv); pathEl.style.strokeDashoffset='0'; resolve(); }
    }, stepDur);
  });
}

/* magnetic: element gently pulls toward the cursor on hover, desktop only */
function magnetic(el, {max=6}={}){
  if (reduce || matchMedia('(hover: none)').matches) return;
  el.addEventListener('mousemove', e=>{
    const r = el.getBoundingClientRect();
    const dx = (e.clientX - (r.left+r.width/2)) / (r.width/2);
    const dy = (e.clientY - (r.top+r.height/2)) / (r.height/2);
    el.style.transform = `translate(${(dx*max).toFixed(1)}px,${(dy*max).toFixed(1)}px)`;
  });
  el.addEventListener('mouseleave', ()=>{
    el.style.transition='transform var(--d-2) var(--ease-out)';
    el.style.transform='translate(0,0)';
    setTimeout(()=>{ el.style.transition=''; }, 260);
  });
}

/* themeWipe: covers the viewport with a Bayer-ordered mask, swaps theme underneath, peels away */
function themeWipe(applyTheme, {duration=400}={}){
  if (reduce){ applyTheme(); return; }
  const N=8;
  const overlay=document.createElement('div');
  overlay.style.cssText=`position:fixed;inset:0;z-index:80;display:grid;grid-template-columns:repeat(${N},1fr);grid-template-rows:repeat(${N},1fr);pointer-events:none`;
  const cells=[];
  for(let y=0;y<N;y++)for(let x=0;x<N;x++){
    const d=document.createElement('div');
    d.style.gridColumn=String(x+1); d.style.gridRow=String(y+1);
    d.style.background=css('--bg');
    overlay.appendChild(d);
    cells.push({el:d, v:BAYER8[y][x]});
  }
  document.body.appendChild(overlay);
  applyTheme();
  const newBg=css('--bg');
  cells.forEach(c=>{ c.el.style.background=newBg; });
  cells.sort((a,b)=>a.v-b.v);
  const steps=16, per=Math.ceil(cells.length/steps), stepDur=duration/steps;
  let step=0;
  const iv=setInterval(()=>{
    step++;
    const upto=Math.min(step*per, cells.length);
    for(let i=0;i<upto;i++) cells[i].el.style.visibility='hidden';
    if(step>=steps){ clearInterval(iv); overlay.remove(); }
  }, stepDur);
}

/* ambient: minimal procedural night-pixel ambience, synthesised with WebAudio, no audio files.
   Warm single-root drone + a consonant fifth + a slow pentatonic arpeggio, all lowpass-filtered
   to stay soft. startAmbient() is safe to call repeatedly: it always retries ac.resume() (needed
   because audio can only truly start inside a real user gesture — click/key/touch, not scroll). */
let _ambientCtx=null, _ambientNodes=null, _ambientTimer=null, _ambientOn=false;
function startAmbient(){
  _ambientCtx = _ambientCtx || new (window.AudioContext||window.webkitAudioContext)();
  const ac=_ambientCtx;
  if (ac.state!=='running') ac.resume().catch(()=>{});
  if (_ambientOn) return;
  _ambientOn=true;

  const master=ac.createGain();
  master.gain.value=0;
  const warmth=ac.createBiquadFilter();
  warmth.type='lowpass'; warmth.frequency.value=2200; warmth.Q.value=0.3;
  master.connect(warmth); warmth.connect(ac.destination);
  master.gain.linearRampToValueAtTime(0.05, ac.currentTime+3);

  const root=65.41; // C2, warm and low
  const bass=ac.createOscillator(); bass.type='sine'; bass.frequency.value=root;
  const bassGain=ac.createGain(); bassGain.gain.value=0.4;
  const bassLfo=ac.createOscillator(); bassLfo.frequency.value=0.06;
  const bassLfoGain=ac.createGain(); bassLfoGain.gain.value=0.15;
  bassLfo.connect(bassLfoGain); bassLfoGain.connect(bassGain.gain);
  bass.connect(bassGain); bassGain.connect(master);
  bass.start(); bassLfo.start();

  const fifth=ac.createOscillator(); fifth.type='sine'; fifth.frequency.value=root*1.5; // perfect fifth, consonant
  const fifthGain=ac.createGain(); fifthGain.gain.value=0.1;
  fifth.connect(fifthGain); fifthGain.connect(master);
  fifth.start();

  const scale=[261.63,293.66,329.63,392.00,440.00]; // C major pentatonic, gentle chiptune register
  let step=0;
  function pluck(){
    if (!_ambientOn) return;
    step=(step+1+((Math.random()*2)|0))%scale.length;
    const o=ac.createOscillator(); o.type='triangle'; o.frequency.value=scale[step];
    const filt=ac.createBiquadFilter(); filt.type='lowpass'; filt.frequency.value=1400;
    const g=ac.createGain(); g.gain.value=0;
    o.connect(filt); filt.connect(g);
    if (ac.createStereoPanner){
      const pan=ac.createStereoPanner(); pan.pan.value=Math.random()*1.2-0.6;
      g.connect(pan); pan.connect(master);
    } else g.connect(master);
    const t=ac.currentTime;
    g.gain.linearRampToValueAtTime(0.05, t+0.15);
    g.gain.exponentialRampToValueAtTime(0.0001, t+3.2);
    o.start(t); o.stop(t+3.3);
    _ambientTimer=setTimeout(pluck, 2600+Math.random()*3200);
  }
  _ambientTimer=setTimeout(pluck, 2200+Math.random()*2000);
  _ambientNodes={master, bass, bassLfo, fifth};
}
function stopAmbient(){
  if (!_ambientOn) return;
  _ambientOn=false;
  clearTimeout(_ambientTimer);
  if (_ambientNodes){
    const {master, bass, bassLfo, fifth}=_ambientNodes, ac=_ambientCtx;
    master.gain.cancelScheduledValues(ac.currentTime);
    master.gain.linearRampToValueAtTime(0, ac.currentTime+1.2);
    setTimeout(()=>{ [bass,bassLfo,fifth].forEach(n=>{ try{n.stop();}catch(_e){} }); }, 1300);
  }
  _ambientNodes=null;
}

/* onEnterView: fire `cb` once when `el` crosses `threshold` visibility, scrolling down only */
function onEnterView(el, cb, {threshold=0.22}={}){
  let done=false;
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(entry=>{
      if (entry.isIntersecting && !done){
        done=true;
        cb();
        io.unobserve(el);
      }
    });
  }, {threshold});
  io.observe(el);
}
