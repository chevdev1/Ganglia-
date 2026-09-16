/*
 * brain.js: 3D pixel brain renderer, 128 nodes, probe, signal propagation
 * Classic script (no modules/build). Files share global scope; load order matters:
 * core.js -> brain.js -> app.js
 */
/* ---------- 3D pixel brain + probe ---------- */
const brain=(()=>{
  const cv=document.getElementById('mindcv');
  if(!cv){
    return {start(){},target(){},ripple(){},stimulate(){},colors(){}};
  }
  const g=cv.getContext('2d');
  const W=320,H=240; cv.width=W; cv.height=H;
  const img=g.createImageData(W,H), buf=img.data, zb=new Float32Array(W*H);
  const hex=h=>{h=h.replace('#','');if(h.length===3)h=h.split('').map(c=>c+c).join('');return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)]};
  let COL; const colors=()=>{COL={bg:hex(css('--bg')),fg:hex(css('--fg')),dim:hex(css('--dim')),cell:hex(css('--cell')),acc:hex(css('--acc'))};};
  const BAY=[0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5];
  let sd=7; const r=()=>((sd=(sd*16807)%2147483647)/2147483647);

  /* geometry: point cloud of a brain */
  const P=[]; // flat arrays for speed
  function add(x,y,z,nx,ny,nz,t){P.push(x,y,z,nx,ny,nz,t);}
  function hemiPoint(side,dx,dy,dz,noise=true){
    const rx=.56,ry=.62,rz=.96,cx=side*.21,cy=.14;
    if(dx*side<0) dx*=.3;          // flat medial wall -> fissure
    if(dy<0) dy*=.62;              // flatter base
    let tone=1, k=1;
    if(noise){
      const f1=Math.sin(dz*7.5+dy*4+side*.7+Math.sin(dy*5)*1.3)*Math.sin(dy*6.5-dz*2.6+Math.sin(dz*4.2)*1.1+side);
      const f2=Math.sin((dx*side)*9+dz*5+dy*3);
      const sulc=Math.min(Math.abs(f1),Math.abs(f2)*1.6);
      const lat=dx*side;
      const sylvian = lat>.35 && dz>-.35 && dz<.7 && Math.abs(dy-(-.08+dz*.28))<.07;
      const central = dy>-.05 && Math.abs(dz-(.02+dy*.22))<.045;
      if(sulc<.16||sylvian||central){ tone=.22; k=.965; } else tone=.8+sulc*.2;
    }
    let x=cx+dx*rx*k, y=cy+dy*ry*k, z=dz*rz*k;
    if(dy<-.15 && dz>-.1 && dz<.55 && dx*side>.45) y-=.1;   // temporal lobe
    if(dz>.7) y-=.04*(dz-.7)*10*(.2-dy);                     // frontal slope
    const nl=Math.hypot(dx/rx,dy/ry,dz/rz)||1;
    return [x,y,z,dx/rx/nl,dy/ry/nl,dz/rz/nl,tone];
  }
  const sph=()=>{const u=r()*2-1,a=r()*6.2832,q=Math.sqrt(1-u*u);return [q*Math.cos(a),u,q*Math.sin(a)];};
  for(const side of[-1,1]) for(let i=0;i<15000;i++){ const [dx,dy,dz]=sph(); add(...hemiPoint(side,dx,dy,dz)); }
  for(let i=0;i<5000;i++){ const [dx,dy,dz]=sph();
    add(dx*.5, -.33+dy*.24, -.6+dz*.34, dx,dy,dz, Math.abs(Math.sin(dy*26))<.35?.3:.85); }
  for(let i=0;i<1100;i++){ const a=r()*6.2832, y=-.3-r()*.6;
    add(Math.cos(a)*.13, y, -.36+(y+.35)*.25+Math.sin(a)*.13, Math.cos(a),0,Math.sin(a), .45); }

  /* 128 nodes on the cortex */
  const NODE=[];
  for(const side of[-1,1]){
    const cand=[], M=170;
    for(let i=0;i<M;i++){ const y=1-(i+.5)/M*2, q=Math.sqrt(1-y*y), a=i*2.39996;
      const dx=q*Math.cos(a), dz=q*Math.sin(a);
      if(y<-.45 || dx*side<-.15) continue;
      const p=hemiPoint(side,dx,y,dz,false); cand.push({x:p[0]+p[3]*.03,y:p[1]+p[4]*.03,z:p[2]+p[5]*.03,nx:p[3],ny:p[4],nz:p[5]}); }
    const step=cand.length/64; for(let i=0;i<64;i++) NODE.push(cand[Math.floor(i*step)]);
  }
  const EDGE=[], NB=NODE.map(()=>[]);
  NODE.forEach((a,i)=>{ NODE.map((b,j)=>[j,(a.x-b.x)**2+(a.y-b.y)**2+(a.z-b.z)**2]).filter(v=>v[0]!==i).sort((p,q)=>p[1]-q[1]).slice(0,3)
    .forEach(([j])=>{ if(!NB[i].includes(j)){NB[i].push(j);NB[j].push(i);EDGE.push([i,j]);} }); });

  /* view state */
  let rotY=-1.25, rotX=.22, vY=0, tgtY=null, tgtX=null, dragging=false, lastInteract=0;
  const act=new Float32Array(128); let pulses=[];
  const probe={node:null,next:null,depth:0,phase:'idle',hold:0};
  const SC=84;
  let cy_,sy_,cx_,sx_;
  function setRot(){cy_=Math.cos(rotY);sy_=Math.sin(rotY);cx_=Math.cos(rotX);sx_=Math.sin(rotX);}
  function proj(x,y,z,out){ const x1=x*cy_+z*sy_, z1=-x*sy_+z*cy_; const y2=y*cx_-z1*sx_, z2=y*sx_+z1*cx_;
    const p=3.6/(3.6-z2); out[0]=W/2+x1*SC*p; out[1]=H/2+10-y2*SC*p; out[2]=z2; return out; }
  function rotN(nx,ny,nz){ const z1=-nx*sy_+nz*cy_; return ny*sx_+z1*cx_; }
  const put=(x,y,c)=>{ if(x<0||y<0||x>=W||y>=H)return; const o=(y*W+x)*4; buf[o]=c[0];buf[o+1]=c[1];buf[o+2]=c[2];buf[o+3]=255; };
  const sq=(x,y,s,c)=>{ for(let i=0;i<s;i++)for(let j=0;j<s;j++) put(x+i,y+j,c); };
  function line(a,b,c,dotted,depthTest){
    let x0=Math.round(a[0]),y0=Math.round(a[1]),x1=Math.round(b[0]),y1=Math.round(b[1]);
    const dx=Math.abs(x1-x0),dy=-Math.abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1; let err=dx+dy,n=0;
    const steps=Math.max(dx,-dy)||1;
    while(true){ const t=n/steps, z=a[2]+(b[2]-a[2])*t;
      if((!dotted||n%2===0) && (!depthTest || x0<0||y0<0||x0>=W||y0>=H || z>=zb[y0*W+x0]-.03)) put(x0,y0,c);
      if(x0===x1&&y0===y1)break; const e2=2*err; if(e2>=dy){err+=dy;x0+=sx;} if(e2<=dx){err+=dx;y0+=sy;} n++; }
  }
  const L=(()=>{const l=[-.45,.6,.66],m=Math.hypot(...l);return l.map(v=>v/m);})();

  function stimulate(i,gen=3){ act[i]=1; if(gen<=0)return;
    NB[i].forEach(j=>{ if(r()<.85) pulses.push({a:i,b:j,t:0,gen:gen-1}); }); }
  function target(i,fire=false){
    probe.next=i; probe.fire=fire;
    if(probe.phase==='idle'){ probe.node=i; probe.next=null; probe.phase='in'; }
    else probe.phase='out';
    const n=NODE[i]; tgtY=Math.atan2(-n.nx,n.nz)+.85; tgtX=.28+Math.max(-.3,Math.min(.4,n.ny*.5)); lastInteract=performance.now();
    hud();
  }
  function ripple(){ for(let k=0;k<3;k++) stimulate(r()*128|0,3); }

  /* HUD */
  const hudProbe=document.getElementById('hudprobe'), tip=document.getElementById('hudtip');
  const pad=n=>'#'+String(n).padStart(3,'0');
  function hud(){ const st={idle:'probe parked',in:'inserting',hold:'stimulating',out:'retracting',on:'reading'}[probe.phase];
    hudProbe.textContent = probe.node===null? 'probe parked' : `probe on ${pad(probe.phase==='out'&&probe.next!==null?probe.next:probe.node)}, ${st}`; }

  /* pointer */
  let hover=-1, down=null, moved=0, vis=new Int8Array(128), scr=NODE.map(()=>[0,0,0]);
  const toLow=e=>{const b=cv.getBoundingClientRect();return [(e.clientX-b.left)/b.width*W,(e.clientY-b.top)/b.height*H];};
  cv.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];moved=0;dragging=true;vY=0;tgtY=tgtX=null;cv.setPointerCapture(e.pointerId);cv.style.cursor='grabbing';});
  cv.addEventListener('pointermove',e=>{
    if(dragging&&down){ const dx=e.clientX-down[0], dy=e.clientY-down[1]; moved+=Math.abs(dx)+Math.abs(dy);
      rotY+=dx*.008; rotX=Math.max(-.9,Math.min(1.1,rotX+dy*.006)); vY=dx*.008; down=[e.clientX,e.clientY]; lastInteract=performance.now(); }
    const [lx,ly]=toLow(e); let best=-1,bd=36;
    for(let i=0;i<128;i++) if(vis[i]){ const d=(scr[i][0]-lx)**2+(scr[i][1]-ly)**2; if(d<bd){bd=d;best=i;} }
    hover=best;
    if(!dragging) cv.style.cursor= best>=0?'pointer':'grab';
    if(best>=0){ const st= best===mine?'yours': owners[best]?'claimed':'free';
      tip.textContent=`${pad(best)}  ${labels[Math.floor(best/16)]}, ${st}`; tip.hidden=false; } else tip.hidden=true;
  });
  const up=e=>{ if(!dragging)return; dragging=false; cv.style.cursor='grab';
    if(moved<6 && hover>=0){ selected=hover; renderGrid(); renderPanel(); target(hover,true); } };
  cv.addEventListener('pointerup',up); cv.addEventListener('pointercancel',up);
  cv.addEventListener('pointerleave',()=>{hover=-1;tip.hidden=true;});
  cv.addEventListener('keydown',e=>{ if(e.key==='ArrowLeft')rotY-=.15; if(e.key==='ArrowRight')rotY+=.15; if(e.key==='ArrowUp')rotX-=.1; if(e.key==='ArrowDown')rotX+=.1; });

  /* render */
  const tmp=[0,0,0], A=[0,0,0], B=[0,0,0];
  let frameN=0, lastAmbient=0;
  function frame(ts){
    frameN++;
    // motion
    if(!dragging){
      if(tgtY!==null){ let d=tgtY-rotY; d=Math.atan2(Math.sin(d),Math.cos(d)); rotY+=d*.07; rotX+=(tgtX-rotX)*.07; if(Math.abs(d)<.005) tgtY=null; }
      else { rotY+=vY; vY*=.94; if(!reduce && ts-lastInteract>2500) rotY+=.0035; }
    }
    setRot();
    const {bg,fg,cell,acc,dim}=COL;
    for(let i=0;i<W*H;i++){ const o=i*4; buf[o]=bg[0];buf[o+1]=bg[1];buf[o+2]=bg[2];buf[o+3]=255; zb[i]=-9; }
    for(let y=4;y<H;y+=8)for(let x=4;x<W;x+=8) put(x,y,cell);
    // surface
    for(let k=0;k<P.length;k+=7){
      const nz=rotN(P[k+3],P[k+4],P[k+5]); if(nz<-.15) continue;
      proj(P[k],P[k+1],P[k+2],tmp); const x=tmp[0]|0,y=tmp[1]|0; if(x<0||y<0||x>=W-1||y>=H-1)continue;
      const z=tmp[2];
      // light using rotated normal approx
      const nx=P[k+3]*cy_+P[k+5]*sy_, z1=-P[k+3]*sy_+P[k+5]*cy_, ny=P[k+4]*cx_-z1*sx_;
      let b=Math.max(0,nx*L[0]+ny*L[1]+nz*L[2])*.75+.32; b*=P[k+6];
      const lvl=b*17;
      for(let oy=0;oy<2;oy++)for(let ox=0;ox<2;ox++){ const px=x+ox,py=y+oy,idx=py*W+px; if(z<=zb[idx])continue; zb[idx]=z;
        const o=idx*4, c= lvl>BAY[(py%4)*4+px%4] ? fg : cell; buf[o]=c[0];buf[o+1]=c[1];buf[o+2]=c[2]; }
    }
    // nodes projection & visibility
    for(let i=0;i<128;i++){ const n=NODE[i]; proj(n.x,n.y,n.z,scr[i]); vis[i]= rotN(n.nx,n.ny,n.nz)>.05 ?1:0; }
    // edges
    EDGE.forEach(([a,b])=>{ if(vis[a]&&vis[b]) line(scr[a],scr[b],dim,true,false); });
    // pulses
    const nextP=[];
    pulses.forEach(p=>{ p.t+= reduce?1:.045; const a=NODE[p.a],b=NODE[p.b];
      if(p.t>=1){ stimulate(p.b,p.gen); return; }
      nextP.push(p);
      if(vis[p.a]||vis[p.b]){ proj(a.x+(b.x-a.x)*p.t,a.y+(b.y-a.y)*p.t,a.z+(b.z-a.z)*p.t,tmp); sq(Math.round(tmp[0])-1,Math.round(tmp[1])-1,2,acc); } });
    pulses=nextP.length>260?nextP.slice(-260):nextP;
    // node glyphs
    for(let i=0;i<128;i++){ act[i]*=.93; if(!vis[i])continue;
      const x=Math.round(scr[i][0]), y=Math.round(scr[i][1]);
      sq(x-2,y-2,5,bg);
      if(i===mine) sq(x-1,y-1,3,acc);
      else if(owners[i]) sq(x-1,y-1,3,fg);
      else { sq(x-1,y-1,3,cell); put(x,y,fg); }
      if(act[i]>.35) sq(x-1,y-1,3,acc);
      if(i===selected && (frameN>>4)%2===0){ for(let d=-3;d<=3;d++){put(x+d,y-3,acc);put(x+d,y+3,acc);put(x-3,y+d,acc);put(x+3,y+d,acc);} }
      if(i===hover){ put(x-4,y-4,fg);put(x+4,y-4,fg);put(x-4,y+4,fg);put(x+4,y+4,fg); }
    }
    // probe
    if(probe.node!==null){
      const sp= reduce?1:.03;
      if(probe.phase==='in'){ probe.depth=Math.min(1,probe.depth+sp); if(probe.depth>=1){probe.phase='hold';probe.hold=0;stimulate(probe.node,4);hud();} }
      else if(probe.phase==='hold'){ probe.hold++; if(probe.hold>70){probe.phase='on';hud();} }
      else if(probe.phase==='on'){ if(!reduce && ts-lastAmbient>2600){lastAmbient=ts;stimulate(probe.node,2);} }
      else if(probe.phase==='out'){ probe.depth=Math.max(0,probe.depth-sp*1.6); if(probe.depth<=0){ probe.node=probe.next; probe.next=null; probe.phase='in'; hud(); } }
      const n=NODE[probe.node], off=.8*(1-probe.depth)-.06;
      const tipW=[n.x+n.nx*off,n.y+n.ny*off,n.z+n.nz*off], topW=[tipW[0]+n.nx*.72,tipW[1]+n.ny*.72,tipW[2]+n.nz*.72];
      proj(...tipW,A); proj(...topW,B);
      line(B,A,fg,false,true); line([B[0]+1,B[1],B[2]],[A[0]+1,A[1],A[2]],fg,false,true);
      // electrode sites along lower shank
      for(let s=1;s<6;s++){ const t=s*.11; const x=A[0]+(B[0]-A[0])*t, y=A[1]+(B[1]-A[1])*t, z=A[2]+(B[2]-A[2])*t;
        const xi=Math.round(x), yi=Math.round(y); if(xi>=0&&yi>=0&&xi<W&&yi<H&&z>=zb[yi*W+xi]-.03) put(xi,yi, (probe.phase==='hold'||probe.phase==='on')&&((frameN>>2)+s)%3===0?acc:bg); }
      // head + cable
      sq(Math.round(B[0])-3,Math.round(B[1])-3,7,fg); sq(Math.round(B[0])-1,Math.round(B[1])-1,3,(frameN>>5)%2?acc:bg);
      const cab=[topW[0]+n.nx*.3,topW[1]+n.ny*.3+.25,topW[2]+n.nz*.3]; proj(...cab,tmp); line(B,tmp,dim,true,false);
      if(typeof window.syncLotCard==='function') window.syncLotCard(probe.node, B[0], B[1]);
    } else if(typeof window.syncLotCard==='function') {
      window.syncLotCard(null, 0, 0);
    }
    g.putImageData(img,0,0);
    requestAnimationFrame(frame);
  }
  function start(){ colors(); hud(); requestAnimationFrame(frame);
    setTimeout(()=>{ let c=0,bx=-1; owners.forEach((o,i)=>{ if(o&&NODE[i].nx<bx+0){} if(o&&-NODE[i].nx>bx&&NODE[i].ny>0){bx=-NODE[i].nx;c=i;} }); target(c,true); },700);
    if(!reduce) setInterval(()=>{ if(!document.hidden) stimulate(r()*128|0,2); },1800); }
  return {start,target,ripple,stimulate,colors};
})();

