export const LEARNING_SEED_OBJECTIVE = {
  id: '72fc7161-b6fb-4612-8d19-f90d1e0d94c3',
  title: '全面了解AI发展脉络 + 掌握数据标注接单技能',
}

export const LEARNING_SEED_KRS = [
  { id: '2e3df71b-c6a2-44b1-b002-3eefe1108c7f', objective_id: LEARNING_SEED_OBJECTIVE.id, title: 'KR1: 能用自己的话完整讲清AI各阶段「为什么出现、解决了什么、又卡在哪里」', target_value: 13, current_value: 0 },
  { id: '4be2d1f4-4c03-4a80-9e26-572295309e0b', objective_id: LEARNING_SEED_OBJECTIVE.id, title: 'KR2: 能清晰描述「vibe coding变傻」背后的技术原因，并知道学界在怎么解决', target_value: 5, current_value: 0 },
  { id: 'dcc19b4b-9840-4e9d-a26e-3350b0a955b1', objective_id: LEARNING_SEED_OBJECTIVE.id, title: 'KR3: 掌握数据标注基础，完成真实标注练习，注册至少2个平台并了解接单规则（含外网赚美元）', target_value: 9, current_value: 0 },
  { id: 'c0f03d23-7e68-4997-8f43-78ab1a353b35', objective_id: LEARNING_SEED_OBJECTIVE.id, title: 'KR4: 产出一份完整「AI发展脉络」个人笔记，能随时翻阅也能讲给别人听', target_value: 5, current_value: 0 },
]

const KR1 = '2e3df71b-c6a2-44b1-b002-3eefe1108c7f'
const KR2 = '4be2d1f4-4c03-4a80-9e26-572295309e0b'
const KR3 = 'dcc19b4b-9840-4e9d-a26e-3350b0a955b1'
const KR4 = 'c0f03d23-7e68-4997-8f43-78ab1a353b35'

const OUTPUT_SEED_TASK_IDS = new Set([
  '6311e8b5-d189-4a2e-9bb6-3b9bb9f1a858', 'dd314073-7c3d-4373-84f4-5a6b8c5db2f9',
  'bfcd8784-f950-49a7-85d3-f9b04855fe83', '4f2f4bf3-f610-4825-be23-7eb0e25a2942',
  '448cb5cb-5ef2-44ba-a07e-2bd5732e8393', 'a8df9f31-80a2-462d-ade0-6a69a9d61df4',
  '7394f830-a5d5-44a2-863c-05e1a3baf9ae', '45eb261d-47b7-4336-bae8-7dda4edc5734',
  'cdf6b4cf-4ce3-4fd1-b588-c289b537dfe0', 'ad7ab20d-84c9-41e7-898b-d2b490c662ac',
  '8ad7dc9e-9799-491c-84b6-6d5a19bd61eb', 'c76d84ce-ba7c-418e-a78c-92c3f8d0f59d',
])

