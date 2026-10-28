import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PublicFooter, PublicHeader } from '../components/PublicChrome'
import { detectPlatform, DOWNLOADS, Platform, RELEASE, serverApiUrl } from '../release'

const PLATFORMS: Record<Platform, { name: string; system: string; summary: string }> = {
  windows: { name: 'Windows', system: 'Windows 10 / 11 (64비트)', summary: '압축을 풀고 start-worker.cmd를 더블클릭하면 필요한 프로그램을 확인하며 설치해요.' },
  mac: { name: 'macOS', system: 'macOS · Apple Silicon 권장', summary: 'Ollama 앱이 Apple GPU를 바로 쓰도록 Docker 없이 실행해요.' },
  linux: { name: 'Linux', system: 'Linux 64비트 · Docker 권장', summary: 'Docker로 Worker와 Ollama를 함께 띄우고 GPU를 자동으로 감지해요.' },
}

const REQUIREMENTS: Record<Platform, string[]> = {
  windows: ['Python 3.11 이상 (없으면 설치 페이지를 안내)', 'Windows용 Ollama', '메모리 8GB 이상 권장 (4B 모델 기준)'],
  mac: ['Python 3.11 이상 (Apple Silicon은 arm64)', '맥용 Ollama 앱', '메모리 8GB 이상 권장 (4B 모델 기준)'],
  linux: ['Docker Engine + Compose v2 (또는 Python 3.11 이상)', 'NVIDIA·AMD GPU는 자동 감지, 없으면 CPU', '메모리 8GB 이상 권장 (4B 모델 기준)'],
}

const FAQ = [
  { q: '포트를 열거나 공유기 설정을 해야 하나요?', a: '아니요. 워커가 서버에 먼저 연락해 작업을 가져가는 방식이라 인바운드 포트나 포트포워딩이 필요 없어요. Worker UI(8765)와 Ollama(11434)는 내 기기 안(127.0.0.1)에서만 열려요.' },
  { q: '내 파일은 어디까지 전달되나요?', a: '업로드한 파일은 서버를 거쳐 워커에 전달되고, 공유 디렉터리 파일은 그 기기 안에서만 읽혀요. 워커는 워크플로우에 연결한 폴더만 읽을 수 있어요.' },
  { q: '어떤 모델을 받아야 하나요?', a: '처음에는 qwen3:4b처럼 4B 크기 모델을 권장해요. Worker UI의 Models 화면에서 받거나 터미널에서 ollama pull qwen3:4b를 실행하세요.' },
  { q: '웹에서 워커가 오프라인으로 보여요.', a: 'Worker UI의 Status 화면에서 실행 중인지, 서버 주소가 /api로 끝나는지 확인하세요. 기기가 잠자기에 들어가면 연결이 끊겨요.' },
  { q: '워커로 워크플로우를 만들 수도 있나요?', a: '네. 첫 화면 생성 모델에서 "내 워커"를 고르면 서버 GPU 대신 이 기기의 Ollama가 워크플로우를 만들어요.' },
  { q: '등록을 지우려면요?', a: 'Worker UI의 "등록 해제"를 누르면 웹 워크스페이스에서도 이 기기가 삭제돼요. 등록 정보 파일(agent_config.json)에는 인증 키가 있으니 다른 사람과 공유하지 마세요.' },
]

