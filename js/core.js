/*
 * core.js: shared helpers, colour tokens, pixel logo mark
 * Classic script (no modules/build). Files share global scope; load order matters:
 * core.js -> wallet.js -> brain.js -> app.js
 */
'use strict';
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* ---------- the mark (23x23) ---------- */
const N=23,C=11, G=new Set(), EYE=new Set(), NODES={}, ARMS=[];
const k=(x,y)=>x+','+y;
for(let x=8;x<15;x++)for(let y=8;y<15;y++){ if((x===8||x===14)&&(y===8||y===14))continue; G.add(k(x,y)); }
const node=(cx,cy)=>{const s=[];for(let i=-1;i<2;i++)for(let j=-1;j<2;j++)s.push(k(cx+i,cy+j));return s;};
// arms: ordered cells soma -> node centre
const dirs=[[0,-1],[1,-1],[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1]];
dirs.forEach(([dx,dy],i)=>{
  const path=[]; const diag=dx&&dy;
  const len= diag?3:5, start=diag?4:3;
  if(diag){ for(let s=0;s<len;s++) path.push([C+dx*(start+s),C+dy*(start+s)]); }
  else { for(let s=7;s>=3;s--) path.push([C+dx*(C-s),C+dy*(C-s)]); }
  const nc= diag?[C+dx*8,C+dy*8]:[C+dx*10,C+dy*10];
  path.forEach(p=>G.add(k(...p)));
  node(...nc).forEach(c=>G.add(c));
  NODES[i]=node(...nc); ARMS.push(path.concat([nc]));
});
['11,10','12,10','11,11','12,11'].forEach(e=>{G.delete(e);EYE.add(e)});

// header logo
const logo=document.getElementById('logo');
function drawLogo(){
  if(!logo) return;
  logo.innerHTML='';
  G.forEach(s=>{const [x,y]=s.split(',');const r=document.createElementNS('http://www.w3.org/2000/svg','rect');
    r.setAttribute('x',x);r.setAttribute('y',y);r.setAttribute('width',1);r.setAttribute('height',1);
    r.setAttribute('fill', NODES[1].includes(s)?css('--acc'):css('--fg'));     logo.appendChild(r);});
}

function openSeat(){
  location.href='/me.html';
}

