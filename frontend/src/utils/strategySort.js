/**
 * 报表排序：策略模板只决定权重，排名统一用综合评分 score。
 * score = w1·makespan + w2·交期违约 + w3·能耗 + w4·负载CV（与排程中心权重一致）
 */

export const DEFAULT_REPORT_SORT_KEY = 'score'

export const SORT_METRICS = {
  score: {
    label: '按综合评分（推荐，含当前策略权重）',
    pick: (r) => r.score,
  },
  best_score: {
    label: '按完工时间（makespan，仅参考）',
    pick: (r) => r.best_score,
  },
}
