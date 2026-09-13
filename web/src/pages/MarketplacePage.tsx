import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Service } from '../types'

const templates = [
  { id: 'research', title: 'Research Assistant', category: 'Research', rating: 4.9, author: 'M.A.R.S Team', description: 'Search relevant sources, compare evidence, and prepare a concise research report.', prompt: 'Research the requested topic using relevant sources, compare the evidence, and produce a concise report with key findings and references.' },
  { id: 'documents', title: 'Document Review', category: 'Documents', rating: 4.7, author: 'M.A.R.S Team', description: 'Review supplied documents and identify key issues, risks, and next steps.', prompt: 'Review the supplied documents, identify the key issues and risks, and provide a structured summary with recommended next steps.' },
  { id: 'data', title: 'Data Analysis', category: 'Analysis', rating: 4.8, author: 'Community', description: 'Find meaningful trends in available data and deliver evidence-backed recommendations.', prompt: 'Analyze the available data, identify meaningful trends and anomalies, and provide evidence-backed recommendations.' },
  { id: 'meeting', title: 'Meeting Preparation', category: 'Productivity', rating: 4.6, author: 'Community', description: 'Collect context, draft an agenda, and prepare decisions and discussion points.', prompt: 'Prepare for the upcoming meeting by collecting the relevant context, drafting an agenda, and listing decisions and discussion points.' },
  { id: 'planner', title: 'Project Planner', category: 'Planning', rating: 4.8, author: 'M.A.R.S Team', description: 'Turn a project brief into milestones, responsibilities, risks, and an execution plan.', prompt: 'Turn the project brief into an actionable plan with milestones, responsibilities, dependencies, risks, and next steps.' },
  { id: 'knowledge', title: 'Knowledge Organizer', category: 'Knowledge', rating: 4.5, author: 'Community', description: 'Organize notes, connect related concepts, and surface reusable insights.', prompt: 'Organize the available notes, connect related concepts, remove duplication, and surface the most useful reusable insights.' },
]

export default function MarketplacePage() {
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState<string | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const filtered = useMemo(() => templates.filter((template) => `${template.title} ${template.category} ${template.description}`.toLowerCase().includes(query.toLowerCase())), [query])

  async function useTemplate(id: string, prompt: string) {
    setCreating(id); setError('')
    try {
      const service = await api.post<Service>('/services/generate', { prompt })
      navigate(`/services/${service.id}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create a workflow from this template.')
      setCreating(null)
    }
  }

  return <div className="marketplace-page">
    <header className="page-heading"><div><div className="breadcrumb">M.A.R.S <span>/</span> Marketplace</div><h1>Marketplace</h1><p>Start with a reusable workflow template and customize every block for your team.</p></div></header>
    <div className="marketplace-toolbar"><div className="marketplace-search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search templates" /></div><span>{filtered.length} templates</span></div>
    {error && <div className="error marketplace-error">{error}</div>}
    <div className="marketplace-grid">
      {filtered.map((template) => <article className="marketplace-card" key={template.id}><div className="marketplace-card-top"><span className="template-category">{template.category}</span><span className="template-rating">★ {template.rating}</span></div><h2>{template.title}</h2><p>{template.description}</p><small>by {template.author}</small><button onClick={() => useTemplate(template.id, template.prompt)} disabled={creating !== null}>{creating === template.id ? 'Creating workflow...' : 'Use template →'}</button></article>)}
    </div>
    {!filtered.length && <div className="marketplace-empty">No templates match your search.</div>}
  </div>
}
