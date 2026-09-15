import json
import re
from datetime import datetime, timedelta, timezone

SENSITIVE = re.compile(r"token|password|secret|cookie|authorization|content|text|note|body|bearer\s+", re.I)
FIELDS = ("event_id", "occurred_at", "device_id", "runtime", "page", "event_type", "action", "target_type", "target_id", "result", "error_code", "trace_id")
PAGE_LABELS = {"timer": "计时", "timebook": "时间记录", "checklist": "任务与习惯", "learning": "学习", "goals": "目标", "rewards": "奖励", "backpack": "背包", "sleep": "睡眠", "settings": "设置", "management_plan": "管理方案"}
RESULT_LABELS = {"accepted": "已受理", "succeeded": "成功", "failed": "失败", "rejected": "未通过"}

class UserBehaviorAuditService:
    def __init__(self, connect): self.connect = connect
    @staticmethod
    def present(event: dict) -> dict:
        try: metadata = json.loads(event.get("metadata_json") or "{}")
        except (TypeError, ValueError): metadata = {}
        safe = {key: str(metadata.get(key) or "") for key in ("tab", "surface", "control", "method", "path", "status")}
        path = safe["path"]
        path_surface = next((label for prefix, label in (("/api/management-plans", "management_plan"), ("/api/tasks", "checklist"), ("/api/habits", "checklist"), ("/api/learning", "learning"), ("/api/rewards", "rewards"), ("/api/goals", "goals"), ("/api/sleep", "sleep"), ("/api/sessions", "timer")) if path.startswith(prefix)), "")
        surface = safe["surface"] or safe["tab"] or path_surface or str(event.get("page") or "").strip("/")
        page_label = PAGE_LABELS.get(surface, surface or "当前页面")
        action = str(event.get("action") or "")
        if action == "navigation.tab_opened": summary = f"打开了{PAGE_LABELS.get(safe['tab'], safe['tab'] or '一个功能')}"
        elif action == "navigation.back": summary = f"从{page_label}返回"
        elif action == "control.activated": summary = f"在{page_label}中点击了“{safe['control'] or '操作按钮'}”"
        elif action == "input.changed": summary = f"在{page_label}中修改了“{safe['control'] or '输入项'}”"
        elif action == "api.request_result": summary = f"{page_label}的服务请求{RESULT_LABELS.get(str(event.get('result') or ''), '已完成')}"
        elif action == "auth.signed_in": summary = "登录了系统"
        elif action == "auth.signed_out": summary = "退出了系统"
        else: summary = f"在{page_label}中执行了系统操作"
        details = [f"结果：{RESULT_LABELS.get(str(event.get('result') or ''), str(event.get('result') or '未知'))}"]
        if safe["method"] and safe["path"]: details.append(f"请求：{safe['method']} {safe['path']}")
        if safe["status"]: details.append(f"状态码：{safe['status']}")
        if event.get("error_code"): details.append(f"错误码：{event['error_code']}")
        return {"summary": summary, "detail": "；".join(details), "page_label": page_label, "result_label": RESULT_LABELS.get(str(event.get("result") or ""), str(event.get("result") or "未知"))}

    def append(self, user_id: int, events: list[dict]) -> list[str]:
        values = []
        for event in events:
            metadata = event.get("metadata") or {}
            row = [str(event.get(field) or "") for field in FIELDS]
            encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
            invalid_meta = not isinstance(metadata, dict) or any(SENSITIVE.search(str(key)) or SENSITIVE.search(str(value)) for key, value in metadata.items())
            if invalid_meta or len(metadata) > 20 or any(len(value) > 256 for value in row) or len(encoded) > 4096 or not all(row[i] for i in (0,1,2,3,4,5,6,9)): raise ValueError("invalid_behavior_event")
            values.append((*row, encoded, user_id, datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")))
        with self.connect() as conn: conn.executemany("INSERT OR IGNORE INTO server_user_behavior_events (event_id,occurred_at,device_id,runtime,page,event_type,action,target_type,target_id,result,error_code,trace_id,metadata_json,user_id,received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        return [row[0] for row in values]
