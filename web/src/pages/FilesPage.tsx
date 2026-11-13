import { ChangeEvent, DragEvent, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { UploadedFile } from '../types'
import { shortDate } from '../workflow'

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function typeLabel(file: UploadedFile) {
  const extension = file.original_name.split('.').pop()?.toUpperCase()
  return extension && extension !== file.original_name ? extension : 'FILE'
}

export default function FilesPage() {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [kind, setKind] = useState('전체')
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const load = () => api.get<UploadedFile[]>('/files').then(setFiles).catch((cause) => setError(cause instanceof Error ? cause.message : '파일 목록을 불러오지 못했어요.'))
  useEffect(() => { load() }, [])

  async function upload(selected: FileList | null) {
    if (!selected?.length || uploading) return
    setUploading(true); setError('')
    try {
      for (const file of Array.from(selected)) { const form = new FormData(); form.append('file', file); await api.upload<UploadedFile>('/files', form) }
      await load()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '파일을 올리지 못했어요.') }
    finally { setUploading(false); if (inputRef.current) inputRef.current.value = '' }
  }
  async function remove(file: UploadedFile) {
    if (!confirm(`${file.original_name} 파일을 지울까요?`)) return
    try { await api.delete(`/files/${file.id}`); setFiles((current) => current.filter((item) => item.id !== file.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '파일을 지우지 못했어요.') }
  }
  function onChange(event: ChangeEvent<HTMLInputElement>) { void upload(event.target.files) }
  function onDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files) }

  return <div className="files-page">
    <header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> 파일</div><h1>입력 파일</h1><p>워크플로우에 쓸 문서와 데이터 파일을 올려 두세요.</p></div></header>
    <section className={`file-dropzone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={onDrop}><div className="drop-icon">+</div><h2>{uploading ? '올리는 중…' : '파일을 여기로 끌어다 놓으세요'}</h2><p>PDF, DOCX, TXT, CSV, XLSX, PPTX 등 · 파일당 최대 50MB</p><input ref={inputRef} type="file" multiple onChange={onChange} /><button type="button" className="btn" disabled={uploading} onClick={() => inputRef.current?.click()}>파일 선택</button></section>
    {error && <div className="error">{error}</div>}
    <section className="file-library"><div className="section-heading"><div><span className="eyebrow">내 파일</span><h2>올린 파일</h2></div><input className="files-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="파일 이름 검색" /></div>
    <div className="files-kinds">{['전체', ...[...new Set(files.map(typeLabel))]].map((label) => <button type="button" key={label} className={kind === label ? 'active' : ''} onClick={() => setKind(label)}>{label} <b>{label === '전체' ? files.length : files.filter((file) => typeLabel(file) === label).length}</b></button>)}</div><div className="file-grid">{files.filter((file) => (kind === '전체' || typeLabel(file) === kind) && file.original_name.toLowerCase().includes(query.toLowerCase())).map((file) => <article className="file-card" key={file.id}><span className="file-type">{typeLabel(file)}</span><div className="file-meta"><strong>{file.original_name}</strong><small>{formatBytes(file.size_bytes)} · {shortDate(file.created_at)}</small></div><button type="button" className="file-remove" onClick={() => remove(file)} aria-label={`${file.original_name} 지우기`}>×</button></article>)}{files.length > 0 && !files.some((file) => (kind === '전체' || typeLabel(file) === kind) && file.original_name.toLowerCase().includes(query.toLowerCase())) && <div className="empty-file-state">검색 결과가 없어요.</div>}{!files.length && <div className="empty-file-state">올린 파일이 여기에 표시돼요. 기기 안의 파일을 바로 읽으려면 워커 폴더를 연결하세요.</div>}</div></section>
  </div>
}
