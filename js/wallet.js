/*
 * wallet.js: Void-style connect — WalletConnect QR, injected extension, or browser key.
 * core.js first. app.js / chamber.js after.
 */
let _walletBusy=false;
let _activeProvider=null;
let _pickResolve=null;
let _wcProvider=null;
let _wcProjectId=null;
let _wcReady=null;

function showErr(msg){
  const flash=document.getElementById('flash');
  if(flash){
    flash.hidden=!msg;
    flash.textContent=msg||'';
    flash.classList.remove('note');
  }
  ['err','errguest'].forEach(id=>{
    const el=document.getElementById(id);
    if(!el) return;
    if(!msg){ el.hidden=true; el.textContent=''; return; }
    el.hidden=false; el.textContent=msg;
  });
}

function showNote(_msg){}

function setConnectBusy(on){
  _walletBusy=!!on;
  const b=document.getElementById('connect');
  if(!b) return;
  b.disabled=!!on;
  if(on) b.textContent='Connecting…';
  else if(!b.hidden) b.textContent='Enter browser';
}

function localSecret(){
  const key='ganglia_local_key';
  let secret=localStorage.getItem(key)||'';
  if(!/^0x[0-9a-fA-F]{64}$/.test(secret)){
    const bytes=new Uint8Array(32);
    crypto.getRandomValues(bytes);
    secret='0x'+Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
    localStorage.setItem(key, secret);
  }
  return secret;
}

function providerLabel(p){
  if(!p) return 'Browser wallet';
  if(p.isTrust||p.isTrustWallet) return 'Trust Wallet';
  if(p.isRabby) return 'Rabby';
  if(p.isCoinbaseWallet||p.isCoinbaseBrowser) return 'Coinbase';
  if(p.isBraveWallet) return 'Brave';
  if(p.isOkxWallet||p.isOKExWallet) return 'OKX';
  if(p.isPhantom) return 'Phantom';
  if(p.isRobinhood||p.isRobinhoodWallet) return 'Robinhood';
  if(p.isMetaMask) return 'MetaMask';
  return 'Browser wallet';
}

function listInjectedProviders(){
  const eth=window.ethereum;
  if(!eth||typeof eth.request!=='function') return [];
  const raw=Array.isArray(eth.providers)&&eth.providers.length?eth.providers:[eth];
  const out=[];
  const seen=new Set();
  raw.forEach(p=>{
    if(!p||typeof p.request!=='function') return;
    const label=providerLabel(p);
    const key=label+(p===eth?'-main':'');
    if(seen.has(key)) return;
    seen.add(key);
    out.push({provider:p, label});
  });
  return out;
}

function hasInjectedWallet(){
  return listInjectedProviders().length>0;
}

function isMobileDevice(){
  const ua=navigator.userAgent||'';
  return /Android|iPhone|iPad|iPod|Mobile/i.test(ua);
}

async function loadWcConfig(){
  if(_wcReady!==null) return _wcReady;
  try{
    const h=await fetch('/api/health').then(r=>r.json());
    _wcProjectId=h.wc_project_id||'';
    _wcReady=!!_wcProjectId;
  }catch(_e){
    _wcReady=false;
  }
  return _wcReady;
}

async function abortWalletConnect(){
  try{ _wcProvider?.modal?.closeModal?.(); }catch(_e){}
  if(!_wcProvider) return;
  try{ await _wcProvider.disconnect(); }catch(_e){}
  _wcProvider=null;
}

function ensureWalletSheet(){
  let sheet=document.getElementById('walletsheet');
  if(sheet) return sheet;
  sheet=document.createElement('div');
  sheet.id='walletsheet';
  sheet.className='wallet-sheet';
  sheet.hidden=true;
  sheet.innerHTML=`<div class="wallet-sheet-card wallet-void" role="dialog" aria-labelledby="wallettitle">
    <button type="button" class="wallet-x" id="walletclose" aria-label="Close">×</button>
    <p class="kicker">access</p>
    <h2 id="wallettitle" class="wallet-h">connect <span>wallet</span></h2>
    <p class="wallet-tip" id="wallettip">On phone: Trust / MetaMask from the list, or open this site inside Trust Browser.</p>
    <div class="wallet-status">
      <div class="wallet-status-row"><span>wallet</span><span class="tag">ethereum</span></div>
      <p class="wallet-status-big" id="walletstatus">not linked</p>
      <p class="wallet-hint" id="walletdesc">Open the full wallet list (Trust, MetaMask, Rainbow, Coinbase, …) via WalletConnect. Chrome extension works too.</p>
    </div>
    <div class="wallet-list" id="walletlist"></div>
    <button type="button" class="btn ghost wallet-opt" id="walletcancel">Cancel</button>
  </div>`;
  document.body.appendChild(sheet);
  sheet.addEventListener('click',e=>{ if(e.target===sheet) closeWalletSheet(true); });
  document.getElementById('walletclose').onclick=()=>closeWalletSheet(true);
  document.getElementById('walletcancel').onclick=()=>{ abortWalletConnect(); closeWalletSheet(true); };
  return sheet;
}

