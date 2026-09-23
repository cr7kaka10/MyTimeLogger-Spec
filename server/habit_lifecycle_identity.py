"""用户和绑定内的 Provider 身份；不按标题匹配，不认领未知旧行。"""


def local_habit_id(user_id, provider_id):
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("invalid_provider_habit_id")
    return f"ticktick:{int(user_id)}:{provider_id}"


def provider_habit_id(user_id, habit_id):
    prefix = f"ticktick:{int(user_id)}:"
    value = str(habit_id)
    return value[len(prefix):] if value.startswith(prefix) else value


def same_binding(row, user_id, binding_id):
    return (row.get("user_id") == user_id and row.get("source") == "ticktick"
            and row.get("provider_binding_id") == binding_id
            and bool(row.get("provider_id")))


def habit_aliases(user_id, provider_id):
    # 原生 local_ ID 不作为 raw 别名删除，避免碰撞。
    canonical = local_habit_id(user_id, provider_id)
    return [canonical] if provider_id.startswith("local_") else [canonical, provider_id]
