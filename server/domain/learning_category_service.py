"""学习任务输入/输出分类的唯一真值与历史修复。"""
from datetime import datetime
from zoneinfo import ZoneInfo

VALID_LEARNING_CATEGORIES = ("输入", "输出")
OUTPUT_SEED_TASK_IDS = {
    "6311e8b5-d189-4a2e-9bb6-3b9bb9f1a858", "dd314073-7c3d-4373-84f4-5a6b8c5db2f9",
    "bfcd8784-f950-49a7-85d3-f9b04855fe83", "4f2f4bf3-f610-4825-be23-7eb0e25a2942",
    "448cb5cb-5ef2-44ba-a07e-2bd5732e8393", "a8df9f31-80a2-462d-ade0-6a69a9d61df4",
    "7394f830-a5d5-44a2-863c-05e1a3baf9ae", "45eb261d-47b7-4336-bae8-7dda4edc5734",
    "cdf6b4cf-4ce3-4fd1-b588-c289b537dfe0", "ad7ab20d-84c9-41e7-898b-d2b490c662ac",
    "8ad7dc9e-9799-491c-84b6-6d5a19bd61eb", "c76d84ce-ba7c-418e-a78c-92c3f8d0f59d",
}


class LearningCategoryError(ValueError):
    code = "invalid_learning_category"


class LearningCategoryService:
    VERSION = "20260814-learning-category-integrity-v1"

    @staticmethod
    def resolve_ids(conn, user_id: int) -> dict[str, int]:
        rows = conn.execute(
            "SELECT id,name FROM server_categories WHERE user_id=? AND name IN ('输入','输出')", (user_id,),
        ).fetchall()
        result = {str(row["name"]): int(row["id"]) for row in rows}
        if set(result) != set(VALID_LEARNING_CATEGORIES):
            raise LearningCategoryError("学习分类配置缺失：必须同时存在输入和输出")
        return result

    @classmethod
    def validate_id(cls, conn, user_id: int, category_id) -> int:
        if category_id is None or isinstance(category_id, bool):
            raise LearningCategoryError("学习任务必须选择输入或输出分类")
        row = conn.execute("SELECT name FROM server_categories WHERE user_id=? AND id=?", (user_id, category_id)).fetchone()
        if not row or str(row["name"]) not in VALID_LEARNING_CATEGORIES:
            raise LearningCategoryError("学习任务分类无效，必须使用当前账号的输入或输出")
        return int(category_id)

    @classmethod
    def repair_account(cls, conn, user_id: int, record_change=None) -> int:
        if not conn.execute("SELECT 1 FROM server_learning_tasks WHERE user_id=? LIMIT 1", (user_id,)).fetchone():
            return 0
        category_ids = cls.resolve_ids(conn, user_id)
        rows = conn.execute("""SELECT t.id FROM server_learning_tasks t
            LEFT JOIN server_categories c ON c.id=t.category_id AND c.user_id=t.user_id
            WHERE t.user_id=? AND (c.id IS NULL OR c.name NOT IN ('输入','输出'))""", (user_id,)).fetchall()
        now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            task_id = str(row["id"]); seed_id = task_id.rsplit(":", 1)[-1]
            name = "输出" if seed_id in OUTPUT_SEED_TASK_IDS else "输入"
            conn.execute("UPDATE server_learning_tasks SET category_id=?,updated_at=? WHERE id=? AND user_id=?", (category_ids[name], now, task_id, user_id))
            if record_change:
                record_change(conn, user_id, "server_learning_tasks", task_id, "upsert", {"id": task_id, "category_id": category_ids[name], "updated_at": now})
        invalid = conn.execute("""SELECT COUNT(*) FROM server_learning_tasks t LEFT JOIN server_categories c
            ON c.id=t.category_id AND c.user_id=t.user_id WHERE t.user_id=? AND (c.id IS NULL OR c.name NOT IN ('输入','输出'))""", (user_id,)).fetchone()[0]
        if invalid:
            raise LearningCategoryError("学习任务分类修复未通过完整性检查")
        conn.execute("""INSERT OR IGNORE INTO server_sample_data_initializations
            (id,user_id,module,sample_data_version,status,created_at,updated_at) VALUES(?,?,'learning_categories',?,'applied',?,?)""",
            (f"{user_id}:learning_categories:{cls.VERSION}", user_id, cls.VERSION, now, now))
        return len(rows)
