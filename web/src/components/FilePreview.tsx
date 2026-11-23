import { useEffect, useState } from 'react'
import { fetchFile } from '../api'
import { UploadedFile } from '../types'

// 모달에서 앞부분을 보여 줄 텍스트 파일. 나머지(pdf, docx, xlsx, pptx 등)는 새 탭에서 연다
const TEXT_PREVIEW = /\.(txt|md|csv|json|jsonl|log)$/i
const PREVIEW_LINES = 50
// 큰 파일도 앞 50줄만 보면 되므로 앞부분만 읽는다
const PREVIEW_BYTES = 512 * 1024

const pad2 = (value: number) => String(value).padStart(2, '0')

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

/** 업로드 시각과 크기: '11/23 15:02 · 4.6KB' */
export function fileMeta(file: UploadedFile) {
  const date = new Date(file.created_at)
  return `${pad2(date.getMonth() + 1)}/${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())} · ${formatBytes(file.size_bytes)}`
}

/** 같은 이름 파일을 구분할 수 있게 이름·업로드 시각·크기를 함께: 'answers.csv · 11/23 15:02 · 4.6KB' */
export function fileLabel(file: UploadedFile) {
  return `${file.original_name} · ${fileMeta(file)}`
}

/** 최신 업로드가 위에 오게 */
export function newestFirst(files: UploadedFile[]) {
  return [...files].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id)
}

/** CSV 한 줄을 칸으로 나눈다. 따옴표 안의 쉼표와 "" 이스케이프를 처리한다 */
function csvCells(line: string) {
  const cells: string[] = []
  let cell = ''
  let quoted = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (quoted) {
      if (char === '"' && line[index + 1] === '"') { cell += '"'; index += 1 }
      else if (char === '"') quoted = false
      else cell += char
    } else if (char === '"') quoted = true
    else if (char === ',') { cells.push(cell); cell = '' }
    else cell += char
  }
  cells.push(cell)
  return cells
}

type Loaded = { lines: string[]; more: boolean }

function FilePreviewModal({ file, onClose }: { file: UploadedFile; onClose: () => void }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [error, setError] = useState('')
  const isCsv = /\.csv$/i.test(file.original_name)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    fetchFile(`/files/${file.id}/download`).then(async (blob) => {
      let text = await blob.slice(0, PREVIEW_BYTES).text()
      // 한 줄로 저장된 JSON은 줄을 나눠야 앞부분을 읽을 수 있다
      if (/\.json$/i.test(file.original_name) && blob.size <= PREVIEW_BYTES) {
        try { text = JSON.stringify(JSON.parse(text), null, 2) } catch { /* 형식이 틀리면 원문 그대로 */ }
      }
      const lines = text.replace(/\r?\n$/, '').split(/\r?\n/)
      if (!cancelled) setLoaded({ lines: lines.slice(0, PREVIEW_LINES), more: lines.length > PREVIEW_LINES || blob.size > PREVIEW_BYTES })
    }).catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : '파일을 열지 못했어요.') })
    return () => { cancelled = true }
  }, [file])

  const rows = loaded && isCsv ? loaded.lines.map(csvCells) : []
  return <div className="file-library-modal-backdrop" role="presentation" onMouseDown={onClose}>
    <section className="file-library-modal file-preview-modal" role="dialog" aria-modal="true" aria-labelledby="file-preview-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><div><span className="eyebrow">파일 미리보기</span><h2 id="file-preview-title">{file.original_name}</h2><small className="file-preview-meta">업로드 {fileMeta(file)}</small></div><button type="button" className="modal-close" aria-label="닫기" onClick={onClose}>×</button></header>
      <div className="file-preview-body">
        {error ? <p className="error">{error}</p>
          : !loaded ? <p className="muted">불러오는 중…</p>
            : isCsv ? <table className="file-preview-table">
              <thead><tr>{(rows[0] ?? []).map((cell, index) => <th key={index}>{cell}</th>)}</tr></thead>
              <tbody>{rows.slice(1).map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, index) => <td key={index}>{cell}</td>)}</tr>)}</tbody>
            </table>
              : <pre className="file-preview-text">{loaded.lines.join('\n')}</pre>}
      </div>
      {loaded?.more && <footer><span>앞 {PREVIEW_LINES}줄만 표시했어요.</span></footer>}
    </section>
  </div>
}

/** 파일 칩을 눌렀을 때: 텍스트 파일은 모달에서 앞부분을 보여 주고, 나머지는 새 탭에서 연다 */
export function useFilePreview() {
  const [file, setFile] = useState<UploadedFile | null>(null)
  const [error, setError] = useState('')

  async function open(target: UploadedFile) {
    setError('')
    if (TEXT_PREVIEW.test(target.original_name)) { setFile(target); return }
    // 다운로드는 로그인 토큰이 필요해 받아 온 뒤 연다. 팝업 차단을 피하려고 탭은 클릭할 때 먼저 연다
    const tab = window.open('', '_blank')
    try {
      const blob = await fetchFile(`/files/${target.id}/download`)
      const url = URL.createObjectURL(target.content_type ? new Blob([blob], { type: target.content_type }) : blob)
      if (/\.pdf$/i.test(target.original_name) && tab) tab.location.href = url
      else {
        // docx·xlsx·pptx 등은 브라우저 탭에서 바로 볼 수 없어 원래 이름으로 내려받는다
        tab?.close()
        const link = document.createElement('a')
        link.href = url
        link.download = target.original_name
        link.click()
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (cause) {
      tab?.close()
      setError(cause instanceof Error ? cause.message : '파일을 열지 못했어요.')
    }
  }

  const modal = file ? <FilePreviewModal file={file} onClose={() => setFile(null)} /> : null
  return { open, modal, error }
}
