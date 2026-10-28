import { useRef } from 'react'
import { BlockEdit, CloudProvider, DEMO_CLOUD, DEMO_DEFAULT_MODEL, DEMO_LOCAL_MODELS, DEMO_WORKERS, DemoBlock } from '../demos'

type Props = {
  block: DemoBlock
  edit: BlockEdit
  onChange: (edit: BlockEdit) => void
  onReset: () => void
  onRun: () => void
}

/** 제품 소개의 편집 예시. 편집기의 블록 설정 패널처럼 실행 위치·워커·모델·첨부 파일을 바꿔 본다.
 *  파일은 이름과 크기만 읽고 어디에도 올리지 않는다. */
export default function DemoEditPanel({ block, edit, onChange, onReset, onRun }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const local = edit.location === 'ollama'
  const models = local ? DEMO_LOCAL_MODELS : DEMO_CLOUD[edit.location as CloudProvider].models
  const workerHint = !local
    ? '외부 API로 보내는 블록은 워커 대신 공급자가 처리해요. 실행 전에 무엇이 전송되는지 보여주고 동의를 받아요.'
    : edit.worker ? `${edit.worker}가 이 블록을 맡아요.` : '실행할 때 비어 있는 워커에 자동으로 맡겨요. 같은 단계의 블록은 여러 워커에 나눠져요.'

  function addFiles(list: FileList | null) {
    if (!list?.length) return
    const added = [...list].map((file) => ({ name: file.name, size: file.size }))
    onChange({ ...edit, files: [...edit.files.filter((file) => !added.some((item) => item.name === file.name)), ...added] })
    if (fileRef.current) fileRef.current.value = ''
  }

  return <aside className="node-panel mk-edit-panel" aria-label={`${block.name} 블록 설정`}>
    <div className="mk-edit-head">
      <h2>에이전트 블록</h2>
      <span>{block.name}</span>
      <small>다른 블록을 누르면 그 블록 설정으로 바뀌어요</small>
    </div>
    <div className="mk-edit-grid">
      <div>
        <label htmlFor="demo-location">실행 위치</label>
        <select id="demo-location" value={edit.location} onChange={(event) => {
          const location = event.target.value as BlockEdit['location']
          onChange({ ...edit, location, worker: location === 'ollama' ? edit.worker || DEMO_WORKERS[0] : '', model: '' })
        }}>
          <option value="ollama">Local Worker · Ollama</option>
          <option value="openai">Cloud · OpenAI</option>
          <option value="anthropic">Cloud · Anthropic</option>
          <option value="gemini">Cloud · Google Gemini</option>
        </select>
        <label htmlFor="demo-worker">컴퓨팅 자원 (Worker)</label>
        <select id="demo-worker" disabled={!local} value={edit.worker} onChange={(event) => onChange({ ...edit, worker: event.target.value })}>
          <option value="">자동 배정</option>
          {DEMO_WORKERS.map((name) => <option key={name} value={name}>{name} · 온라인</option>)}
        </select>
        <small className="muted">{workerHint}</small>
      </div>
      <div>
        <label htmlFor="demo-model">모델</label>
        <select id="demo-model" value={edit.model} onChange={(event) => onChange({ ...edit, model: event.target.value })}>
          <option value="">{local ? `Worker 기본 모델 · ${DEMO_DEFAULT_MODEL}` : `공급자 기본 모델 · ${models[0]}`}</option>
          {models.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
        <small className="muted">블록마다 다른 모델을 고를 수 있어요. 검수 블록만 큰 모델로 두는 식이에요.</small>
        <div className="uploaded-file-picker">
          <div className="uploaded-file-heading">
            <strong>첨부 파일</strong>
            <div className="file-picker-actions"><button type="button" className="btn sm ghost" onClick={() => fileRef.current?.click()}>새 파일 업로드</button></div>
            <input ref={fileRef} className="inline-file-input" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx" onChange={(event) => addFiles(event.target.files)} />
          </div>
          <small className="file-picker-help">이 블록이 실행할 때 우선 읽는 파일이에요. 예시 화면이라 고른 파일은 어디에도 올라가지 않아요.</small>
          <div className="selected-file-list">
            {edit.files.map((file) => <div className="selected-file-chip" key={file.name}>
              <span><strong>{file.name}</strong><small>{file.size.toLocaleString()} bytes</small></span>
              <button type="button" aria-label={`${file.name} 첨부 해제`} onClick={() => onChange({ ...edit, files: edit.files.filter((item) => item.name !== file.name) })}>×</button>
            </div>)}
            {!edit.files.length && <span className="muted">선택된 파일이 없습니다.</span>}
          </div>
        </div>
      </div>
    </div>
    <div className="mk-edit-foot">
      <button type="button" className="btn sm ghost" onClick={onReset}>원래대로</button>
      <button type="button" className="btn sm" onClick={onRun}>이대로 실행 →</button>
    </div>
  </aside>
}
