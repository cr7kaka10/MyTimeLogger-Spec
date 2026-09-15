from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from ..db_wrapper import ServerDBWrapper
except ImportError:
    from db_wrapper import ServerDBWrapper
from .reward_config_service import RewardConfigService
from .management_plan_service import ManagementPlanService
from .learning_category_service import LearningCategoryService, OUTPUT_SEED_TASK_IDS
from .default_timer_categories import DEFAULT_TIMER_CATEGORY_RECORDS

TIMER_CATEGORIES_V2_MODULE = "timer_categories_v2_19"
LEGACY_TIMER_ALIASES = {"家庭": "带娃", "车": "交通", "生活杂事": "个人杂事"}
LEGACY_TIMER_NAMES = {
    "输入", "输出", "副业生产", "副业营销", "副业研发", "吃饭", "带娃", "娱乐",
    "交通", "个人杂事", "运动", "松鼠病", "状态切换", "睡觉", "拉屎",
}
V4_DIET_RULE_KEYS = ("no_snacks", "no_sugary_drinks", "no_refined_staples")

LEARNING_OBJECTIVE = (
    "72fc7161-b6fb-4612-8d19-f90d1e0d94c3",
    "全面了解AI发展脉络 + 掌握数据标注接单技能",
)

LEARNING_KRS = [
    ("2e3df71b-c6a2-44b1-b002-3eefe1108c7f", LEARNING_OBJECTIVE[0], "KR1: 能用自己的话完整讲清AI各阶段「为什么出现、解决了什么、又卡在哪里」", 13, 0),
    ("4be2d1f4-4c03-4a80-9e26-572295309e0b", LEARNING_OBJECTIVE[0], "KR2: 能清晰描述「vibe coding变傻」背后的技术原因，并知道学界在怎么解决", 5, 0),
    ("dcc19b4b-9840-4e9d-a26e-3350b0a955b1", LEARNING_OBJECTIVE[0], "KR3: 掌握数据标注基础，完成真实标注练习，注册至少2个平台并了解接单规则（含外网赚美元）", 9, 0),
    ("c0f03d23-7e68-4997-8f43-78ab1a353b35", LEARNING_OBJECTIVE[0], "KR4: 产出一份完整「AI发展脉络」个人笔记，能随时翻阅也能讲给别人听", 5, 0),
]

