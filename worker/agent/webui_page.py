"""Worker 관리 화면의 HTML. 디자인은 웹(web/src/styles.css)을 기준으로 맞춘다."""

CSS = r'''
/* ===== 웹 styles.css 기준 (feat/frontend-redesign). 웹이 바뀌면 같이 수정 ===== */
*{box-sizing:border-box;margin:0;padding:0}
:root{--primary:#1f1f1f;--primary-dark:#000;--bg:#ffffff;--card:#ffffff;--text:#1f1f1f;--muted:#6b6b68;--border:#e8e8e5;--danger:#ef4444;--warning:#d97706;--success:#22c55e;--side-bg:#f9f9f8;--hover:#ececea;--active:#e8e8e5}
body{min-height:100vh;background:var(--bg);color:var(--text);font:14px/1.5 'Pretendard Variable','Pretendard',-apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif}
a{color:var(--text)}
h2{margin:0 0 12px;font-size:18px;letter-spacing:-.02em}
h3{margin:20px 0 8px;font-size:14px}
label{display:block;margin:12px 0 5px;color:var(--muted);font-size:12px;font-weight:600}
input{width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:8px;outline:0;background:#fff;color:var(--text);font:inherit}
input:focus{border-color:var(--primary)}
.card{margin-bottom:16px;padding:20px;border:1px solid var(--border);border-radius:12px;background:var(--card)}
.btn{display:inline-block;padding:9px 16px;border:1px solid transparent;border-radius:8px;background:var(--primary);color:#fff;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.btn:hover{background:var(--primary-dark)}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn.ghost{background:transparent;border-color:var(--border);color:inherit}
.btn.ghost:hover{background:var(--hover)}
.btn.danger{background:var(--danger)}
.btn.danger:hover{background:#dc2626}
.btn.sm{padding:5px 10px;font-size:12px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#f1f5f9;color:#475569}
.badge.online,.badge.available{background:#dcfce7;color:#15803d}
.badge.offline,.badge.stopped{background:#f1f5f9;color:#475569}
.badge.running{background:#dbeafe;color:#1d4ed8}
.badge.user_active,.badge.busy,.badge.overload,.badge.paused{background:#fef3c7;color:#b45309}
.muted{color:var(--muted);font-size:12px}
.row{display:flex;gap:10px;align-items:center}
.row input{flex:1}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.item{display:flex;gap:10px;align-items:center;justify-content:space-between;padding:12px 2px;border-bottom:1px solid var(--border)}
.item:last-child{border-bottom:0}
.item span{min-width:0;line-height:1.55}
.msg{min-height:20px;margin-top:10px;font-size:12px;font-weight:600}
.bad{color:var(--danger)}
progress{accent-color:var(--primary)}
pre{height:260px;overflow:auto;padding:14px;border:1px solid var(--border);border-radius:10px;background:#fafaf9;color:#3a3a38;font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}

/* 사이드바 (웹 .sidebar.side와 같은 구조) */
#appShell{min-height:100vh;display:flex}
.side{width:224px;flex:none;position:sticky;top:0;height:100vh;overflow-y:auto;display:flex;flex-direction:column;gap:2px;padding:12px 10px;border-right:1px solid var(--border);background:var(--side-bg)}
.side-brand{display:flex;align-items:center;gap:9px;padding:6px 10px 12px}
.side-brand strong{font-size:15px;font-weight:700}
.brand-mark{width:24px;height:24px;display:grid;place-items:center;border-radius:7px;background:var(--primary);color:#fff;font-size:12px;font-weight:800}
.side-section{padding:8px 10px 4px;color:var(--muted);font-size:12px}
.side nav{display:flex;flex-direction:column;gap:2px}
.side nav button{padding:9px 10px;border:0;border-radius:9px;background:none;color:var(--text);font:inherit;font-size:14px;text-align:left;cursor:pointer}
.side nav button:hover{background:var(--hover)}
.side nav button.active{background:var(--active);font-weight:600}
.side-spacer{flex:1;min-height:12px}
.side-status{display:grid;gap:6px;margin:8px 2px;padding:10px;border:1px solid var(--border);border-radius:12px;background:#fff}
.side-status-head{display:grid;justify-items:start;gap:6px;color:var(--muted);font-size:12px;font-weight:600}
.side-status p{color:var(--muted);font-size:12px;line-height:1.45}
.side-account{display:grid;gap:2px;padding:8px 10px 4px;border-top:1px solid var(--hover);font-size:12px}
.side-account strong{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.side-account span{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.side-account button{justify-self:start;margin-top:4px;padding:0;border:0;background:none;color:var(--text);font:inherit;font-size:12px;font-weight:600;text-decoration:underline;cursor:pointer}
main{flex:1;min-width:0;max-width:1100px;padding:36px 44px 52px}
.page{display:none}
.page.active{display:block}
.page-heading{margin-bottom:22px}
.page-heading h1{margin:0 0 6px;font-size:30px;letter-spacing:-.035em}
.page-heading p{color:var(--muted)}

/* ===== Worker 화면 고유 요소 ===== */
.metric{margin-top:6px;font-size:26px;font-weight:700}
.metric.small{font-size:18px}
.state-line{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.state-line p{color:var(--muted);font-size:13px}
.usage-bar{display:flex;height:8px;margin:10px 0 8px;border-radius:999px;background:#f0f0ee;overflow:hidden}
.usage-bar i{display:block;height:100%}
.usage-bar .mars{background:var(--primary)}
.usage-bar .other{background:#b9b9b4}
.usage-legend{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--muted);font-size:12px}
.usage-legend b{color:var(--text)}
.usage-legend i{display:inline-block;width:8px;height:8px;margin-right:5px;border-radius:2px;background:var(--primary)}
.usage-legend i.other{background:#b9b9b4}
.banner{display:none;margin-bottom:16px;padding:14px 16px;border:1px solid #fcd34d;border-radius:12px;background:#fffbeb;color:#92400e}
.banner.show{display:block}
.banner strong{display:block;margin-bottom:2px;font-size:14px}
.banner p{font-size:13px}
.banner .row{margin-top:10px;flex-wrap:wrap}
.hint{margin-top:12px;padding:10px 12px;border-radius:8px;background:#fafaf9;color:var(--muted);font-size:12px}

/* 로그인 */
.worker-auth{min-height:100vh;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(400px,.92fr)}
.worker-auth.shell-hidden{display:none}
.worker-auth:not(.shell-hidden)+#appShell{display:none}
.worker-auth-intro{padding:clamp(48px,9vw,120px) clamp(36px,8vw,120px);background:var(--primary);color:#fff}
.auth-brand{display:flex;align-items:center;gap:9px;margin-bottom:64px;font-size:18px;font-weight:700}
.auth-brand .brand-mark{background:#fff;color:var(--primary)}
.worker-auth-intro h1{margin:0 0 14px;font-size:clamp(28px,3.2vw,42px);letter-spacing:-.04em;line-height:1.2}
.worker-auth-intro>p{max-width:460px;color:#d6d6d2;line-height:1.7}
.worker-points{display:grid;gap:14px;margin-top:40px}
.worker-points div{display:flex;gap:12px}
.worker-points i{width:24px;height:24px;flex:none;display:grid;place-items:center;border:1px solid rgba(255,255,255,.35);border-radius:7px;font-size:12px;font-style:normal;font-weight:700}
.worker-points strong,.worker-points small{display:block}
.worker-points small{margin-top:2px;color:#c4c4bf;font-size:12px}
.worker-auth-form{display:grid;place-items:center;padding:36px}
.worker-auth-card{width:min(100%,380px)}
.worker-auth-card h2{margin:0 0 6px;font-size:24px}
.worker-auth-card>p{color:var(--muted);font-size:13px}
.worker-auth-card form{margin-top:22px}
.worker-auth-card .btn{width:100%;margin-top:20px;padding:12px}
.worker-specs{margin-top:12px;padding:10px;border-radius:8px;background:#fafaf9;color:var(--muted);font-size:12px;line-height:1.5}
@media(max-width:760px){
  .worker-auth{grid-template-columns:1fr}.worker-auth-intro{padding:32px 24px}.auth-brand{margin-bottom:32px}.worker-points{display:none}.worker-auth-form{padding:36px 22px}
  #appShell{flex-direction:column}.side{position:static;height:auto;width:auto;border-right:0;border-bottom:1px solid var(--border)}.side nav{flex-direction:row;flex-wrap:wrap}.side-spacer{display:none}
  main{padding:24px 16px 40px}.row{flex-wrap:wrap}.item{align-items:flex-start}
}
'''

