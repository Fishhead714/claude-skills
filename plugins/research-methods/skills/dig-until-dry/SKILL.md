---
name: dig-until-dry
description: 对一个研究主题做"循环深挖直到挖不出新东西"的全自动多轮调研——每轮结束后自动生成下一轮子问题、继续挖、每条发现都过对抗性核实，直到连续几轮无新发现（挖干）或token预算耗尽才收尾出报告，全程不需要人逐轮确认"继续吗"。用户说"帮我深挖一下XX，自动往下挖，不要每轮都停下来问我""这个主题我要穷举式地搞清楚""长期跑一下，挖到挖不动为止"时使用。跟单轮调研类 skill（例如 deep-research 一类）的区别：单轮调研是单轮扇出+核实+综合，像抽样式调研，大多数"帮我查一下XX"的请求应该用它；本 skill 是有预算兜底的多轮收敛，更贵、更慢、更彻底，只在用户明确要"自动持续/穷举/不要每轮确认"时用——不要在用户只是想要一份常规调研报告时套用，那样是无谓烧 token。也不要在问题本身很小、一两轮扇出就能覆盖的场景使用。
---

# Skill: 循环深挖 (dig-until-dry)

## 0. 这是什么

参考 GPT Researcher / Open Deep Research / Tongyi DeepResearch 这类开源自动调研项目的核心套路：
**规划子问题 → 并行检索 → 对抗性核实 → 反思"还缺什么/哪里矛盾/哪里信源单薄" → 拿反思结果生成下一轮子问题 → 循环，直到反思agent说"挖透了"才收尾。**

不是靠人工每轮"继续吗？"点头推进，是靠一个自动化的"还缺什么"判断（Reflect 阶段）来决定要不要再挖一轮，配合 token 预算兜底防止失控。

单会话内跑完，不引入跨天定时（如果之后要做"跨天持续挖同一个大课题"，需要另外加 CronCreate + 断点文件落盘，那是本 skill 当前没做的扩展方向，先不做）。

## 1. 怎么调用

主线程（你，不是子 agent）直接调用 `Workflow` 工具，`script` 参数用第 3 节的完整脚本，`args` 传：

```json
{"topic": "用户的研究主题，写清楚要回答的核心问题", "maxDryRounds": 2, "maxRounds": 8}
```

- `maxDryRounds`：连续几轮"一条新发现都没有"就判定挖干收尾，默认2，不需要用户特别要求不要改。
- `maxRounds`：硬顶轮数，防止 Reflect 阶段无限生成新子问题导致失控，默认8。这是**必须有的兜底**——`budget.remaining()` 在用户没下达 token 预算指令时恒为 `Infinity`，只靠 dry 轮数收敛不够保险。

Workflow 在后台跑，跑完你会收到 task-notification，返回值结构是 `{topic, rounds, confirmed, stopped_reason}`。

## 2. Workflow 跑完之后，主线程要做的事（脚本本身做不到，因为它没有文件系统权限）

1. **如实报告 `stopped_reason`**：`dry`（挖干了，正常收尾）还是 `budget_or_round_cap`（撞到预算/轮数上限，可能还没挖透）。这两种情况的报告措辞必须不同，不能都说"已完成调研"——命中上限时要明确告诉用户"还有余地，可以加预算/轮数再跑"，这是红线，不能省略。
2. 把 `confirmed` 里的发现按主题分组、标注置信度，写成一份带引用来源的 Markdown 报告发给用户。低置信度/单一信源的条目要单独标出，不要和高置信度的混在一起呈现。

   **行文要求**：这是顺序阅读的论证文档，不是查询表——结论先行、节标题写成结论句、表格只用于横向比较、
   承重术语首次出现就地解释。

   常见翻车：把每一条发现塞进一张大表的单元格里。那样读者拿到的是数据库不是论证——
   「按主题分组」指的是分节讲清楚，不是分行填表。