const LEGACY_LEARNING_SEED_TASKS = [
  { id: 'e3844f52-2d7f-4bd2-9717-a88943d2ec90', kr_id: KR1, title: '读懂符号主义时代（1950s-1980s）：图灵测试→专家系统，解决了什么、为什么失败，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'd48cf77d-a301-4c5c-9f4a-4eddfafbfaeb', kr_id: KR1, title: '读懂连接主义复兴（1980s-2000s）：反向传播让神经网络能训练，为什么还是没火，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '2353511a-4a77-40d9-81a3-28d8a09dac7c', kr_id: KR1, title: '读懂深度学习爆发（2012 AlexNet）：GPU+大数据+深层网络，为什么2012是分水岭，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '63d9b345-478d-4d66-bc52-e270bfab7bfe', kr_id: KR1, title: '读懂CNN→RNN→LSTM演进逻辑：图像识别解决了，序列任务为什么还需要RNN，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'ea2ecb5f-24af-4aaa-b9d4-ec01dfd0c367', kr_id: KR1, title: '读懂Attention机制的由来：LSTM处理长句子为什么会「忘事」，Attention怎么解决，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '08e45ee1-1ec7-423c-96ce-16038e86c3c3', kr_id: KR1, title: '读懂Transformer的意义（2017）：Attention Is All You Need解决了什么、带来了什么可能，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'a68e077c-1dac-4b27-9dfc-c7abc8a24050', kr_id: KR1, title: '读懂BERT vs GPT路线分歧：理解 vs 生成，两条路各解决什么问题，写对比表格', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '7acc98c7-7e82-4805-8c14-0920db407338', kr_id: KR1, title: '读懂GPT-3的震撼（2020）：Scaling Law是什么，为什么「大力出奇迹」，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '1c6e42f8-0910-4ccc-8f60-fb4dbac33057', kr_id: KR1, title: '读懂InstructGPT/ChatGPT的诞生：光有大模型为什么还不够用，RLHF解决了什么，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '06bde91f-8124-4cb6-871d-544ac7552411', kr_id: KR1, title: '读懂当前大模型格局：GPT-4/Claude/Gemini/LLaMA各自定位，开源vs闭源角力，写200字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'b2ac7bd4-2f2a-4d93-9106-b0e07cc445f9', kr_id: KR1, title: '读懂当前主要局限性：幻觉、长上下文、推理弱、慢而贵——每个局限性写2句话解释清楚', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'eedbbc45-0093-46a3-9d60-24a0c711d626', kr_id: KR1, title: '读懂未来方向：多模态/Agent/长上下文/推理增强/端侧部署，每个方向写2句话解释清楚', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '6311e8b5-d189-4a2e-9bb6-3b9bb9f1a858', kr_id: KR1, title: '自测：闭卷写一条AI发展时间线，每个节点标注「解决了什么/遗留了什么」，对照资料检查漏洞', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '45f9593d-6944-4135-b276-f3f584ffb3b7', kr_id: KR2, title: '学习「注意力机制的上下文窗口」概念：Token是什么，上下文窗口为什么有上限，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'b98f6960-b0b2-43df-98de-9e83015d47cc', kr_id: KR2, title: '读懂「Lost in the Middle」现象：为什么信息在对话中间容易被模型遗忘，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '8d501974-a8af-4560-a3da-088ce8fc7a13', kr_id: KR2, title: '了解RAG（检索增强生成）基本思路：不把所有代码塞进对话而是检索相关片段，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '9e1fe07e-b8ce-4380-8d86-858a745e252a', kr_id: KR2, title: '了解CodeGraph/代码符号索引工具思路：为什么Cursor能比antigravity处理更大代码库，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'dd314073-7c3d-4373-84f4-5a6b8c5db2f9', kr_id: KR2, title: '整理「vibe coding为什么会变傻」个人解释文档（200字），用自己的语言写，不用术语', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '7d4ccfcf-1412-40de-ae0a-8766c65f0c40', kr_id: KR3, title: '了解数据标注行业全貌：国内外主流平台（Scale AI、Outlier、龙猫、MagicData等），任务类型与报酬范围，写200字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '51172094-9d41-4e3c-a0f4-e877e2aa77f5', kr_id: KR3, title: '调研外网接单平台（Scale AI / Outlier / Appen / DataAnnotation.tech）的注册条件、付款方式（PayPal/Wise）、任务类型，写对比表格', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '919f1c23-c294-44a2-aa73-c88e1202c295', kr_id: KR3, title: '了解代码类标注的具体需求：代码正确性判断、质量评分、解释审核——Java开发者的优势在哪里，写100字总结', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '17a2546a-6fa5-4f74-8d2e-f0f63d9106f0', kr_id: KR3, title: '了解通用标注任务规范：文本分类、指令对偏好评分（好回答vs坏回答）、事实核查，写标注规范解读笔记', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'bfcd8784-f950-49a7-85d3-f9b04855fe83', kr_id: KR3, title: '实战练习：取10条Java代码片段（LeetCode/GitHub），按「正确性/可读性/有无bug」自己标注一遍', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '4f2f4bf3-f610-4825-be23-7eb0e25a2942', kr_id: KR3, title: '实战练习：找5组「AI回答对比题」，按「准确/有用/安全」维度做偏好标注，体会评分标准的模糊地带', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '448cb5cb-5ef2-44ba-a07e-2bd5732e8393', kr_id: KR3, title: '注册 Outlier 或 DataAnnotation.tech（外网，支持美元结算），完成新手资质测试，记录题型和踩坑点', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'a8df9f31-80a2-462d-ade0-6a69a9d61df4', kr_id: KR3, title: '注册国内标注平台（龙猫数据或MagicData），了解任务报酬范围和接单门槛，对比外网差异', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '7394f830-a5d5-44a2-863c-05e1a3baf9ae', kr_id: KR3, title: '整理「我能接哪类单/外网报酬大概多少/收款注意事项/Java方向优势」个人参考文档', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '45eb261d-47b7-4336-bae8-7dda4edc5734', kr_id: KR4, title: '整合KR1的13份小总结，合并成结构化文章（时间线+每阶段：背景/突破/局限）', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'cdf6b4cf-4ce3-4fd1-b588-c289b537dfe0', kr_id: KR4, title: '加入KR2的技术归因内容，作为「当前局限性」章节的具体案例', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'ad7ab20d-84c9-41e7-898b-d2b490c662ac', kr_id: KR4, title: '补充「未来方向」章节：多模态/Agent/推理/效率，每个写3-5句话', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: '8ad7dc9e-9799-491c-84b6-6d5a19bd61eb', kr_id: KR4, title: '全文通读一遍，用自己的话改掉所有「感觉是复制粘贴的」句子', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
  { id: 'c76d84ce-ba7c-418e-a78c-92c3f8d0f59d', kr_id: KR4, title: '最终自测：把这篇文章讲给完全不懂AI的人听，记录听不懂的地方并修改', status: 0, category_id: null, priority: 0, reward: 0, due_date: null },
]

export const LEARNING_SEED_TASKS = LEGACY_LEARNING_SEED_TASKS.map(({ category_id: _legacyCategory, ...task }) => ({
  ...task,
  category_name: OUTPUT_SEED_TASK_IDS.has(task.id) ? '输出' as const : '输入' as const,
}))
