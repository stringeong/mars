import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Execution, Service, UploadedFile } from '../types'

export default function WorkflowRunPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { api.get<Service>(`/services/${id}`).then(setService).catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load workflow.')); api.get<UploadedFile[]>('/files').then(setFiles).catch(() => {}) }, [id])
  async function run(event: FormEvent) { event.preventDefault(); setLoading(true); setError(''); try { const execution = await api.post<Execution>(`/services/${id}/executions`, { run_prompt: prompt }); navigate(`/executions/${execution.id}`) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to start workflow.') } finally { setLoading(false) } }
  if (!service) return <div className="page-loading">{error || 'Loading workflow...'}</div>
  return <div className="workflow-run-page"><header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> {service.name} <span>/</span> Run</div><h1>Configure execution</h1><p>Provide the task-specific input, then start this saved workflow.</p></div><Link className="btn ghost" to={`/services/${service.id}`}>Back to builder</Link></header><div className="run-input-layout"><form className="run-input-card" onSubmit={run}><span className="eyebrow">EXECUTION INPUT</span><h2>What should this workflow do?</h2><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe the output you need for this run. The workflow structure stays unchanged." required minLength={1} /><div className="run-card-footer"><span>Workflow: <strong>{service.name}</strong></span><button className="generate-button" disabled={loading}>{loading ? 'Starting...' : 'Run workflow'} <b>→</b></button></div>{error && <div className="error">{error}</div>}</form><aside className="run-summary-panel"><span className="eyebrow">WORKFLOW SUMMARY</span><h2>{service.name}</h2><p>{service.description || 'No workflow description provided.'}</p><div className="run-summary-stat"><strong>{service.graph.nodes?.length ?? 0}</strong><span>workflow blocks</span></div><div className="run-files-note"><div><strong>Input file vault</strong><small>{files.length} uploaded file{files.length === 1 ? '' : 's'}</small></div><p>Files are stored separately. Assign a Worker directory to an agent when it needs direct file access.</p><Link to="/files">Manage files →</Link></div></aside></div></div>
}