BODY = r'''
<section id="workerLogin" class="worker-auth">
  <div class="worker-auth-intro">
    <div class="auth-brand"><span class="brand-mark">M</span> M.A.R.S 워커</div>
    <h1>이 컴퓨터를<br>내 AI 팀에 연결해요.</h1>
    <p>이 기기를 M.A.R.S 워커로 등록하면, 쓰지 않는 동안 남는 자원으로 워크플로우 작업을 나눠 처리해요.</p>
    <div class="worker-points">
      <div><i>1</i><span><strong>워커 전용 연결</strong><small>웹 로그인과 별개로, 이 기기를 등록하는 화면이에요.</small></span></div>
      <div><i>2</i><span><strong>이 기기의 자원 사용</strong><small>CPU·GPU와 여기에 설치한 Ollama 모델로 실행해요.</small></span></div>
      <div><i>3</i><span><strong>고른 폴더만 공유</strong><small>직접 등록한 폴더만 작업에서 읽을 수 있어요.</small></span></div>
    </div>
  </div>
  <div class="worker-auth-form"><div class="worker-auth-card">
    <h2>워커 등록</h2><p>M.A.R.S 계정으로 로그인해 이 기기를 워커로 연결해요.</p>
    <form id="workerLoginForm">
      <label for="server">서버 주소</label><input id="server" value="https://marsflowlab.com/api" required>
      <label for="name">워커 이름</label><input id="name" required>
      <label for="user">아이디</label><input id="user" required autocomplete="username">
      <label for="pass">비밀번호</label><input id="pass" type="password" required autocomplete="current-password">
      <div id="specs" class="worker-specs"></div><p id="setupMsg" class="msg"></p>
      <button id="register" class="btn" type="submit">워커 연결하기</button>
    </form>
  </div></div>
</section>
<div id="appShell">
  <aside class="side">
    <div class="side-brand"><span class="brand-mark">M</span><strong>M.A.R.S 워커</strong></div>
    <nav aria-label="워커 관리 메뉴">
      <button data-p="status" class="active">상태</button>
      <button data-p="setup">연결·설정</button>
      <button data-p="models">모델</button>
      <button data-p="tools">도구</button>
    </nav>
    <div class="side-spacer"></div>
    <div class="side-status" aria-live="polite">
      <div class="side-status-head"><span>지금 상태</span><span id="sideBadge" class="badge">확인 중</span></div>
      <p id="sideReason"></p>
    </div>
    <div class="side-account">
      <strong id="accountName">-</strong><span id="accountEmail"></span><span id="accountServer"></span>
      <button id="switchAccount" type="button">계정 바꾸기</button>
    </div>
  </aside>
  <main>
    <div id="overloadBanner" class="banner" role="alert">
      <strong>과부하 경고</strong><p id="overloadReason"></p>
      <p id="overloadCountdown"></p>
      <div class="row"><button id="overloadContinue" class="btn sm ghost" type="button">계속 실행</button><button id="overloadRelease" class="btn sm" type="button">다른 기기로 넘기기</button></div>
    </div>
    <div id="pausedBanner" class="banner">
      <strong id="pausedTitle">일시 중지</strong><p>작업을 다른 기기로 넘겨서 잠시 새 작업을 받지 않아요.</p>
      <div class="row"><button id="resume" class="btn sm ghost" type="button">지금 다시 받기</button></div>
    </div>

    <section id="status" class="page active">
      <div class="page-heading"><h1>상태</h1><p>이 워커가 지금 작업을 받을 수 있는지와 그 이유를 보여줘요.</p></div>
      <div class="card">
        <div class="state-line"><span id="badge" class="badge">확인 중</span><p id="reason"></p></div>
        <div class="row" style="margin-top:14px"><button id="start" class="btn" type="button">시작</button><button id="stop" class="btn ghost" type="button">중지</button></div>
        <div class="hint">작업을 받는 기준(CPU·GPU 상한, 자리 비움 기준, 과부하일 때 동작)은 웹의 워커 설정에서 바꿔요. <a id="webLink" href="#" target="_blank" rel="noreferrer">웹에서 워커 설정 열기</a><br><span id="limitSummary"></span></div>
      </div>
      <div class="grid">
        <div class="card"><b>CPU</b><div id="cpu" class="metric">-</div>
          <div class="usage-bar" aria-hidden="true"><i id="cpuMars" class="mars"></i><i id="cpuOther" class="other"></i></div>
          <div class="usage-legend"><span><i></i>M.A.R.S. <b id="cpuMarsText">-</b></span><span><i class="other"></i>다른 프로그램 <b id="cpuOtherText">-</b></span></div>
        </div>
        <div class="card"><b>RAM</b><div id="ram" class="metric">-</div></div>
        <div class="card"><b>GPU</b><div id="gpu" class="metric">-</div><p id="gpuName" class="muted"></p></div>
        <div class="card"><b>마지막 입력</b><div id="idle" class="metric small">-</div><p class="muted">키보드·마우스를 마지막으로 쓴 뒤 지난 시간이에요.</p></div>
      </div>
      <div class="card"><h2>실행 중인 작업</h2><div id="homeTask" class="metric small">대기 중</div><p id="homeTaskDetail" class="muted"></p></div>
      <div class="card"><h2>최근 기록</h2><pre id="logs">기록이 없어요.</pre></div>
    </section>

    <section id="setup" class="page">
      <div class="page-heading"><h1>연결·설정</h1><p>이 기기의 이름과 연결, 작업에서 읽을 폴더를 관리해요.</p></div>
      <div class="card"><h2>연결 정보</h2><label>워커 이름</label><div id="homeDeviceName" class="metric small">-</div>
        <label for="settingsName">이름 바꾸기</label><div class="row"><input id="settingsName" maxlength="128" placeholder="새 워커 이름"><button id="rename" class="btn" type="button">이름 저장</button></div><p id="settingsMsg" class="msg"></p>
        <h3>연결 관리</h3><div class="row"><button id="logout" class="btn ghost" type="button">로그아웃</button><button id="unregister" class="btn danger" type="button">워커 등록 해제</button></div>
        <p class="muted" style="margin-top:8px">로그아웃은 이 프로그램의 인증 정보만 지워요. 등록 해제는 웹의 워커 목록에서도 이 기기를 삭제해요.</p></div>
      <div class="card"><h2>등록한 폴더</h2><div class="row"><input id="folder" placeholder="이 기기의 폴더 절대 경로"><button id="add" class="btn" type="button">추가</button></div><div id="folders"></div></div>
    </section>

    <section id="models" class="page">
      <div class="page-heading"><h1>모델</h1><p>이 기기의 Ollama에 설치된 모델을 관리해요.</p></div>
      <div class="card"><h2>Ollama</h2><div id="ollamaInstall"></div><h3>공식 라이브러리 검색</h3><div class="row"><input id="model" placeholder="예: qwen, coding, vision"><button id="search" class="btn" type="button">검색</button><button id="refresh" class="btn ghost" type="button">설치된 모델</button></div><p id="modelMsg" class="msg"></p><div id="searchList"></div><h3>설치된 모델</h3><div id="modelList"></div></div>
      <div class="card"><h2>내려받기 상태</h2><div id="jobs"></div></div>
    </section>

    <section id="tools" class="page">
      <div class="page-heading"><h1>도구</h1><p>문서를 읽는 데 필요한 추가 도구예요. 아래 허용 목록만 설치해요.</p></div>
      <div class="card"><h2>허용된 도구</h2><div id="toolList"></div><h3>설치 상태</h3><div id="toolJobs"></div></div>
    </section>
  </main>
</div>
'''

