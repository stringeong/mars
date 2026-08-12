"""Localhost-only web management screen for M.A.R.S Worker."""
import os, importlib.util, json, platform, shutil, subprocess, sys, threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import httpx
from . import config as cfg
from .main import collect_runtime_stats, collect_specs
from .downloads import create_job, get_jobs, ollama_install_info, pull_model, search_library

PROCESS = None
LOGS = deque(maxlen=200)
TOOLS = ({"id":"pdf-ocr","name":"PDF & OCR","packages":["pypdf","pytesseract"],"modules":["pypdf","pytesseract"],"binary":"tesseract"},{"id":"office","name":"Office 문서","packages":["python-docx","openpyxl","python-pptx"],"modules":["docx","openpyxl","pptx"]},{"id":"git","name":"Git CLI","packages":[],"modules":[],"binary":"git"})
HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>M.A.R.S Worker</title><style>
*{box-sizing:border-box}body{margin:0;background:#09111e;color:#e7edf8;font:15px system-ui}header,main,nav{max-width:1050px;margin:auto;padding:22px}header{display:flex;justify-content:space-between}h1{margin:0}.muted{color:#91a2bb}nav{display:flex;gap:8px;padding-top:0;border-bottom:1px solid #25344b}button{border:0;border-radius:8px;padding:10px 14px;background:#16859c;color:white;font-weight:650;cursor:pointer}nav button{background:transparent;color:#91a2bb}.active{color:white!important;background:#17263b!important}.page{display:none}.page.active{display:block}.card{background:#111d30;border:1px solid #293950;border-radius:14px;padding:20px;margin-bottom:16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:15px}label{display:block;margin:11px 0 5px;color:#a9b6c9}input{width:100%;padding:11px;background:#08121f;border:1px solid #354761;border-radius:8px;color:white}.row,.item{display:flex;gap:10px;align-items:center}.row input{flex:1}.item{justify-content:space-between;padding:12px 0;border-bottom:1px solid #293950}.danger{background:#a43d55}.metric{font-size:28px;font-weight:750}pre{height:260px;overflow:auto;background:#060c14;padding:14px;white-space:pre-wrap}.msg{color:#62d9ed;min-height:22px}.bad{color:#fb7185}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#64748b}.dot.on{background:#34d399;box-shadow:0 0 10px #34d399}</style></head><body>
<header><div><h1>M.A.R.S Worker</h1><span class="muted">Local control center</span></div><div><i id="dot" class="dot"></i> <span id="state">확인 중</span></div></header><nav><button data-p="setup" class="active">Setup</button><button data-p="models">Models</button><button data-p="tools">Tools</button><button data-p="status">Status</button></nav><main>
<section id="setup" class="page active"><div class="card"><h2>서버 연결 및 등록</h2><div class="grid"><div><label>서버 주소</label><input id="server" value="http://localhost:8000"><label>아이디</label><input id="user"><label>비밀번호</label><input id="pass" type="password"></div><div><label>Worker 이름</label><input id="name"><label>기기 정보</label><p id="specs" class="muted"></p><button id="register">로그인 및 등록</button></div></div><p id="setupMsg" class="msg"></p></div><div class="card"><h2>공유 디렉터리</h2><div class="row"><input id="folder" placeholder="로컬 디렉터리 절대 경로"><button id="add">추가</button></div><div id="folders"></div></div></section>
<section id="models" class="page"><div class="card"><h2>Ollama</h2><div id="ollamaInstall"></div><h3>공식 라이브러리 검색</h3><div class="row"><input id="model" placeholder="예: qwen, coding, vision"><button id="search">검색</button><button id="refresh">설치 모델</button></div><p id="modelMsg" class="msg"></p><div id="searchList"></div><h3>설치된 모델</h3><div id="modelList"></div></div><div class="card"><h2>다운로드 상태</h2><div id="jobs"></div></div></section>
<section id="tools" class="page"><div class="card"><h2>승인된 Tool 카탈로그</h2><p class="muted">임의 명령 대신 아래 허용 목록만 설치합니다.</p><div id="toolList"></div><h3>설치 상태</h3><div id="toolJobs"></div></div></section>
<section id="status" class="page"><div class="grid"><div class="card"><b>CPU</b><div id="cpu" class="metric">-</div></div><div class="card"><b>RAM</b><div id="ram" class="metric">-</div></div><div class="card"><b>GPU</b><div id="gpu" class="metric">-</div></div></div><div class="card"><h2>Worker</h2><button id="start">시작</button> <button id="stop" class="danger">중지</button></div><div class="card"><h2>최근 로그</h2><pre id="logs">로그가 없습니다.</pre></div></section></main><script>
const $=s=>document.querySelector(s), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),api=async(p,o={})=>{let r=await fetch(p,{headers:{'Content-Type':'application/json'},...o}),d=await r.json();if(!r.ok)throw Error(d.error||'요청 실패');return d};let S={};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.page').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#'+b.dataset.p).classList.add('active');if(b.dataset.p==='models')models();if(b.dataset.p==='tools')tools()});
async function status(){try{S=await api('/api/status');$('#dot').className='dot '+(S.running?'on':'');$('#state').textContent=S.running?'실행 중':S.registered?'등록됨 · 중지':'등록 필요';$('#server').value=S.server_url||$('#server').value;$('#name').value=S.device_name||navigator.platform;$('#specs').textContent=Object.entries(S.specs).map(x=>x.join(': ')).join(' · ');$('#cpu').textContent=S.stats.cpu_percent+'%';$('#ram').textContent=S.stats.ram_percent+'%';$('#gpu').textContent=S.stats.gpu_percent==null?'감지 안 됨':S.stats.gpu_percent+'%';$('#logs').textContent=S.logs.join('\n')||'로그가 없습니다.';folders()}catch(e){$('#state').textContent='API 오류'}}
function folders(){$('#folders').innerHTML=(S.allowed_folders||[]).map((x,i)=>`<div class="item"><span>${esc(x)}</span><button class="danger" onclick="removeFolder(${i})">삭제</button></div>`).join('')||'<p class="muted">등록된 디렉터리가 없습니다.</p>'}async function save(f){try{await api('/api/folders',{method:'POST',body:JSON.stringify({folders:f})});status()}catch(e){alert(e.message)}}window.removeFolder=i=>save(S.allowed_folders.filter((_,n)=>n!==i));$('#add').onclick=()=>{let v=$('#folder').value.trim();if(v)save([...(S.allowed_folders||[]),v]);$('#folder').value=''};
$('#register').onclick=async()=>{try{$('#setupMsg').textContent='등록 중…';await api('/api/register',{method:'POST',body:JSON.stringify({server_url:$('#server').value,username:$('#user').value,password:$('#pass').value,device_name:$('#name').value})});$('#pass').value='';$('#setupMsg').textContent='등록 완료';status()}catch(e){$('#setupMsg').textContent=e.message;$('#setupMsg').className='msg bad'}};
async function models(){try{let d=await api('/api/models');$('#modelMsg').textContent='Ollama 연결됨';$('#ollamaInstall').innerHTML='';$('#modelList').innerHTML=(d.models||[]).map(m=>`<div class="item"><b>${esc(m.name)}</b><button class="danger" onclick="delModel('${esc(m.name)}')">삭제</button></div>`).join('')||'<p class="muted">설치된 모델 없음</p>'}catch(e){let i=await api('/api/ollama/install');$('#modelMsg').textContent='Ollama가 실행 중이 아닙니다.';$('#modelMsg').className='msg bad';$('#ollamaInstall').innerHTML=`<p>${esc(i.instructions)}</p><p><a href="${i.download_url}" target="_blank"><button>Ollama 공식 다운로드</button></a></p>`}}window.delModel=async n=>{if(confirm(n+' 삭제?')){await api('/api/models/delete',{method:'POST',body:JSON.stringify({name:n})});models()}};window.pullModel=async n=>{await api('/api/models/pull',{method:'POST',body:JSON.stringify({name:n})});jobs()};$('#refresh').onclick=models;$('#search').onclick=async()=>{try{$('#modelMsg').textContent='공식 라이브러리 검색 중…';let d=await api('/api/models/search?q='+encodeURIComponent($('#model').value));$('#searchList').innerHTML=d.models.map(m=>`<div class="item"><span><b>${esc(m.name)}</b> <small class="muted">${esc(m.performance)} ${esc(m.tags.join(' · '))}</small><br>${esc(m.description)}<br><a href="${m.url}" target="_blank" class="muted">상세 정보</a></span><button onclick="pullModel('${esc(m.name)}')">다운로드</button></div>`).join('')||'<p class="muted">검색 결과가 없습니다.</p>';$('#modelMsg').textContent=d.models.length+'개 모델'}catch(e){$('#modelMsg').textContent=e.message}};
async function jobs(){let d=await api('/api/jobs');$('#jobs').innerHTML=d.jobs.map(j=>`<div class="item"><span><b>${esc(j.label)}</b><br><small class="${j.status==='failed'?'bad':'muted'}">${esc(j.error||j.message)} · ${j.percent||0}%</small><br><progress max="100" value="${j.percent||0}" style="width:280px;max-width:100%"></progress></span><b>${esc(j.status)}</b></div>`).join('')||'<p class="muted">다운로드 내역이 없습니다.</p>'}
setInterval(()=>{let t=$("#toolJobs"),j=$("#jobs");if(t&&j)t.innerHTML=j.innerHTML},500);
async function tools(){let d=await api('/api/tools');$('#toolList').innerHTML=d.tools.map(t=>`<div class="item"><span><b>${t.name}</b><br><small class="muted">${t.installed?'설치됨':'설치 필요'}</small></span><button ${t.installed?'disabled':''} onclick="installTool('${t.id}')">설치</button></div>`).join('')}window.installTool=async id=>{if(confirm('승인된 패키지를 설치할까요?')){await api('/api/tools/install',{method:'POST',body:JSON.stringify({id})});jobs()}};$('#start').onclick=async()=>{await api('/api/worker/start',{method:'POST',body:'{}'});status()};$('#stop').onclick=async()=>{await api('/api/worker/stop',{method:'POST',body:'{}'});status()};status();setInterval(()=>{status();jobs()},2000);
</script></body></html>'''.replace('\n+','\n')

def tool_states():
    return [{**t,"installed":all(importlib.util.find_spec(m) for m in t["modules"]) and (not t.get("binary") or bool(shutil.which(t["binary"])))} for t in TOOLS]
def watch(p):
    for line in p.stdout: LOGS.append(line.rstrip())

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body)
    def body(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))) or b"{}")
    def do_GET(self):
        try:
            if self.path=="/":
                b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Content-Security-Policy","default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'");self.end_headers();self.wfile.write(b);return
            c=cfg.load()
            if self.path=="/api/status": self.reply({"registered":bool(c.get("api_key")),"running":bool(PROCESS and PROCESS.poll() is None),"server_url":c["server_url"],"device_name":c["device_name"],"allowed_folders":c.get("allowed_folders",[]),"specs":collect_specs(),"stats":collect_runtime_stats(),"logs":list(LOGS)});return
            if self.path=="/api/models": r=httpx.get(c["ollama_url"].rstrip('/')+'/api/tags',timeout=5);r.raise_for_status();self.reply(r.json());return
            if self.path=="/api/ollama/install": self.reply(ollama_install_info());return
            if self.path=="/api/jobs": self.reply({"jobs":get_jobs()});return
            if self.path.startswith("/api/models/search"):
                from urllib.parse import parse_qs
                query=parse_qs(urlparse(self.path).query).get("q",[""])[0];self.reply({"models":search_library(query)});return
            if self.path=="/api/tools": self.reply({"tools":tool_states()});return
            self.reply({"error":"Not found"},404)
        except Exception as e:self.reply({"error":str(e)},503)
    def do_POST(self):
        global PROCESS
        origin=self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in {"127.0.0.1","localhost","::1"}:self.reply({"error":"localhost만 허용됩니다."},403);return
        try:
            d=self.body();c=cfg.load()
            if self.path=="/api/register":
                server=str(d.get("server_url","")).rstrip('/');user=str(d.get("username","")).strip();password=str(d.get("password","")).strip()
                if not all((server,user,password)):raise ValueError("서버 주소, 아이디, 비밀번호를 입력하세요.")
                r=httpx.post(server+'/auth/login',data={"username":user,"password":password},timeout=15);r.raise_for_status();name=str(d.get("device_name","")).strip() or platform.node() or "내 기기";r=httpx.post(server+'/devices',json={"name":name,"specs":collect_specs()},headers={"Authorization":'Bearer '+r.json()["access_token"]},timeout=15);r.raise_for_status();x=r.json();c.update(server_url=server,device_id=x["id"],device_name=x["name"],api_key=x["api_key"]);cfg.save(c);LOGS.append('기기 등록 완료: '+x["name"]);self.reply({"ok":True});return
            if self.path=="/api/folders":
                folders=[]
                for raw in d.get("folders",[]):
                    p=Path(raw).expanduser().resolve()
                    if not p.is_dir():raise ValueError('존재하지 않는 디렉터리: '+str(raw))
                    if str(p) not in folders:folders.append(str(p))
                c["allowed_folders"]=folders;cfg.save(c);self.reply({"folders":folders});return
            if self.path=="/api/worker/start":
                if not c.get("api_key"):raise ValueError("먼저 Worker를 등록하세요.")
                if not PROCESS or PROCESS.poll() is not None:PROCESS=subprocess.Popen([sys.executable,'-m','agent','run'],cwd=str(Path(__file__).parents[1]),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1);threading.Thread(target=watch,args=(PROCESS,),daemon=True).start()
                self.reply({"ok":True});return
            if self.path=="/api/worker/stop":
                if PROCESS and PROCESS.poll() is None:PROCESS.terminate();PROCESS.wait(timeout=8);LOGS.append('Worker 중지')
                self.reply({"ok":True});return
            if self.path in {"/api/models/pull","/api/models/delete"}:
                name=str(d.get("name","")).strip()
                if not name:raise ValueError("모델 이름을 입력하세요.")
                if self.path.endswith("pull"):
                    job=create_job("model",name,lambda job_id:pull_model(c["ollama_url"],name,job_id));self.reply({"job":job},202);return
                r=httpx.request("DELETE",c["ollama_url"].rstrip("/")+"/api/delete",json={"name":name},timeout=30);r.raise_for_status();self.reply({"ok":True});return
            if self.path=="/api/tools/install":
                t=next((x for x in TOOLS if x["id"]==d.get("id")),None)
                if not t:raise ValueError("승인되지 않은 Tool입니다.")
                def install(job_id):
                    if t["packages"]:
                        p=subprocess.run([sys.executable,"-m","pip","install",*t["packages"]],capture_output=True,text=True,timeout=600)
                        if p.returncode:raise RuntimeError(p.stderr[-2000:] or "패키지 설치 실패")
                    if t.get("binary") and not shutil.which(t["binary"]):raise RuntimeError(t["binary"]+"는 Docker Worker 이미지에 포함되어 있습니다. Docker 방식으로 실행하세요.")
                job=create_job("tool",t["name"],install);self.reply({"job":job},202);return
            self.reply({"error":"Not found"},404)
        except httpx.HTTPStatusError as e:self.reply({"error":e.response.text or str(e)},400)
        except Exception as e:self.reply({"error":str(e)},400)

def serve(host='127.0.0.1',port=8765):
    if host not in {'127.0.0.1','localhost','::1'} and os.getenv('MARS_ALLOW_CONTAINER_BIND') != '1':raise ValueError('관리 UI는 localhost에만 바인딩할 수 있습니다.')
    server=ThreadingHTTPServer((host,port),Handler);print(f'M.A.R.S Worker UI: http://{host}:{port}')
    try:server.serve_forever()
    except KeyboardInterrupt:print('\n관리 UI 종료')
    finally:
        if PROCESS and PROCESS.poll() is None:PROCESS.terminate()
        server.server_close()
