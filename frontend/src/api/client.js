import axios from 'axios'

export const api = axios.create({
  // Vite dev 下通过 proxy 转发；生产下同域部署无需 baseURL
  baseURL: '',
  timeout: 600000,
})

/** HITL：确认将待落库排程写入 work_orders */
export function confirmPersistSave(confirmToken) {
  return api.post('/api/db/confirm_save', { confirm_token: confirmToken })
}

/** 直接提议落库（一般由 scheduling Agent 内部调用） */
export function proposePersistSave(body) {
  return api.post('/api/db/propose_save', body)
}

/** 智能排程 Agent（含 persist_after 时走交期评估 + HITL 落库） */
export function runSchedulingAgent(body) {
  const params = { ...(body.params || {}), persist_after: true }
  return api.post('/api/agents/scheduling/run', { ...body, params })
}

/** @deprecated 使用 runSchedulingAgent */
export function runPipelineAgent(body) {
  return runSchedulingAgent(body)
}

/**
 * Orchestrator SSE：思考过程实时推送。
 * @param {object} body 与 /api/orchestrator/run 相同
 * @param {(payload: object) => void} onEvent
 */
export async function streamOrchestrator(body, onEvent) {
  const res = await fetch('/api/orchestrator/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const err = await res.json()
      detail = err.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('浏览器不支持流式响应')
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const chunks = buf.split('\n\n')
    buf = chunks.pop() || ''
    for (const chunk of chunks) {
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        const payload = JSON.parse(line.slice(6))
        onEvent(payload)
      }
    }
  }
  if (buf.trim()) {
    for (const line of buf.split('\n')) {
      if (!line.startsWith('data: ')) continue
      onEvent(JSON.parse(line.slice(6)))
    }
  }
}

