import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import ValidationPanel from '../components/ValidationPanel'
import { Execution, Service, UploadedFile, ValidationResult } from '../types'

type Transfer = { node_id: string; node_name: string; provider: string; type: 'user_input' | 'derived_text' | 'file_text'; file_ids?: number[]; sources?: string[] }
type Preview = { requires_consent: boolean; consent_token: string | null; transfers: Transfer[]; validation: ValidationResult }

export default function WorkflowRunPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  function showValidationFrom(cause: unknown) {
    const detail = cause instanceof ApiError ? cause.detail as { validation?: ValidationResult } | undefined : undefined
    if (detail?.validation) setValidation(detail.validation)
  }
  useEffect(() => { api.get<Service>(`/services/${id}`).then(setService).catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load workflow.')); api.get<UploadedFile[]>('/files').then(setFiles).catch(() => {}) }, [id])
  async function start(consentToken?: string | null) { setLoading(true); setError(''); try { const execution = await api.post<Execution>(`/services/${id}/executions`, { run_prompt: prompt, consent_token: consentToken || null, acknowledge_warnings: acknowledged }); navigate(`/executions/${execution.id}`) } catch (cause) { setPreview(null); showValidationFrom(cause); setError(cause instanceof Error ? cause.message : 'Unable to start workflow.') } finally { setLoading(false) } }
  async function run(event: FormEvent) { event.preventDefault(); setLoading(true); setError(''); try { const result = await api.post<Preview>(`/services/${id}/executions/preview`, { run_prompt: prompt }); setValidation(result.validation); if (result.validation.errors.length) { setError('구성 오류를 고친 뒤 실행할 수 있습니다.'); return } if (result.validation.warnings.length && !acknowledged) { setError('구성 경고를 확인하고 체크한 뒤 다시 실행해 주세요.'); return } if (result.requires_consent) setPreview(result); else await start() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to inspect workflow.') } finally { setLoading(false) } }
  if (!service) return <div className="page-loading">{error || 'Loading workflow...'}</div>
  const fileName = (fileId: number) => files.find((file) => file.id === fileId)?.original_name || `File #${fileId}`
  return <div className="workflow-run-page"><header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> {service.name} <span>/</span> Run</div><h1>Configure execution</h1><p>Provide the task-specific input, then start this saved workflow.</p></div><Link className="btn ghost" to={`/services/${service.id}`}>Back to builder</Link></header><div className="run-input-layout"><form className="run-input-card" onSubmit={run}><span className="eyebrow">EXECUTION INPUT</span><h2>What should this workflow do?</h2><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe the output you need for this run." required minLength={1} />{validation && (validation.errors.length > 0 || validation.warnings.length > 0) && <><ValidationPanel validation={validation} nodeNames={Object.fromEntries(service.graph.nodes.map((node) => [node.id, node.name]))} showStages={false} />{validation.errors.length > 0 && <Link className="btn sm ghost" to={`/services/${service.id}`}>편집 화면에서 고치기</Link>}{!validation.errors.length && <label className="ack-row"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />경고 내용을 확인했고 그대로 실행합니다.</label>}</>}<div className="run-card-footer"><span>Workflow: <strong>{service.name}</strong></span><button className="generate-button" disabled={loading}>{loading ? 'Checking...' : 'Run workflow'} <b>→</b></button></div>{error && <div className="error">{error}</div>}</form><aside className="run-summary-panel"><span className="eyebrow">WORKFLOW SUMMARY</span><h2>{service.name}</h2><p>{service.description || 'No workflow description provided.'}</p><div className="run-summary-stat"><strong>{service.graph.nodes?.length ?? 0}</strong><span>workflow blocks</span></div><div className="run-files-note"><div><strong>Input file vault</strong><small>{files.length} uploaded file{files.length === 1 ? '' : 's'}</small></div><p>Cloud steps always require a transfer review before execution.</p><Link to="/files">Manage files →</Link></div></aside></div>
    {preview && <div className="file-library-modal-backdrop" role="presentation"><section className="file-library-modal transfer-consent-modal" role="dialog" aria-modal="true" aria-labelledby="transfer-title"><header><div><span className="eyebrow">EXTERNAL DATA TRANSFER</span><h2 id="transfer-title">클라우드 전송 내용을 확인해 주세요</h2></div><button className="modal-close" onClick={() => setPreview(null)}>×</button></header><p>API 키는 서버에만 보관되며 아래 입력과 결과만 외부 공급자에 전달됩니다.</p><div className="transfer-list">{preview.transfers.map((item, index) => <div className={`transfer-item ${item.type}`} key={`${item.node_id}-${item.type}-${index}`}><strong>{item.node_name} → {item.provider}</strong><span>{item.type === 'user_input' ? '사용자 실행 요청' : item.type === 'derived_text' ? `로컬 파일에서 파생된 텍스트: ${(item.sources || []).join(', ')}` : `첨부파일에서 추출한 텍스트: ${(item.file_ids || []).map(fileName).join(', ')}`}</span></div>)}</div><footer><span>이번 실행에만 적용됩니다.</span><div><button className="btn sm ghost" onClick={() => setPreview(null)}>취소</button><button className="btn sm" disabled={loading} onClick={() => start(preview.consent_token)}>동의하고 실행</button></div></footer></section></div>}
  </div>
}