function CopyButton({ text, label = '복사' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  return <button type="button" className="mk-copy" onClick={copy}>{copied ? '복사됨' : label}</button>
}

function Command({ code }: { code: string }) {
  return <div className="mk-command"><pre><code>{code}</code></pre><CopyButton text={code} /></div>
}

/** 워커 다운로드: 운영체제별 설치와 서버 등록 방법 */
export default function DownloadPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('os')
  const [detected] = useState(detectPlatform)
  const platform: Platform = requested === 'windows' || requested === 'mac' || requested === 'linux' ? requested : detected
  const server = serverApiUrl()
  const folder = DOWNLOADS.folder

  useEffect(() => { window.scrollTo(0, 0) }, [])

  function choose(next: Platform) {
    setSearchParams(next === detected ? {} : { os: next }, { replace: true })
  }

  const install: Record<Platform, JSX.Element> = {
    windows: <ol className="mk-install">
      <li><b>다운로드한 ZIP의 압축을 풀어요.</b><span><code>{folder}</code> 폴더가 생겨요.</span></li>
      <li><b><code>start-worker.cmd</code>를 더블클릭해요.</b><span>Python과 Ollama가 없으면 공식 다운로드 페이지와 설치 방법을 안내해요. 설치 후 다시 실행하세요.</span></li>
      <li><b>브라우저에 Worker UI가 열리면 등록해요.</b><span>아래 <a href="#register">등록 순서</a>를 따라 서버 주소와 계정을 입력하세요.</span></li>
    </ol>,
    mac: <ol className="mk-install">
      <li><b><a href="https://ollama.com/download/mac" target="_blank" rel="noreferrer">맥용 Ollama 앱</a>을 설치하고 실행해요.</b><span>앱이 Apple GPU를 자동으로 사용해요.</span></li>
      <li><b>터미널에서 아래 명령을 그대로 실행해요.</b><span>워커를 내려받아 가상환경에 설치하고 Worker UI를 열어요.</span>
        <Command code={`curl -L ${DOWNLOADS.tarball} | tar xz\ncd ${folder}/worker\npython3 -m venv .venv && source .venv/bin/activate\npip install -r requirements.txt\npython -m agent ui`} />
      </li>
      <li><b>http://127.0.0.1:8765 에서 등록해요.</b><span>다음부터는 <code>cd {folder}/worker && source .venv/bin/activate && python -m agent ui</code>만 실행하면 돼요.</span></li>
    </ol>,
    linux: <ol className="mk-install">
      <li><b>Docker로 실행해요 (권장).</b><span>Worker UI와 Ollama를 함께 띄우고 NVIDIA·AMD GPU를 자동으로 감지해요.</span>
        <Command code={`curl -L ${DOWNLOADS.tarball} | tar xz\ncd ${folder}\n./start-worker.sh`} />
      </li>
      <li><b>Docker 없이 실행할 수도 있어요.</b><span>호스트에 Ollama를 설치한 뒤 Python으로 실행해요.</span>
        <Command code={`curl -fsSL https://ollama.com/install.sh | sh\ncd ${folder}/worker\npython3 -m venv .venv && source .venv/bin/activate\npip install -r requirements.txt\npython -m agent ui`} />
      </li>
      <li><b>http://127.0.0.1:8765 에서 등록해요.</b><span>아래 <a href="#register">등록 순서</a>를 따르세요.</span></li>
    </ol>,
  }

  return <div className="mk-page">
    <PublicHeader />

    <section className="mk-dl-hero">
      <div className="mk-shell">
        <span className="mk-kicker">M.A.R.S Worker · {RELEASE}</span>
        <h1>내 기기를 M.A.R.S 워커로 연결하세요</h1>
        <p>설치하고 로그인하면 이 PC가 워크플로우 작업을 나눠 맡기 시작해요. 따로 네트워크 설정은 필요 없어요.</p>
        <div className="mk-dl-primary">
          <a className="mk-btn mk-btn-light mk-btn-lg" href={platform === 'windows' ? DOWNLOADS.zip : DOWNLOADS.tarball}>
            {PLATFORMS[platform].name}용 다운로드
          </a>
          <span>{PLATFORMS[platform].system}{platform === detected ? ' · 지금 쓰는 기기' : ''} · <a href={DOWNLOADS.zip}>ZIP</a> · <a href={DOWNLOADS.tarball}>tar.gz</a></span>
        </div>
      </div>
    </section>

    <section className="mk-section">
      <div className="mk-shell mk-dl-layout">
        <div className="mk-dl-main">
          <div className="mk-tabs" role="tablist" aria-label="운영체제">
            {(Object.keys(PLATFORMS) as Platform[]).map((key) => <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === platform}
              className={key === platform ? 'active' : ''}
              onClick={() => choose(key)}
            >{PLATFORMS[key].name}{key === detected && <small>내 기기</small>}</button>)}
          </div>
          <div className="mk-card mk-dl-card" role="tabpanel">
            <div className="mk-dl-card-head">
              <div><h2>{PLATFORMS[platform].name}에 설치하기</h2><p>{PLATFORMS[platform].summary}</p></div>
              <a className="mk-btn mk-btn-primary" href={platform === 'windows' ? DOWNLOADS.zip : DOWNLOADS.tarball}>다운로드</a>
            </div>
            {install[platform]}
            <div className="mk-req">
              <b>필요한 것</b>
              <ul>{REQUIREMENTS[platform].map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>

          <div className="mk-card" id="register">
            <h2>서버에 등록하기</h2>
            <ol className="mk-register">
              <li><b>모델을 하나 받아요.</b><span>Worker UI의 Models 화면이나 터미널에서 받아요.</span><Command code="ollama pull qwen3:4b" /></li>
              <li><b>Register this worker 화면에 입력해요.</b><span>Server address, 기기 이름(예: 홍길동-맥북), M.A.R.S 계정을 입력하고 <b>Connect worker</b>를 눌러요.</span></li>
              <li><b>Status 화면에서 시작을 눌러요.</b><span>웹 사이드바의 워커가 온라인으로 바뀌면 끝이에요. 첫 화면 생성 모델에도 "내 워커"가 나타나요.</span></li>
            </ol>
          </div>

          <div className="mk-card">
            <h2>자주 묻는 질문</h2>
            <div className="mk-faq">
              {FAQ.map((item) => <details key={item.q}><summary>{item.q}</summary><p>{item.a}</p></details>)}
            </div>
          </div>
        </div>

        <aside className="mk-dl-side">
          <div className="mk-card mk-server-card">
            <span>서버 주소</span>
            <code>{server}</code>
            <CopyButton text={server} label="주소 복사" />
            <small>Worker UI의 Server address에 이 주소를 넣으세요.</small>
          </div>
          <div className="mk-card mk-side-card">
            <b>계정이 아직 없나요?</b>
            <p>워커는 M.A.R.S 계정의 기기로 등록돼요.</p>
            <Link className="mk-btn mk-btn-primary" to="/login?mode=register">회원가입</Link>
          </div>
          <div className="mk-card mk-side-card">
            <b>다른 운영체제</b>
            {(Object.keys(PLATFORMS) as Platform[]).filter((key) => key !== platform).map((key) => <button key={key} type="button" className="mk-link-button" onClick={() => choose(key)}>{PLATFORMS[key].name} 설치 방법 →</button>)}
          </div>
        </aside>
      </div>
    </section>

    <PublicFooter />
  </div>
}
