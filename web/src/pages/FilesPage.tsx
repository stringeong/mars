import { ChangeEvent, DragEvent, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { UploadedFile } from '../types'

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
  const inputRef = useRef<HTMLInputElement>(null)
  const load = () => api.get<UploadedFile[]>('/files').then(setFiles).catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load files.'))
  useEffect(() => { load() }, [])

  async function upload(selected: FileList | null) {
    if (!selected?.length || uploading) return
    setUploading(true); setError('')
    try {
      for (const file of Array.from(selected)) { const form = new FormData(); form.append('file', file); await api.upload<UploadedFile>('/files', form) }
      await load()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to upload file.') }
    finally { setUploading(false); if (inputRef.current) inputRef.current.value = '' }
  }
  async function remove(file: UploadedFile) {
    if (!confirm(`Remove ${file.original_name}?`)) return
    try { await api.delete(`/files/${file.id}`); setFiles((current) => current.filter((item) => item.id !== file.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to remove file.') }
  }
  function onChange(event: ChangeEvent<HTMLInputElement>) { void upload(event.target.files) }
  function onDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files) }

  return <div className="files-page">
    <header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> Files</div><h1>Input files</h1><p>Upload documents and data files that you want to keep with your workflow workspace.</p></div><div className="page-stat"><strong>{files.length}</strong><span>stored files</span></div></header>
    <section className={`file-dropzone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={onDrop}><div className="drop-icon">+</div><h2>{uploading ? 'Uploading files...' : 'Drop files here to upload'}</h2><p>PDF, DOCX, TXT, CSV, XLSX, PPTX and common document formats. Maximum 50 MB per file.</p><input ref={inputRef} type="file" multiple onChange={onChange} /><button type="button" className="btn" disabled={uploading} onClick={() => inputRef.current?.click()}>Choose files</button></section>
    {error && <div className="error">{error}</div>}
    <section className="file-library"><div className="section-heading"><div><span className="eyebrow">YOUR FILE VAULT</span><h2>Uploaded files</h2></div><span className="count-pill">{files.length}</span></div><div className="file-grid">{files.map((file) => <article className="file-card" key={file.id}><span className="file-type">{typeLabel(file)}</span><div className="file-meta"><strong>{file.original_name}</strong><small>{formatBytes(file.size_bytes)} · {new Date(file.created_at).toLocaleDateString()}</small></div><button type="button" className="file-remove" onClick={() => remove(file)} aria-label={`Remove ${file.original_name}`}>×</button></article>)}{!files.length && <div className="empty-file-state">Files you upload will appear here. Use Worker directories when a workflow needs to read files directly on a device.</div>}</div></section>
  </div>
}
