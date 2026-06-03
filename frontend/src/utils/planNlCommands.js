/** 从自然语言解析计划库操作（客户端处理，不走 Orchestrator） */

const PREFIX = /^(?:请|帮我|麻烦|我想|我要)?\s*/

function stripPrefix(t) {
  return t.replace(PREFIX, '').trim()
}

/** @returns {{ type: string, name?: string, query?: string } | null} */
export function parsePlanNlCommand(text) {
  const raw = (text || '').trim()
  if (!raw) return null
  const t = stripPrefix(raw)

  let m = t.match(
    /^(?:新建|创建|添加)(?:一个)?(?:名为|叫做|叫|名称[是为]|名字[是为])?\s*[「"'『]?([^」"'』\s，,。.!?]+)[」"'』]?\s*(?:的)?(?:计划|订单|工单计划)\s*[。.!?]*$/i
  )
  if (m) return { type: 'create', name: (m[1] || '').trim() }

  m = t.match(
    /^(?:新建|创建|添加)(?:一个)?(?:计划|订单|工单计划)\s*(?:[，,\s]*(?:叫|名为|名称是|名称为|名字))?\s*[「"'『]?([^」"'』\s，,。.!?]+)?[」"'』]?\s*[。.!?]*$/i
  )
  if (m) return { type: 'create', name: (m[1] || '').trim() }

  m = t.match(/^(?:列出|查看|显示|刷新)(?:所有)?(?:计划|订单)(?:列表)?\s*[。.!?]*$/i)
  if (m) return { type: 'list' }

  m = t.match(
    /^(?:删除|删掉|移除)(?:计划|订单)?\s*[「"'『]?([^」"'』\s，,。.!?]+)[」"'』]?\s*[。.!?]*$/i
  )
  if (m) return { type: 'delete', query: (m[1] || '').trim() }

  m = t.match(
    /^(?:打开|去|进入|跳转|转到)(?:智能)?排程(?:中心|页面)?\s*[。.!?]*$/i
  )
  if (m) return { type: 'goto_aps' }

  m = t.match(
    /^(?:加载|打开|选择|切换|绑定|使用|载入)(?:计划|订单|工单)?\s*[：:\s]*[「"'『]?([^」"'』\s，,。.!?]+)[」"'』]?\s*[。.!?]*$/i
  )
  if (m) return { type: 'select', query: (m[1] || '').trim() }

  m = t.match(/^(?:用|把)\s*[「"'『]?([^」"'』\s，,]+)[」"'』]?\s*(?:这个)?(?:计划|订单)/i)
  if (m) return { type: 'select', query: (m[1] || '').trim() }

  m = t.match(/^(?:解绑|清除|取消)(?:当前)?(?:计划|订单|绑定)\s*[。.!?]*$/i)
  if (m) return { type: 'clear' }

  return null
}

export function findPlanByQuery(orders, query) {
  if (!query || !orders?.length) return null
  const q = query.toLowerCase()
  const exact = orders.find(
    (o) =>
      String(o.id || '').toLowerCase() === q ||
      String(o.plan_name || '').toLowerCase() === q
  )
  if (exact) return exact
  const partial = orders.filter(
    (o) =>
      String(o.plan_name || '').toLowerCase().includes(q) ||
      String(o.id || '').toLowerCase().includes(q)
  )
  if (partial.length === 1) return partial[0]
  if (partial.length > 1) return { ambiguous: true, matches: partial }
  return null
}