LEARNING_TASKS = [
    ("e3844f52-2d7f-4bd2-9717-a88943d2ec90", LEARNING_KRS[0][0], "读懂符号主义时代（1950s-1980s）：图灵测试→专家系统，解决了什么、为什么失败，写100字总结"),
    ("d48cf77d-a301-4c5c-9f4a-4eddfafbfaeb", LEARNING_KRS[0][0], "读懂连接主义复兴（1980s-2000s）：反向传播让神经网络能训练，为什么还是没火，写100字总结"),
    ("2353511a-4a77-40d9-81a3-28d8a09dac7c", LEARNING_KRS[0][0], "读懂深度学习爆发（2012 AlexNet）：GPU+大数据+深层网络，为什么2012是分水岭，写100字总结"),
    ("63d9b345-478d-4d66-bc52-e270bfab7bfe", LEARNING_KRS[0][0], "读懂CNN→RNN→LSTM演进逻辑：图像识别解决了，序列任务为什么还需要RNN，写100字总结"),
    ("ea2ecb5f-24af-4aaa-b9d4-ec01dfd0c367", LEARNING_KRS[0][0], "读懂Attention机制的由来：LSTM处理长句子为什么会「忘事」，Attention怎么解决，写100字总结"),
    ("08e45ee1-1ec7-423c-96ce-16038e86c3c3", LEARNING_KRS[0][0], "读懂Transformer的意义（2017）：Attention Is All You Need解决了什么、带来了什么可能，写100字总结"),
    ("a68e077c-1dac-4b27-9dfc-c7abc8a24050", LEARNING_KRS[0][0], "读懂BERT vs GPT路线分歧：理解 vs 生成，两条路各解决什么问题，写对比表格"),
    ("7acc98c7-7e82-4805-8c14-0920db407338", LEARNING_KRS[0][0], "读懂GPT-3的震撼（2020）：Scaling Law是什么，为什么「大力出奇迹」，写100字总结"),
    ("1c6e42f8-0910-4ccc-8f60-fb4dbac33057", LEARNING_KRS[0][0], "读懂InstructGPT/ChatGPT的诞生：光有大模型为什么还不够用，RLHF解决了什么，写100字总结"),
    ("06bde91f-8124-4cb6-871d-544ac7552411", LEARNING_KRS[0][0], "读懂当前大模型格局：GPT-4/Claude/Gemini/LLaMA各自定位，开源vs闭源角力，写200字总结"),
    ("b2ac7bd4-2f2a-4d93-9106-b0e07cc445f9", LEARNING_KRS[0][0], "读懂当前主要局限性：幻觉、长上下文、推理弱、慢而贵——每个局限性写2句话解释清楚"),
    ("eedbbc45-0093-46a3-9d60-24a0c711d626", LEARNING_KRS[0][0], "读懂未来方向：多模态/Agent/长上下文/推理增强/端侧部署，每个方向写2句话解释清楚"),
    ("6311e8b5-d189-4a2e-9bb6-3b9bb9f1a858", LEARNING_KRS[0][0], "自测：闭卷写一条AI发展时间线，每个节点标注「解决了什么/遗留了什么」，对照资料检查漏洞"),
    ("45f9593d-6944-4135-b276-f3f584ffb3b7", LEARNING_KRS[1][0], "学习「注意力机制的上下文窗口」概念：Token是什么，上下文窗口为什么有上限，写100字总结"),
    ("b98f6960-b0b2-43df-98de-9e83015d47cc", LEARNING_KRS[1][0], "读懂「Lost in the Middle」现象：为什么信息在对话中间容易被模型遗忘，写100字总结"),
    ("8d501974-a8af-4560-a3da-088ce8fc7a13", LEARNING_KRS[1][0], "了解RAG（检索增强生成）基本思路：不把所有代码塞进对话而是检索相关片段，写100字总结"),
    ("9e1fe07e-b8ce-4380-8d86-858a745e252a", LEARNING_KRS[1][0], "了解CodeGraph/代码符号索引工具思路：为什么Cursor能比antigravity处理更大代码库，写100字总结"),
    ("dd314073-7c3d-4373-84f4-5a6b8c5db2f9", LEARNING_KRS[1][0], "整理「vibe coding为什么会变傻」个人解释文档（200字），用自己的语言写，不用术语"),
    ("7d4ccfcf-1412-40de-ae0a-8766c65f0c40", LEARNING_KRS[2][0], "了解数据标注行业全貌：国内外主流平台、任务类型与报酬范围，写200字总结"),
    ("51172094-9d41-4e3c-a0f4-e877e2aa77f5", LEARNING_KRS[2][0], "调研外网接单平台（Scale AI / Outlier / Appen / DataAnnotation.tech）的注册条件、付款方式（PayPal/Wise）、任务类型，写对比表格"),
    ("919f1c23-c294-44a2-aa73-c88e1202c295", LEARNING_KRS[2][0], "了解代码类标注的具体需求：代码正确性判断、质量评分、解释审核——Java开发者的优势在哪里，写100字总结"),
    ("17a2546a-6fa5-4f74-8d2e-f0f63d9106f0", LEARNING_KRS[2][0], "了解通用标注任务规范：文本分类、指令对偏好评分（好回答vs坏回答）、事实核查，写标注规范解读笔记"),
    ("bfcd8784-f950-49a7-85d3-f9b04855fe83", LEARNING_KRS[2][0], "实战练习：取10条Java代码片段（LeetCode/GitHub），按「正确性/可读性/有无bug」自己标注一遍"),
    ("4f2f4bf3-f610-4825-be23-7eb0e25a2942", LEARNING_KRS[2][0], "实战练习：找5组「AI回答对比题」，按「准确/有用/安全」维度做偏好标注，体会评分标准的模糊地带"),
    ("448cb5cb-5ef2-44ba-a07e-2bd5732e8393", LEARNING_KRS[2][0], "注册 Outlier 或 DataAnnotation.tech（外网，支持美元结算），完成新手资质测试，记录题型和踩坑点"),
    ("a8df9f31-80a2-462d-ade0-6a69a9d61df4", LEARNING_KRS[2][0], "注册国内标注平台（龙猫数据或MagicData），了解任务报酬范围和接单门槛，对比外网差异"),
    ("7394f830-a5d5-44a2-863c-05e1a3baf9ae", LEARNING_KRS[2][0], "整理「我能接哪类单/外网报酬大概多少/收款注意事项/Java方向优势」个人参考文档"),
    ("45eb261d-47b7-4336-bae8-7dda4edc5734", LEARNING_KRS[3][0], "整合KR1的13份小总结，合并成结构化文章"),
    ("cdf6b4cf-4ce3-4fd1-b588-c289b537dfe0", LEARNING_KRS[3][0], "加入KR2的技术归因内容，作为「当前局限性」章节的具体案例"),
    ("ad7ab20d-84c9-41e7-898b-d2b490c662ac", LEARNING_KRS[3][0], "补充「未来方向」章节：多模态/Agent/推理/效率，每个写3-5句话"),
    ("8ad7dc9e-9799-491c-84b6-6d5a19bd61eb", LEARNING_KRS[3][0], "全文通读一遍，用自己的话改掉所有「感觉是复制粘贴的」句子"),
    ("c76d84ce-ba7c-418e-a78c-92c3f8d0f59d", LEARNING_KRS[3][0], "最终自测：把这篇文章讲给完全不懂AI的人听，记录听不懂的地方并修改"),
]

EXERCISE_PLAN_SAMPLE_DATA_PATH = Path(__file__).with_name("exercise_plan_sample_data.json")

STORE_GOAL_SAMPLE_DATA = (
    ("input-output-daily-4-5h", "【天】输入+输出 ≥ 4.5h", ("输入", "输出"), 270, "daily", 20, 1),
    ("input-output-weekly-25h", "【周】输入+输出 ≥ 25h", ("输入", "输出"), 1500, "weekly", 100, 5),
    ("side-income-daily-1-5h", "【天】副业≥1.5h", ("副业生产", "副业营销", "副业研发"), 90, "daily", 20, 5),
)