3. 判断这份报告是不是该落进知识库（用户自己项目/工作相关的主题落库，纯粹泛泛的技术调研不必强行落库）——不确定就问，不要默认都存或都不存。
4. 如果你配了完成通知（手机推送、聊天机器人等），推一条——本任务在后台跑，可能耗时数十分钟到一两小时，用户多半不在屏幕前。

## 3. Workflow 脚本

```javascript
export const meta = {
  name: 'dig-until-dry',
  description: 'Recursive loop-until-dry deep research with adversarial verification and self-generated follow-up questions',
  phases: [
    { title: 'Plan' },
    { title: 'Research' },
    { title: 'Verify' },
    { title: 'Reflect' },
  ],
}

const PLAN_SCHEMA = {
  type: 'object',
  properties: { subquestions: { type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 5 } },
  required: ['subquestions'],
}
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          source: { type: 'string' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['claim', 'source', 'confidence'],
      },
    },
  },
  required: ['findings'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: { confirmed: { type: 'boolean' }, reasoning: { type: 'string' } },
  required: ['confirmed', 'reasoning'],
}
const GAPS_SCHEMA = {
  type: 'object',
  properties: {
    gaps: { type: 'array', items: { type: 'string' }, maxItems: 5 },
    rationale: { type: 'string' },
  },
  required: ['gaps'],
}

const parsedArgs = typeof args === 'string' ? JSON.parse(args) : args
const topic = parsedArgs.topic
const maxDry = parsedArgs.maxDryRounds || 2
const maxRounds = parsedArgs.maxRounds || 8

function key(f) {
  return `${f.source || ''}::${f.claim.trim().toLowerCase()}`
}
function chunk(arr, size) {
  const out = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

phase('Plan')
const plan = await agent(
  `研究主题：${topic}\n把它拆成2-5个独立的、可以分别检索验证的子问题，覆盖主题的不同侧面。只做拆解，不要回答。`,
  { phase: 'Plan', schema: PLAN_SCHEMA }
)

const seen = new Set()
const confirmed = []
let gaps = (plan && plan.subquestions && plan.subquestions.length) ? plan.subquestions : [topic]
let dryRounds = 0
let round = 0
let stopReason = null

while (true) {
  if (dryRounds >= maxDry) { stopReason = 'dry'; break }
  if (round >= maxRounds) { stopReason = 'budget_or_round_cap'; break }
  if (budget.total && budget.remaining() < 30000) { stopReason = 'budget_or_round_cap'; break }
  if (!gaps.length) { stopReason = 'dry'; break }

  round++
  log(`第${round}轮：${gaps.length}个待挖子问题 — ${gaps.join(' / ')}`)

  const results = await parallel(gaps.map(g => () =>
    agent(
      `调研以下问题，只做信息采集，不下结论，不要自己再派发子agent：\n${g}\n\n每条发现给出：claim(具体事实)、source(来源，越具体越好，标URL或文件名)、confidence(high/medium/low，找不到权威来源就标low并如实说明)。不要编造。`,
      { phase: 'Research', label: g.slice(0, 30), schema: FINDINGS_SCHEMA }
    )
  ))

  const rawFindings = results.filter(Boolean).flatMap(r => r.findings || [])
  const fresh = rawFindings.filter(f => !seen.has(key(f)))

  if (fresh.length) {
    dryRounds = 0
    fresh.forEach(f => seen.add(key(f)))

    const verified = []
    for (const batch of chunk(fresh, 5)) {
      const batchVerified = await parallel(batch.map(f => () =>
        agent(
          `独立核实这条主张，主动尝试证伪，不要因为它看起来合理就默认成立：\n主张：${f.claim}\n声称来源：${f.source}\n给出 confirmed(布尔) 和 reasoning(为什么信/不信，找到了什么反证或佐证)。`,
          { phase: 'Verify', schema: VERDICT_SCHEMA }
        ).then(v => ({ ...f, verdict: v }))
      ))
      verified.push(...batchVerified)
    }
    const surviving = verified.filter(Boolean).filter(v => v.verdict && v.verdict.confirmed)
    confirmed.push(...surviving)
    log(`核实通过 ${surviving.length}/${fresh.length} 条`)
  } else {
    dryRounds++
    log(`本轮无新发现，连续空轮 ${dryRounds}/${maxDry}`)
    if (dryRounds >= maxDry) { stopReason = 'dry'; break }
  }

  const reflection = await agent(
    `研究主题：${topic}\n\n目前已确认的发现：\n${confirmed.map(c => `- ${c.claim}（来源：${c.source}，置信度：${c.confidence}）`).join('\n')}\n\n请判断：1) 主题还有哪些侧面完全没覆盖到 2) 哪些已确认发现之间互相矛盾、需要进一步查证 3) 哪些发现信源单薄(low confidence)、需要交叉验证。列出下一轮要挖的具体子问题（最多5个，每个必须是具体可检索的问题，不要空泛）。如果确实已经挖透了、没有值得再查的缺口，返回空列表。`,
    { phase: 'Reflect', schema: GAPS_SCHEMA }
  )
  if (!reflection) {
    gaps = []
    log('反思agent无返回，按无新缺口处理')
  } else {
    gaps = reflection.gaps || []
    log(`本轮反思：${reflection.rationale || ''}；下一轮子问题：${gaps.join(' / ') || '（无，判定挖透）'}`)
  }
}

return { topic, rounds: round, confirmed, stopped_reason: stopReason }
```

