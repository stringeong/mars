import { api } from './api'
import { GenerationError, GenerationJob, GeneratorModels } from './types'

const POLL_MS = 1500

/** 서버 GPU가 부족할 수 있으므로, 온라인이고 모델이 있는 워커가 있으면 그 워커를 기본 생성 모델로 고른다. */
export function defaultWorker(models: GeneratorModels | null) {
  return models?.workers.find((worker) => worker.online && worker.models.length) ?? null
}

export class GenerationFailed extends Error {
  constructor(public detail: GenerationError) {
    super(detail.message)
  }
}

/**
 * 워커에 워크플로우 생성을 맡기고 끝날 때까지 상태를 확인한다.
 * 만들어진 워크플로우 id를, 사용자가 취소하면 null을 돌려준다. 실패하면 GenerationFailed.
 */
export async function generateOnWorker(
  prompt: string,
  deviceId: number,
  model: string,
  onUpdate: (job: GenerationJob) => void,
  signal: AbortSignal,
): Promise<number | null> {
  let job = await api.post<GenerationJob>('/services/generation-jobs', { prompt, device_id: deviceId, model })
  onUpdate(job)
  while (job.status === 'pending' || job.status === 'running') {
    await new Promise((resolve) => window.setTimeout(resolve, POLL_MS))
    if (signal.aborted) {
      await api.post(`/services/generation-jobs/${job.id}/cancel`).catch(() => {})
      return null
    }
    job = await api.get<GenerationJob>(`/services/generation-jobs/${job.id}`)
    onUpdate(job)
  }
  if (job.status === 'done' && job.service_id) return job.service_id
  if (job.status === 'canceled') return null
  throw new GenerationFailed(job.generation_error ?? {
    stage: 'connection', message: '워커에서 워크플로우를 만들지 못했습니다.', location: 'worker', provider: 'ollama', model: job.model,
  })
}

/** 생성 진행 안내: 워커가 가져가기 전/하던 작업을 마치는 중/생성 중 */
export function workerProgressLabel(job: GenerationJob, seconds: number) {
  const name = job.device_name ?? '워커'
  if (job.status === 'pending' && job.worker_busy) return `${name} 워커가 하던 작업을 마치면 생성을 시작합니다… ${seconds}초`
  if (job.status === 'pending') return `${name} 워커가 요청을 가져가기를 기다리는 중… ${seconds}초`
  return `${name} 워커에서 워크플로우를 만드는 중… ${seconds}초${job.attempt > 1 ? ' (다시 묻는 중)' : ''}`
}