class SampleDataInitializationService:
    VERSION = "20260702-server-authoritative-seed"
    STORE_REWARDS_MODULE = "store_rewards"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._change_writer = ServerDBWrapper(db_path)

    def ensure_user_sample_data(self, user_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_timer_categories(conn, user_id)
            self._ensure_learning_sample_data(conn, user_id)
            self._repair_learning_categories(conn, user_id)
            self._ensure_exercise_plan_sample_data(conn, user_id)
            store_rewards_seeded = self._ensure_store_reward_sample_data(conn, user_id)
            self._migrate_canonical_phone_reward(conn, user_id)
            RewardConfigService().materialize_user(conn, user_id)
            # 回填样例数据的稳定逻辑键（分类、学习、运动）
            ManagementPlanService._backfill_object_keys(conn, user_id, ManagementPlanService._CORE_OBJECT_SOURCES + ManagementPlanService._EXTENDED_OBJECT_SOURCES)
            conn.commit()
            return store_rewards_seeded

    def _migrate_canonical_phone_reward(self, conn: sqlite3.Connection, user_id: int) -> bool:
        now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        canonical_id = f"{user_id}:seed:reward:phone"
        legacy_ids = (f"{user_id}:seed:reward:phone-brush", f"{user_id}:seed:reward:phone-face")
        habits = conn.execute("SELECT id,name FROM server_habits WHERE user_id=? AND is_active=0 AND name IN ('刷牙','洗脸','发广告帖')", (user_id,)).fetchall()
        legacy = conn.execute("SELECT id FROM server_rewards WHERE user_id=? AND id IN (?,?)", (user_id, *legacy_ids)).fetchall()
        canonical = conn.execute("SELECT 1 FROM server_rewards WHERE user_id=? AND id=?", (user_id, canonical_id)).fetchone()
        if not legacy and not canonical:
            return False
        conn.execute("""INSERT INTO server_rewards
            (id,user_id,title,icon,price,redemption_mode,description,inventory_mode,inventory_limit,unlock_required_count,
             fulfillment_mode,fragment_target_count,fragment_rule_version,is_active,created_at,updated_at)
            VALUES (?,?,'解锁手机','📱',0,'task','多个习惯共享 100% 进度，完整卡每月最多 10 张','monthly',10,1,'fragment',100,1,1,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,icon=excluded.icon,price=0,redemption_mode='task',
            inventory_mode='monthly',inventory_limit=10,fulfillment_mode='fragment',fragment_target_count=100,is_active=1,updated_at=excluded.updated_at""",
            (canonical_id, user_id, now, now))
        sources = {(str(row["id"]), str(row["name"])) for row in habits}
        for row in conn.execute("SELECT source_id FROM server_reward_source_bindings WHERE user_id=? AND reward_id IN (?,?) AND source_type='habit'", (user_id, *legacy_ids)).fetchall():
            name = conn.execute("SELECT name FROM server_habits WHERE user_id=? AND id=?", (user_id, row["source_id"])).fetchone()
            if name and name["name"] in {"刷牙", "洗脸", "发广告帖"}: sources.add((str(row["source_id"]), str(name["name"])))
        for source_id, _name in sources:
            binding_id = f"reward-source:{canonical_id}:habit:{source_id}"
            conn.execute("""INSERT INTO server_reward_source_bindings
                (id,user_id,reward_id,source_type,source_id,drop_mode,drop_min_units,drop_max_units,created_at,updated_at)
                VALUES (?,?,?,'habit',?,'random',10,20,?,?) ON CONFLICT(user_id,reward_id,source_type,source_id)
                DO UPDATE SET drop_mode='random',drop_min_units=10,drop_max_units=20,updated_at=excluded.updated_at""",
                (binding_id, user_id, canonical_id, source_id, now, now))
            self._write_seed_change(conn, user_id, "server_reward_source_bindings", "reward_source_binding", binding_id, namespace="phone-v1")
        old_bindings = conn.execute("SELECT id FROM server_reward_source_bindings WHERE user_id=? AND reward_id IN (?,?)", (user_id, *legacy_ids)).fetchall()
        conn.execute("DELETE FROM server_reward_source_bindings WHERE user_id=? AND reward_id IN (?,?)", (user_id, *legacy_ids))
        for row in old_bindings: self._write_seed_change(conn, user_id, "server_reward_source_bindings", "reward_source_binding", row["id"], "delete", "phone-v1")
        conn.execute("UPDATE server_rewards SET is_active=0,unlock_source_type=NULL,unlock_source_id=NULL,unlock_task_id=NULL,updated_at=? WHERE user_id=? AND id IN (?,?)", (now, user_id, *legacy_ids))
        self._write_seed_change(conn, user_id, "server_rewards", "reward", canonical_id, namespace="phone-v1")
        for row in legacy: self._write_seed_change(conn, user_id, "server_rewards", "reward", row["id"], namespace="phone-v1")
        return True

    def repair_learning_categories(self, user_id: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            changed = self._repair_learning_categories(conn, user_id)
            conn.commit()
            return changed

    def repair_v4_diet_rule_keys(self, user_id: int) -> int:
        """修复已登录用户的 V4 规则身份，不重跑整套样例初始化。"""
        now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            changed = self._repair_v4_diet_rule_keys(conn, user_id, now)
            conn.commit()
            return changed

    def _repair_learning_categories(self, conn: sqlite3.Connection, user_id: int) -> int:
        def publish(txn, account_id, table, record_id, operation, fields):
            self._change_writer.write_server_change(account_id, "learning_task", record_id, operation, fields, table_name=table, conn=txn)
        return LearningCategoryService.repair_account(conn, user_id, publish)

    def _has_marker(self, conn: sqlite3.Connection, user_id: int, module: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM server_sample_data_initializations WHERE user_id=? AND module=? AND sample_data_version=?",
            (user_id, module, self.VERSION),
        ).fetchone()
        return row is not None

    def _mark(self, conn: sqlite3.Connection, user_id: int, module: str, now: str, status: str = "applied") -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO server_sample_data_initializations
              (id, user_id, module, sample_data_version, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{user_id}:{module}:{self.VERSION}", user_id, module, self.VERSION, status, now, now),
        )

    def _ensure_timer_categories(self, conn: sqlite3.Connection, user_id: int) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        marker = conn.execute(
            "SELECT status FROM server_sample_data_initializations WHERE user_id=? AND module=? AND sample_data_version=?",
            (user_id, TIMER_CATEGORIES_V2_MODULE, self.VERSION),
        ).fetchone()
        if marker:
            return marker["status"]
        rows = list(conn.execute(
            "SELECT id,name,icon,color,group_name,sort_order FROM server_categories WHERE user_id=? ORDER BY id", (user_id,),
        ))
        if not rows:
            for item in DEFAULT_TIMER_CATEGORY_RECORDS:
                cursor = conn.execute(
                    "INSERT INTO server_categories (user_id,name,icon,color,group_name,sort_order,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (user_id, item["name"], item["icon"], item["color"], item["group_name"], item["sort_order"], now),
                )
                self._write_seed_change(conn, user_id, "server_categories", "category", str(cursor.lastrowid), namespace="timer-categories-v2")
            self._mark(conn, user_id, TIMER_CATEGORIES_V2_MODULE, now, "initialized")
            return "initialized"
        canonical_rows: dict[str, sqlite3.Row] = {}
        for row in rows:
            canonical = LEGACY_TIMER_ALIASES.get(row["name"], row["name"])
            if canonical in canonical_rows:
                self._mark(conn, user_id, TIMER_CATEGORIES_V2_MODULE, now, "skipped_alias_conflict")
                return "skipped_alias_conflict"
            canonical_rows[canonical] = row
        target = {item["name"]: item for item in DEFAULT_TIMER_CATEGORY_RECORDS}
        if set(canonical_rows) == set(target) and len(rows) == len(target):
            self._mark(conn, user_id, TIMER_CATEGORIES_V2_MODULE, now, "already_current")
            return "already_current"
        if len(rows) != 15 or set(canonical_rows) != LEGACY_TIMER_NAMES:
            self._mark(conn, user_id, TIMER_CATEGORIES_V2_MODULE, now, "skipped_signature_mismatch")
            return "skipped_signature_mismatch"
        old_ids = [row["id"] for row in rows]
        before_refs = self._category_reference_counts(conn, user_id, old_ids)
        for name, row in canonical_rows.items():
            conn.execute(
                "UPDATE server_categories SET name=?,sort_order=?,updated_at=?,pushed_at=NULL WHERE id=? AND user_id=?",
                (name, target[name]["sort_order"], now, row["id"], user_id),
            )
            self._write_seed_change(conn, user_id, "server_categories", "category", str(row["id"]), namespace="timer-categories-v2")
        for name in ("工作", "家务", "休息", "活动"):
            item = target[name]
            cursor = conn.execute(
                "INSERT INTO server_categories (user_id,name,icon,color,group_name,sort_order,updated_at) VALUES (?,?,?,?,?,?,?)",
                (user_id, name, item["icon"], item["color"], item["group_name"], item["sort_order"], now),
            )
            self._write_seed_change(conn, user_id, "server_categories", "category", str(cursor.lastrowid), namespace="timer-categories-v2")
        if before_refs != self._category_reference_counts(conn, user_id, old_ids):
            raise RuntimeError("timer_category_reference_count_changed")
        self._mark(conn, user_id, TIMER_CATEGORIES_V2_MODULE, now, "upgraded")
        return "upgraded"

    @staticmethod
    def _category_reference_counts(conn: sqlite3.Connection, user_id: int, category_ids: list[int]) -> dict:
        counts = {}
        placeholders = ",".join("?" for _ in category_ids)
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not {"user_id", "category_id"}.issubset(columns):
                continue
            for category_id, count in conn.execute(
                f"SELECT category_id,COUNT(*) FROM {table} WHERE user_id=? AND category_id IN ({placeholders}) GROUP BY category_id",
                (user_id, *category_ids),
            ):
                counts[(table, category_id)] = count
        return counts

    def _ensure_learning_sample_data(self, conn: sqlite3.Connection, user_id: int) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        category_ids = LearningCategoryService.resolve_ids(conn, user_id)
        if self._has_marker(conn, user_id, "learning"):
            return
        if conn.execute("SELECT 1 FROM server_learning_objectives WHERE user_id=? LIMIT 1", (user_id,)).fetchone():
            self._mark(conn, user_id, "learning", now)
            return
        objective_id = f"{user_id}:{LEARNING_OBJECTIVE[0]}"
        kr_ids = {kr_id: f"{user_id}:{kr_id}" for kr_id, *_ in LEARNING_KRS}
        conn.execute(
            "INSERT INTO server_learning_objectives (id, user_id, title, status, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
            (objective_id, user_id, LEARNING_OBJECTIVE[1], now, now),
        )
        for kr_id, _template_objective_id, title, target_value, current_value in LEARNING_KRS:
            conn.execute(
                """
                INSERT INTO server_learning_krs
                  (id, user_id, objective_id, title, target_value, current_value, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (kr_ids[kr_id], user_id, objective_id, title, target_value, current_value, now, now),
            )
        for task_id, kr_id, title in LEARNING_TASKS:
            category_id = category_ids["输出" if task_id in OUTPUT_SEED_TASK_IDS else "输入"]
            conn.execute(
                "INSERT INTO server_learning_tasks (id, user_id, kr_id, title, status, category_id, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
                (f"{user_id}:{task_id}", user_id, kr_ids[kr_id], title, category_id, now, now),
            )
        self._mark(conn, user_id, "learning", now)

    def _ensure_exercise_plan_sample_data(self, conn: sqlite3.Connection, user_id: int) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        module = "exercise_plan"
        with EXERCISE_PLAN_SAMPLE_DATA_PATH.open("r", encoding="utf-8") as fh:
            definitions = json.load(fh)
        v1 = definitions.get("v1")
        if v1:
            v2 = json.loads(json.dumps(v1, ensure_ascii=False))
            v1.update(weekdayScore=[[0,3,"作息"],[1,7,"工作"],[2,2,"拉伸"],[3,8,"工作"],[4,8,"工作"],[5,2,"拉伸"],[6,7,"工作"]], categoryOrder=["运动","工作","拉伸","作息","守时","活动"], exercisePoints=63)
            v2.update(version="v2", sourceName="每日打卡表v2", weekdayScore=[[0,5,"检验"],[1,10,"工作"],[1,1.25,"守时","10:30"],[2,5,"拉伸"],[3,10,"工作"],[3,1.25,"守时","12:20"],[4,10,"工作"],[4,1.25,"守时","15:10"],[5,5,"拉伸"],[6,10,"工作"],[6,1.25,"守时","17:00"]], categoryOrder=["运动","工作","拉伸","检验","守时","活动"], exercisePoints=40)
            definitions["v2"] = v2
        for version, definition in definitions.items():
            self._insert_exercise_plan_definition(conn, user_id, version, definition, now)
        self._repair_v4_diet_rule_keys(conn, user_id, now)
        self._migrate_exercise_scoring(conn, user_id, definitions, now)
        self._publish_complete_exercise_v2(conn, user_id)
        first_v4_publish = not conn.execute(
            "SELECT 1 FROM server_sample_data_initializations WHERE user_id=? AND module='exercise_plan_v4'",
            (user_id,),
        ).fetchone()
        self._publish_complete_exercise_v4(conn, user_id)
        if first_v4_publish:
            previous = conn.execute(
                "SELECT value FROM server_system_config WHERE user_id=? AND key='active_exercise_plan_version'",
                (user_id,),
            ).fetchone()
            conn.execute("""INSERT INTO server_system_config(user_id,key,value,value_type,description,updated_at)
                VALUES (?,'previous_exercise_plan_version',?,'string','V4回滚前训练计划版本',?)
                ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                (user_id, previous["value"] if previous else "v2", now))
        conn.execute(
            """
            INSERT INTO server_system_config
              (user_id, key, value, value_type, description, updated_at)
            VALUES (?, 'active_exercise_plan_version', 'v4', 'string', '当前训练计划版本', ?)
            ON CONFLICT(user_id,key) DO UPDATE SET value=CASE WHEN ? THEN 'v4' ELSE value END,updated_at=excluded.updated_at
            """,
            (user_id, now, int(first_v4_publish)),
        )
        if first_v4_publish:
            self._write_seed_change(conn, user_id, "server_system_config", "system_config", "active_exercise_plan_version", namespace="exercise-v4-complete-v1")
            self._mark(conn, user_id, "exercise_plan_v4", now)
        self._mark(conn, user_id, module, now)

    def _repair_v4_diet_rule_keys(self, conn: sqlite3.Connection, user_id: int, now: str) -> int:
        changed = 0
        for sort_order, rule_key in enumerate(V4_DIET_RULE_KEYS):
            row = conn.execute("""SELECT id,rule_key FROM server_exercise_plan_diet_rules
                WHERE user_id=? AND plan_version='v4' AND sort_order=?""", (user_id, sort_order)).fetchone()
            if not row or row["rule_key"] == rule_key:
                continue
            conn.execute("UPDATE server_exercise_plan_diet_rules SET rule_key=?,updated_at=? WHERE id=? AND user_id=?",
                         (rule_key, now, row["id"], user_id))
            self._write_seed_change(conn, user_id, "server_exercise_plan_diet_rules", "exercise_plan_diet_rule", row["id"],
                                    namespace="exercise-v4-diet-key-repair-v1")
            changed += 1
        return changed

    def _publish_complete_exercise_v4(self, conn: sqlite3.Connection, user_id: int) -> None:
        namespace = "exercise-v4-complete-v1"
        tables = (
            ("server_exercise_plan_versions", "exercise_plan_version"),
            ("server_exercise_plan_schedule_items", "exercise_plan_schedule_item"),
            ("server_exercise_plan_items", "exercise_plan_item"),
            ("server_exercise_plan_progress_items", "exercise_plan_progress_item"),
            ("server_exercise_plan_diet_rules", "exercise_plan_diet_rule"),
            ("server_exercise_plan_category_rules", "exercise_plan_category_rule"),
        )
        for table, entity_type in tables:
            select_id = "version AS id" if table.endswith("versions") else "id"
            where = "version='v4'" if table.endswith("versions") else "plan_version='v4'"
            for row in conn.execute(f"SELECT {select_id} FROM {table} WHERE user_id=? AND {where} ORDER BY id", (user_id,)):
                self._write_seed_change(conn, user_id, table, entity_type, row["id"], namespace=namespace)

    def _publish_complete_exercise_v2(self, conn: sqlite3.Connection, user_id: int) -> None:
        namespace = "exercise-v2-complete-v1"
        self._write_seed_change(conn, user_id, "server_exercise_plan_versions", "exercise_plan_version", "v2", namespace=namespace)
        entities = (
            ("server_exercise_plan_schedule_items", "exercise_plan_schedule_item"),
            ("server_exercise_plan_items", "exercise_plan_item"),
            ("server_exercise_plan_progress_items", "exercise_plan_progress_item"),
            ("server_exercise_plan_diet_rules", "exercise_plan_diet_rule"),
            ("server_exercise_plan_score_rules", "exercise_plan_score_rule"),
            ("server_exercise_plan_category_rules", "exercise_plan_category_rule"),
        )
        for table, entity_type in entities:
            for row in conn.execute(f"SELECT id FROM {table} WHERE user_id=? AND plan_version='v2' ORDER BY id", (user_id,)):
                self._write_seed_change(conn, user_id, table, entity_type, row["id"], namespace=namespace)

    def _migrate_exercise_scoring(self, conn: sqlite3.Connection, user_id: int, definitions: dict, now: str) -> None:
        """幂等升级已存在账户的地点项和工作日评分规则。"""
        removed = ("到达图书馆", "离开图书馆", "到达体育公园", "达到体育公园", "离开体育公园", "结束户外锻炼")
        for version, definition in definitions.items():
            conn.execute("UPDATE server_exercise_plan_versions SET exercise_points=?,updated_at=? WHERE user_id=? AND version=?", (int(definition.get("exercisePoints") or 0), now, user_id, version))
            self._write_seed_change(conn, user_id, "server_exercise_plan_versions", "exercise_plan_version", version, namespace="exercise-v2")
            old_items = [row for row in conn.execute(
                "SELECT id,item FROM server_exercise_plan_schedule_items WHERE user_id=? AND plan_version=?",
                (user_id, version),
            ).fetchall() if str(row["item"] or "").strip().split(None, 1)[-1] in removed]
            for row in old_items:
                conn.execute("DELETE FROM server_exercise_plan_schedule_items WHERE user_id=? AND plan_version=? AND id=?", (user_id, version, row["id"]))
            for row in old_items:
                self._write_seed_change(conn, user_id, "server_exercise_plan_schedule_items", "exercise_plan_schedule_item", row["id"], "delete", "exercise-v2")
            for schedule_type, schedule_items in (("weekday", definition.get("weekdaySchedule") or []), ("rest", definition.get("restSchedule") or [])):
                for index, item in enumerate(schedule_items):
                    if "体脂" not in str(item.get("item") or ""):
                        continue
                    item_id = f"{version}-schedule-{schedule_type}-{index}"
                    conn.execute("UPDATE server_exercise_plan_schedule_items SET item=?,updated_at=? WHERE user_id=? AND plan_version=? AND id=?", (item["item"], now, user_id, version, item_id))
                    self._write_seed_change(conn, user_id, "server_exercise_plan_schedule_items", "exercise_plan_schedule_item", item_id, namespace="exercise-v2")
            rules = definition.get("weekdayScore") or []
            old_rules = conn.execute(
                "SELECT id FROM server_exercise_plan_score_rules WHERE user_id=? AND plan_version=? AND day_type='weekday'",
                (user_id, version),
            ).fetchall()
            conn.execute("DELETE FROM server_exercise_plan_score_rules WHERE user_id=? AND plan_version=? AND day_type='weekday'", (user_id, version))
            for row in old_rules:
                self._write_seed_change(conn, user_id, "server_exercise_plan_score_rules", "exercise_plan_score_rule", row["id"], "delete", "exercise-v2")
            for index, rule in enumerate(rules):
                rule_id = f"{version}-score-weekday-{index}"
                conn.execute(
                    """INSERT INTO server_exercise_plan_score_rules
                       (id,user_id,plan_version,day_type,sort_order,schedule_index,points,category,target_time,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (rule_id, user_id, version, "weekday", index, int(rule[0] or 0), float(rule[1] or 0), rule[2] or "", rule[3] if len(rule) > 3 else None, now, now),
                )
                self._write_seed_change(conn, user_id, "server_exercise_plan_score_rules", "exercise_plan_score_rule", rule_id, namespace="exercise-v2")
            old_categories = conn.execute("SELECT id FROM server_exercise_plan_category_rules WHERE user_id=? AND plan_version=?", (user_id, version)).fetchall()
            conn.execute("DELETE FROM server_exercise_plan_category_rules WHERE user_id=? AND plan_version=?", (user_id, version))
            for row in old_categories: self._write_seed_change(conn, user_id, "server_exercise_plan_category_rules", "exercise_plan_category_rule", row["id"], "delete", "exercise-v2")
            for index, category in enumerate(definition.get("categoryOrder") or []):
                category_id = f"{version}-category-{index}"
                conn.execute("INSERT INTO server_exercise_plan_category_rules (id,user_id,plan_version,sort_order,category,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (category_id,user_id,version,index,category,now,now))
                self._write_seed_change(conn, user_id, "server_exercise_plan_category_rules", "exercise_plan_category_rule", category_id, namespace="exercise-v2")
        conn.execute("INSERT OR REPLACE INTO server_sample_data_initializations (id,user_id,module,sample_data_version,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (f"{user_id}:exercise_plan:scoring-v3", user_id, "exercise_plan_scoring", "scoring-v3", "applied", now, now))

    def _ensure_store_reward_sample_data(self, conn: sqlite3.Connection, user_id: int) -> bool:
        module, now = self.STORE_REWARDS_MODULE, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self._has_marker(conn, user_id, module):
            return False
        if conn.execute("SELECT 1 FROM server_rewards WHERE user_id=? LIMIT 1", (user_id,)).fetchone():
            self._mark(conn, user_id, module, now)
            return False
        required_category_names = ("输入", "输出", "副业生产", "副业营销", "副业研发")
        placeholders = ",".join("?" for _ in required_category_names)
        categories = conn.execute(
            f"SELECT id, name FROM server_categories WHERE user_id=? AND name IN ({placeholders})",
            (user_id, *required_category_names),
        ).fetchall()
        category_ids = {name: [row["id"] for row in categories if row["name"] == name] for name in required_category_names}
        habits = conn.execute(
            "SELECT id, name FROM server_habits WHERE user_id=? AND is_active=0 AND name IN ('刷牙', '洗脸')", (user_id,)
        ).fetchall()
        habit_ids = {name: [row["id"] for row in habits if row["name"] == name] for name in ("刷牙", "洗脸")}
        if any(len(category_ids[name]) != 1 for name in category_ids) or any(len(habit_ids[name]) != 1 for name in habit_ids):
            return False
        goal_ids = {}
        for key, title, category_names, target_value, period, reward_coins, penalty_coins in STORE_GOAL_SAMPLE_DATA:
            goal_id = f"{user_id}:seed:goal:{key}"
            goal_ids[key] = goal_id
            selected_category_ids = [category_ids[name][0] for name in category_names]
            conn.execute(
                "INSERT OR IGNORE INTO server_goals (id, user_id, title, category_id, metric, target_value, period, operator, reward_coins, reward_id, penalty_coins, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, 'duration', ?, ?, '>=', ?, NULL, ?, 1, ?, ?)",
                (goal_id, user_id, title, selected_category_ids[0], target_value, period, reward_coins, penalty_coins, now, now),
            )
            self._write_seed_change(conn, user_id, "server_goals", "goal", goal_id)
            for category_id in selected_category_ids:
                binding_id = f"goal-category:{goal_id}:{category_id}"
                conn.execute(
                    "INSERT OR IGNORE INTO server_goal_category_bindings (id, user_id, goal_id, category_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (binding_id, user_id, goal_id, category_id, now, now),
                )
                self._write_seed_change(conn, user_id, "server_goal_category_bindings", "goal_category_binding", binding_id)
        rewards = (
            ("fly", "来一发", "✈️", "每日输入+输出 ≥ 4.5h，可得【来一发】卡", "goal", goal_ids["input-output-daily-4-5h"], "【天】输入+输出 ≥ 4.5h", "unlimited", None, 1),
            ("phone-brush", "解锁手机*1", "📱", "一周刷牙 5 次，可以解锁手机 1 次", "habit", habit_ids["刷牙"][0], "刷牙", "weekly", 1, 5),
            ("phone-face", "解锁手机*1", "📱", "一周洗脸 7 次，可以解锁手机 1 次", "habit", habit_ids["洗脸"][0], "洗脸", "weekly", 1, 7),
            ("day-out", "出去玩一天", "🏖️", "每周输入+输出 ≥ 25h，可得【出去玩一天】卡", "goal", goal_ids["input-output-weekly-25h"], "【周】输入+输出 ≥ 25h", "unlimited", None, 1),
        )
        for key, title, icon, description, source_type, source_id, source_title, inventory_mode, inventory_limit, required_count in rewards:
            reward_id = f"{user_id}:seed:reward:{key}"
            legacy_id = f"goal_{source_id}" if source_type == "goal" else None
            conn.execute(
                "INSERT OR IGNORE INTO server_rewards (id, user_id, title, icon, price, description, unlock_task_id, unlock_task_title, unlock_source_type, unlock_source_id, inventory_mode, inventory_limit, unlock_required_count, unlock_threshold_started_at, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (reward_id, user_id, title, icon, description, legacy_id, source_title, source_type, source_id, inventory_mode, inventory_limit, required_count, now if source_type == "habit" else None, now, now),
            )
            self._write_seed_change(conn, user_id, "server_rewards", "reward", reward_id)
        self._mark(conn, user_id, module, now)
        return True

    def _write_seed_change(self, conn: sqlite3.Connection, user_id: int, table_name: str, entity_type: str, entity_id: str, operation: str = "upsert", namespace: str = "seed") -> None:
        change_id = f"{namespace}:{user_id}:{entity_id}:{operation}"
        if conn.execute("SELECT 1 FROM server_change_log WHERE user_id=? AND change_id=?", (user_id, change_id)).fetchone():
            return
        self._change_writer.write_server_change(
            user_id, entity_type, entity_id, operation, {"id": entity_id},
            change_id=change_id, table_name=table_name, conn=conn,
        )

    def _insert_exercise_plan_definition(
        self,
        conn: sqlite3.Connection,
        user_id: int,
        version: str,
        definition: dict,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO server_exercise_plan_versions
              (version, user_id, title, source_name, is_active, exercise_points, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                version,
                user_id,
                definition.get("title") or "每日打卡表",
                definition.get("sourceName") or "",
                int(definition.get("exercisePoints") or 0),
                now,
                now,
            ),
        )
        for schedule_type, items in (
            ("weekday", definition.get("weekdaySchedule") or []),
            ("rest", definition.get("restSchedule") or []),
            ("sunday_extra", [definition.get("sundayExtra") or {}]),
        ):
            for index, item in enumerate(items):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO server_exercise_plan_schedule_items
                      (id, user_id, plan_version, schedule_type, sort_order, time, item, note, accent, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{version}-schedule-{schedule_type}-{index}",
                        user_id,
                        version,
                        schedule_type,
                        index,
                        item.get("time") or "",
                        item.get("item") or "",
                        item.get("note") or "",
                        item.get("accent") or "default",
                        now,
                        now,
                    ),
                )
        for index, item in enumerate(definition.get("diet") or []):
            conn.execute(
                """
                INSERT OR IGNORE INTO server_exercise_plan_diet_rules
                  (id, user_id, plan_version, rule_key, sort_order, time, content, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{version}-diet-{index}",
                    user_id,
                    version,
                    item.get("ruleKey"),
                    index,
                    item.get("time") or "",
                    item.get("content") or "",
                    item.get("note") or "",
                    now,
                    now,
                ),
            )
        score_groups = (
            ("weekday", definition.get("weekdayScore") or []),
            ("saturday", definition.get("saturdayScore") or []),
            ("sunday", definition.get("sundayScore") or []),
        )
        for day_type, rules in score_groups:
            for index, rule in enumerate(rules):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO server_exercise_plan_score_rules
                      (id, user_id, plan_version, day_type, sort_order, schedule_index, points, category, target_time, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{version}-score-{day_type}-{index}",
                        user_id,
                        version,
                        day_type,
                        index,
                        int(rule[0] or 0),
                        float(rule[1] or 0),
                        rule[2] or "",
                        rule[3] if len(rule) > 3 else None,
                        now,
                        now,
                    ),
                )
        for index, category in enumerate(definition.get("categoryOrder") or []):
            conn.execute(
                """
                INSERT OR IGNORE INTO server_exercise_plan_category_rules
                  (id, user_id, plan_version, sort_order, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"{version}-category-{index}", user_id, version, index, category, now, now),
            )
        for index, item in enumerate(definition.get("progress") or []):
            conn.execute(
                """
                INSERT OR IGNORE INTO server_exercise_plan_progress_items
                  (id, user_id, plan_version, sort_order, when_text, text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"{version}-progress-{index}", user_id, version, index, item.get("when") or "", item.get("text") or "", now, now),
            )
        for day_key, day in (definition.get("exercisePlan") or {}).items():
            for variant in ("gym", "rain"):
                for index, item in enumerate(day.get(variant) or []):
                    tags = dict(item)
                    tags["label"] = day.get("label") or day_key
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO server_exercise_plan_items
                          (id, user_id, plan_version, day_key, variant, section, sort_order, name, sets, intensity, tags_json, progression, color, is_active, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            f"{version}-{day_key}-{variant}-{index}",
                            user_id,
                            version,
                            day_key,
                            variant,
                            item.get("s") or "",
                            index,
                            item.get("name") or "",
                            item.get("sets") or "",
                            item.get("intensity") or "",
                            json.dumps(tags, ensure_ascii=False),
                            item.get("prog"),
                            day.get("color"),
                            now,
                            now,
                        ),
                    )