## 4. 红线（都是真实踩过的坑）

1. **每轮 Reflect 生成的子问题硬顶5个**，不要让它自由生长，否则轮数/token 双失控。Plan 阶段的初始拆解同样硬顶5个（`PLAN_SCHEMA.maxItems`），跟并发扇出宽度上限对齐。
2. **只有过了 Verify 的发现才算数**，不能直接把 Research 阶段的原始产出当结论——单轮 agent 自己说"我查到了"不构成证据，这是一次真实调研踩过的教训。
3. **`stopped_reason` 必须如实报告**，撞到轮数/预算上限跟正常挖干是两种完全不同的置信程度，不能都包装成"调研完成"。为此 Plan/Reflect 两处单发 `agent()` 调用都必须做空值兜底（脚本已加），否则一次瞬时失败就会让整个数小时的无人值守任务直接崩溃、连 `stopped_reason` 都报不出来。
4. **不要用 `general-purpose` 当 Research/Verify 步骤的默认 agent**——本脚本用的是 Workflow 默认工作 agent（无 `agentType`），意图是避免它自己再递归派单（general-purpose 自带 Agent 工具、多段式 prompt 可能被它自己拆给更多孙子 agent 吃 token，是真实踩过的教训）。这是刻意选择，不要为了"更聪明"改成 `general-purpose`；同时 Research 阶段的 prompt 里也显式写了"不要自己再派发子agent"做双保险，不要单靠工具缺失这一层假设。
5. **Verify 阶段按批次≤5并发**，不要把一整轮的 `fresh` 发现一次性全塞进 `parallel()`——多个子问题各自返回的发现累加起来可能远超5条，不分批会撞上重量级 MCP 服务器在并发扇出时的 OOM（每个子 agent 会话各起一份 MCP 进程；并发宽度上限 4-5 是真实 OOM 过之后换来的经验值，不是随便定的）。
6. **`seen` 去重键必须带 source**，不要只截断 claim 文本前若干字符当键——长句子共享前缀会被误判重复而丢发现，脚本用 `source::claim` 全文做键。
7. 主题选得太小、一两轮就能问完的，不要用这个 skill——先问自己"这个问题扇出一次是不是就够了"，够了就用单轮调研，省时间也省 token。