function closeWalletSheet(cancelled){
  const sheet=document.getElementById('walletsheet');
  if(sheet) sheet.hidden=true;
  if(cancelled && _pickResolve){
    const done=_pickResolve;
    _pickResolve=null;
    done(null);
  }
}

function openWalletSheet(onPick){
  const sheet=ensureWalletSheet();
  const list=document.getElementById('walletlist');
  const injected=listInjectedProviders();
  const primary=injected[0];
  list.innerHTML='';
  const finish=choice=>{
    _pickResolve=null;
    closeWalletSheet(false);
    onPick(choice);
  };

  loadWcConfig().then(wcOk=>{
    list.innerHTML='';
    if(wcOk){
      const qr=document.createElement('button');
      qr.type='button';
      qr.className='btn acc wallet-opt wallet-primary';
      qr.innerHTML='<span class="wallet-opt-title">All wallets</span><span class="wallet-opt-sub">QR · Trust · MetaMask · Rainbow · Coinbase · 540+</span>';
      qr.onclick=()=>finish({mode:'qr'});
      list.appendChild(qr);
    }else{
      const miss=document.createElement('p');
      miss.className='wallet-hint';
      miss.innerHTML='WalletConnect QR needs a free Project ID from <a href="https://cloud.reown.com" target="_blank" rel="noopener">cloud.reown.com</a> in <code>WALLETCONNECT_PROJECT_ID</code>.';
      list.appendChild(miss);
    }
    if(primary){
      const ext=document.createElement('button');
      ext.type='button';
      ext.className='btn ghost wallet-opt';
      ext.innerHTML=`<span class="wallet-opt-title">Use ${primary.label}</span><span class="wallet-opt-sub">Installed Chrome / Brave extension</span>`;
      ext.onclick=()=>finish({mode:'injected', provider:primary.provider, label:primary.label});
      list.appendChild(ext);
    }
    injected.slice(1).forEach(({provider,label})=>{
      const b=document.createElement('button');
      b.type='button';
      b.className='btn ghost wallet-opt';
      b.textContent='Wallet · '+label;
      b.onclick=()=>finish({mode:'injected', provider, label});
      list.appendChild(b);
    });
    const local=document.createElement('button');
    local.type='button';
    local.className='btn ghost wallet-opt';
    local.innerHTML='<span class="wallet-opt-title">Browser key</span><span class="wallet-opt-sub">No popup — seat stays on this device</span>';
    local.onclick=()=>finish({mode:'local'});
    list.appendChild(local);
  });

  document.getElementById('walletstatus').textContent='not linked';
  sheet.hidden=false;
}

function pickWallet(){
  return new Promise(resolve=>{
    if(_pickResolve){
      _pickResolve(null);
      _pickResolve=null;
    }
    _pickResolve=resolve;
    openWalletSheet(choice=>{
      _pickResolve=null;
      resolve(choice);
    });
  });
}

