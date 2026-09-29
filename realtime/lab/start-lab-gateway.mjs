// 小科实验助手 — 实时语音 Gateway 启动器：
// 实时语音前台（DashScope Qwen Audio）+ 后台 = 实验助手 Python 后端。
// 用法：
//   DASHSCOPE_API_KEY=... node lab/start-lab-gateway.mjs

// Node 18+ 内置 fetch (undici) 不读 NODE_TLS_REJECT_UNAUTHORIZED，
// 必须显式设置 dispatcher 才能接受自签名 HTTPS 证书。
import { setGlobalDispatcher, Agent } from 'undici'
setGlobalDispatcher(new Agent({ connect: { rejectUnauthorized: false } }))

import { createGatewayApplication } from '../server/src/app/gateway-application.mjs'
import { createBackendAgentHost } from '../server/src/backend/backend-adapter-sdk.mjs'
import { createLabAssistantBackend } from './lab-assistant-backend.mjs'

const agent = createBackendAgentHost(createLabAssistantBackend())
const application = createGatewayApplication({
  agent,
  spawnThinkingDescription: [
    '【定位】你是实验助手，通过工具直接操作实验数据。',
    '【核心原则】所有实验操作都通过工具完成，不要用自由聊天替代。',
    '【实验记录原则】没有任何字段是必填的；用户说了什么就记什么，没说的留空；不要追问缺失字段；只有用户明确说"下一步/进入下一步"才推进，否则停在当前步。',
    '【常用工具】',
    '• 查当前步骤/导航：get_current_step, navigate_view, get_protocol_detail',
    '• 记录数据/推进步骤：record_observation, move_step',
    '• 计时：start_timer, check_timer, start_step_timer',
    '• 库存管理：list_storage_items, add_storage_item, update_storage_item',
    '• 方案管理：list_protocols, select_protocol',
    '• 计算与时间：calculate, get_current_time, generate_schedule',
    '• 试剂查询：list_reagent_preps, check_reagent_safety',
    '• 知识库检索：search_knowledge_base(query="关键词") — 查引物表/抗体表等已上传表格；禁止用联网搜索查引物',
    '• 实验记忆：list_experiment_memory, save_experiment_memory',
    '【边界】工具返回失败时不要声称已完成；不要假装查过或做过；用本地工具数据替代通用知识。',
  ].join(''),
})

async function shutdown(signal) {
  console.log(`[lab-gateway] received ${signal}, shutting down`)
  try {
    await application.close()
  } catch (error) {
    console.error('[lab-gateway] close error', error)
  }
  process.exit(0)
}

process.once('SIGINT', () => void shutdown('SIGINT'))
process.once('SIGTERM', () => void shutdown('SIGTERM'))