SCRIPT = r'''
const $=s=>document.querySelector(s), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),api=async(p,o={})=>{let r=await fetch(p,{headers:{'Content-Type':'application/json'},...o}),d=r.status===204?{}:await r.json();if(!r.ok)throw Error(d.error||'요청 실패');return d};let S={};
const post=(p,b={})=>api(p,{method:'POST',body:JSON.stringify(b)});
const pct=v=>v==null?'-':Math.round(v)+'%';
function ago(sec){if(sec==null)return '측정할 수 없음';if(sec<60)return Math.round(sec)+'초 전';if(sec<3600)return Math.floor(sec/60)+'분 전';return Math.floor(sec/3600)+'시간 전'}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.page').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#'+b.dataset.p).classList.add('active');if(b.dataset.p==='models')models();if(b.dataset.p==='tools')tools()});
function limitSummary(l){l=l||{};let parts=[];parts.push('CPU 상한 '+(l.max_cpu_percent?l.max_cpu_percent+'%':'없음'));parts.push('GPU 상한 '+(l.max_gpu_percent?l.max_gpu_percent+'%':'없음'));parts.push('자리 비움 기준 '+(l.min_user_idle_min?l.min_user_idle_min+'분':'꺼짐'));parts.push('과부하일 때 '+({ask:'물어보기',continue:'계속 실행',release:'바로 넘기기'}[l.on_overload||'ask']));return '지금 설정: '+parts.join(' · ')}
async function status(){try{S=await api('/api/status');
  let b=S.badge||{key:'stopped',label:'확인 중',reason:''};
  for(const id of ['#badge','#sideBadge']){$(id).className='badge '+b.key;$(id).textContent=b.label}
  $('#reason').textContent=b.reason;$('#sideReason').textContent=b.reason;
  $('#server').value=S.server_url||$('#server').value;let name=$('#name');if(!name.value)name.value=S.device_name||S.specs.hostname||'';
  $('#homeDeviceName').textContent=S.device_name||'-';if(document.activeElement!==$('#settingsName'))$('#settingsName').value=S.device_name||'';
  $('#homeTask').textContent=S.current_task?'#'+S.current_task.task_id+' '+S.current_task.agent_name:'대기 중';
  $('#homeTaskDetail').textContent=S.current_task?(S.current_task.label||'실행 #'+S.current_task.execution_id)+' · '+(S.current_task.model||'기본 모델'):S.running?'새 작업을 기다리고 있어요.':'워커가 꺼져 있어요.';
  $('#specs').textContent=Object.entries(S.specs).filter(x=>typeof x[1]!=='object').map(x=>x.join(': ')).join(' · ');
  let st=S.stats;$('#cpu').textContent=pct(st.cpu_percent);$('#cpuMars').style.width=Math.min(100,st.mars_cpu_percent||0)+'%';$('#cpuOther').style.width=Math.min(100,st.other_cpu_percent||0)+'%';$('#cpuMarsText').textContent=pct(st.mars_cpu_percent);$('#cpuOtherText').textContent=pct(st.other_cpu_percent);
  $('#ram').textContent=pct(st.ram_percent);$('#gpu').textContent=st.gpu_percent==null?'감지 안 됨':pct(st.gpu_percent);$('#gpuName').textContent=(st.gpu_devices||[]).map(g=>g.name).join(', ')||'장치 없음';$('#idle').textContent=ago(st.user_idle_sec);
  $('#logs').textContent=S.logs.join('\n')||'기록이 없어요.';
  let a=S.account;$('#accountName').textContent=a?a.username:'계정 확인 중';$('#accountEmail').textContent=a?a.email:'워커를 시작하면 표시돼요';$('#accountServer').textContent=S.server_url||'';$('#accountServer').title=S.server_url||'';
  $('#webLink').href=S.web_url||'#';$('#webLink').style.display=S.web_url?'':'none';$('#limitSummary').textContent=limitSummary(S.limits);
  let o=S.overload;$('#overloadBanner').classList.toggle('show',!!o);if(o){$('#overloadReason').textContent=o.reason+'. 이 기기에서 계속 실행할지, 다른 기기로 넘길지 골라 주세요.';let left=Math.max(0,Math.round(o.deadline-Date.now()/1000));$('#overloadCountdown').textContent=o.decision?'선택을 전달하고 있어요…':left+'초 안에 고르지 않으면 계속 실행해요.'}
  $('#pausedBanner').classList.toggle('show',b.key==='paused');if(b.key==='paused')$('#pausedTitle').textContent=b.label;
  if(S.notice){$('#setupMsg').className='msg bad';$('#setupMsg').textContent=S.notice}
  $('#workerLogin').classList.toggle('shell-hidden',S.registered);folders()}catch(e){$('#badge').textContent='화면 오류';$('#reason').textContent=e.message}}
function folders(){$('#folders').innerHTML=(S.shared_folders||[]).map((x,i)=>`<div class="item"><span>${esc(x)}</span><button class="btn sm danger" onclick="removeFolder(${i})">삭제</button></div>`).join('')||'<p class="muted" style="margin-top:10px">등록한 폴더가 없어요.</p>'}async function save(f){try{await post('/api/folders',{folders:f});status()}catch(e){alert(e.message)}}window.removeFolder=i=>save(S.shared_folders.filter((_,n)=>n!==i));$('#add').onclick=()=>{let v=$('#folder').value.trim();if(v)save([...(S.shared_folders||[]),v]);$('#folder').value=''};
$('#workerLoginForm').onsubmit=async e=>{e.preventDefault();try{$('#setupMsg').className='msg';$('#setupMsg').textContent='등록하는 중…';await post('/api/register',{server_url:$('#server').value,username:$('#user').value,password:$('#pass').value,device_name:$('#name').value});$('#pass').value='';$('#setupMsg').textContent='등록했어요';status()}catch(e){$('#setupMsg').textContent=e.message;$('#setupMsg').className='msg bad'}};
$('#rename').onclick=async()=>{try{let name=$('#settingsName').value.trim();if(!name)throw Error('워커 이름을 입력하세요.');await post('/api/settings/name',{name});$('#settingsMsg').className='msg';$('#settingsMsg').textContent='이름을 바꿨어요.';status()}catch(e){$('#settingsMsg').className='msg bad';$('#settingsMsg').textContent=e.message}};
async function logout(question){if(confirm(question)){try{await post('/api/logout');location.reload()}catch(e){alert(e.message)}}}
$('#logout').onclick=()=>logout('이 프로그램에서 로그아웃할까요? 서버의 워커 등록은 그대로 남아요.');
$('#switchAccount').onclick=()=>logout('다른 계정으로 바꾸려면 로그아웃한 뒤 다시 로그인해요. 계속할까요?');
$('#unregister').onclick=async()=>{if(confirm('웹의 워커 목록에서 이 기기를 삭제할까요? 되돌릴 수 없어요.')){try{await post('/api/unregister');location.reload()}catch(e){$('#settingsMsg').className='msg bad';$('#settingsMsg').textContent=e.message}}};
$('#overloadContinue').onclick=async()=>{await post('/api/overload',{decision:'continue'});status()};
$('#overloadRelease').onclick=async()=>{await post('/api/overload',{decision:'release'});status()};
$('#resume').onclick=async()=>{try{await post('/api/resume');status()}catch(e){alert(e.message)}};
async function models(){try{let d=await api('/api/models');$('#modelMsg').className='msg';$('#modelMsg').textContent='Ollama에 연결됐어요';$('#ollamaInstall').innerHTML='';$('#modelList').innerHTML=(d.models||[]).map(m=>`<div class="item"><b>${esc(m.name)}</b><button class="btn sm danger" onclick="delModel('${esc(m.name)}')">삭제</button></div>`).join('')||'<p class="muted">설치된 모델이 없어요.</p>'}catch(e){let i=await api('/api/ollama/install');$('#modelMsg').textContent='Ollama가 실행 중이 아니에요.';$('#modelMsg').className='msg bad';$('#ollamaInstall').innerHTML=`<p>${esc(i.instructions)}</p><p style="margin-top:8px"><a class="btn" href="${i.download_url}" target="_blank">Ollama 공식 내려받기</a></p>`}}window.delModel=async n=>{if(confirm(n+' 모델을 삭제할까요?')){await post('/api/models/delete',{name:n});models()}};window.pullModel=async n=>{await post('/api/models/pull',{name:n});jobs()};$('#refresh').onclick=models;$('#search').onclick=async()=>{try{$('#modelMsg').className='msg';$('#modelMsg').textContent='공식 라이브러리를 검색하는 중…';let d=await api('/api/models/search?q='+encodeURIComponent($('#model').value));$('#searchList').innerHTML=d.models.map(m=>`<div class="item"><span><b>${esc(m.name)}</b> <small class="muted">${esc(m.performance)} ${esc(m.tags.join(' · '))}</small><br>${esc(m.description)}<br><a href="${m.url}" target="_blank" class="muted">자세히</a></span><button class="btn sm" onclick="pullModel('${esc(m.name)}')">내려받기</button></div>`).join('')||'<p class="muted">검색 결과가 없어요.</p>';$('#modelMsg').textContent='모델 '+d.models.length+'개'}catch(e){$('#modelMsg').textContent=e.message}};
const JOB_STATUS={pending:'대기',running:'진행 중',done:'완료',failed:'실패'};
const jobRow=(j,extra='')=>`<div class="item"><span><b>${esc(j.label)}</b><br><small class="${j.status==='failed'?'bad':'muted'}">${esc(j.error||j.message)} · ${j.percent||0}%</small><br><progress max="100" value="${j.percent||0}" style="width:280px;max-width:100%"></progress></span><span><b>${esc(JOB_STATUS[j.status]||j.status)}</b>${extra}</span></div>`;
async function jobs(){let d=await api('/api/jobs');$('#jobs').innerHTML=d.jobs.map(j=>jobRow(j)).join('')||'<p class="muted">내려받은 기록이 없어요.</p>'}
async function toolJobs(){let d=await api('/api/jobs'),items=d.jobs.filter(j=>j.kind==='tool');$('#toolJobs').innerHTML=items.map(j=>jobRow(j,j.status==='failed'&&j.tool_id?` <button class="btn sm" onclick="installTool('${esc(j.tool_id)}',true)">다시 설치</button>`:'')).join('')||'<p class="muted">도구 설치 기록이 없어요.</p>'}
async function tools(){let d=await api('/api/tools');$('#toolList').innerHTML=d.tools.map(t=>`<div class="item"><span><b>${esc(t.name)}</b><br><small class="muted">${t.installed?'설치됨':'설치 필요'}</small></span><button class="btn sm ${t.installed?'ghost':''}" onclick="installTool('${esc(t.id)}',${t.installed})">${t.installed?'다시 설치':'설치'}</button></div>`).join('');toolJobs()}window.installTool=async(id,reinstall=false)=>{if(confirm('허용된 패키지를 '+(reinstall?'다시 설치':'설치')+'할까요?')){try{await post('/api/tools/install',{id,reinstall});toolJobs()}catch(e){alert(e.message);toolJobs()}}};
$('#start').onclick=async()=>{try{await post('/api/worker/start')}catch(e){alert(e.message)}status()};$('#stop').onclick=async()=>{await post('/api/worker/stop');status()};
status();setInterval(()=>{status();jobs();tools()},2000);
'''

HTML = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>M.A.R.S 워커</title><style>' + CSS + '</style></head><body>' + BODY + '<script>' + SCRIPT + '</script></body></html>')