async function connectWalletConnect(){
  await loadWcConfig();
  if(!_wcProjectId) throw new Error('Set WALLETCONNECT_PROJECT_ID in .env (free at cloud.reown.com)');
  const status=document.getElementById('walletstatus');
  if(status) status.textContent='waiting…';
  await abortWalletConnect();
  const mod=await import('https://esm.sh/@walletconnect/ethereum-provider@2.21.0');
  const EthereumProvider=mod.EthereumProvider||mod.default?.EthereumProvider||mod.default;
  if(!EthereumProvider?.init) throw new Error('WalletConnect failed to load. Check network / adblock.');
  _wcProvider=await EthereumProvider.init({
    projectId:_wcProjectId,
    showQrModal:true,
    chains:[1],
    optionalChains:[1],
    rpcMap:{1:'https://ethereum.publicnode.com'},
    qrModalOptions:{
      themeMode:'dark',
      themeVariables:{
        '--wcm-z-index':'200000',
        '--wcm-accent-color':'#3A63F5',
        '--wcm-background-color':'#0A0A0A'
      },
      enableExplorer:!isMobileDevice(),
      explorerRecommendedWalletIds:[
        '4622a2b2d6af1c9844944291e5e7351a6aa24cd7b23099efac1b2fd875da31a0',
        'c57ca95b47569778a828d19178114f4db188b89b763c899ba0be274e97267d96',
        '1ae92b26df02f0abca6304df07debccd18262fdf5fe82daa81593582dac9a369'
      ]
    },
    metadata:{
      name:'Ganglia',
      description:'One mind. 128 nodes.',
      url:location.origin,
      icons:[location.origin+'/assets/favicon.ico']
    }
  });
  await _wcProvider.enable();
  const accounts=_wcProvider.accounts?.length
    ? _wcProvider.accounts
    : await _wcProvider.request({method:'eth_accounts'});
  if(!accounts||!accounts[0]) throw new Error('No account from WalletConnect');
  _activeProvider=_wcProvider;
  return {provider:_wcProvider, address:accounts[0]};
}

async function injectedAddress(provider){
  const p=provider||_activeProvider||window.ethereum;
  if(!p) throw new Error('No wallet found.');
  _activeProvider=p;
  let accounts=[];
  try{ accounts=await p.request({method:'eth_accounts'}); }catch(_e){}
  if(accounts&&accounts[0]) return accounts[0];
  try{
    accounts=await p.request({method:'eth_requestAccounts'});
  }catch(err){
    const msg=String(err&&err.message||err||'');
    if(/already pending|requestPermissions/i.test(msg)){
      throw new Error('A wallet popup is already open. Close it, or use All wallets / Browser key.');
    }
    if(/rejected|denied|User rejected/i.test(msg)) throw new Error('Wallet request was cancelled.');
    throw err;
  }
  const address=accounts&&accounts[0];
  if(!address) throw new Error('No wallet account was returned.');
  return address;
}

async function signInjected(message, address, provider){
  const p=provider||_activeProvider||window.ethereum;
  return p.request({method:'personal_sign', params:[message, address]});
}

async function loginWithChoice(api, choice){
  if(!choice) return null;
  if(choice.mode==='local'){
    const me=await api('/api/auth/local',{method:'POST', body:JSON.stringify({secret:localSecret()})});
    setSessionKind('local');
    return me;
  }
  try{
    let provider, address;
    if(choice.mode==='qr'){
      ({provider, address}=await connectWalletConnect());
    }else{
      provider=choice.provider;
      address=await injectedAddress(provider);
    }
    const challenge=await api('/api/auth/nonce?address='+encodeURIComponent(address));
    const signature=await signInjected(challenge.message, address, provider);
    const me=await api('/api/auth/connect',{method:'POST', body:JSON.stringify({address:challenge.address, signature})});
    setSessionKind(choice.mode==='qr'?'wc':'injected');
    return me;
  }catch(err){
    const msg=String(err&&err.message||err||'');
    if(/already pending|requestPermissions|popup is already open/i.test(msg) && choice.mode!=='local'){
      const me=await api('/api/auth/local',{method:'POST', body:JSON.stringify({secret:localSecret()})});
      setSessionKind('local');
      return me;
    }
    throw err;
  }finally{
    const status=document.getElementById('walletstatus');
    if(status) status.textContent='not linked';
  }
}

function sessionKind(){
  return localStorage.getItem('ganglia_session_kind')||'';
}

function setSessionKind(kind){
  if(kind) localStorage.setItem('ganglia_session_kind', kind);
  else localStorage.removeItem('ganglia_session_kind');
}

function clearSessionKind(){
  setSessionKind('');
}

/**
 * Only react to MetaMask/extension account changes for injected sessions.
 * Ignore while connecting, and never for browser-key sessions.
 */
function bindAccountWatch(getAddress, onLost){
  const eth=window.ethereum;
  if(!eth||typeof eth.on!=='function') return;
  eth.on('accountsChanged', (accs)=>{
    if(_walletBusy) return;
    if(sessionKind()!=='injected') return;
    const current=(getAddress()||'').toLowerCase();
    if(!current) return;
    const next=(accs&&accs[0]||'').toLowerCase();
    if(next===current) return;
    onLost(next||null);
  });
}
