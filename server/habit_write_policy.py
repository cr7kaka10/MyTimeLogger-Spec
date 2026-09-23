"""客户端/旧 REST 只能管理本地习惯，不能写 Provider 生命周期。"""
def local_habit_write(conn, user_id, data, now):
    hid = str(data.get('id') or '')
    tombstone = conn.execute(
        "SELECT 1 FROM server_habit_tombstones WHERE user_id=? AND (habit_id=? OR provider_id=?)",
        (user_id, hid, hid)).fetchone()
    row = conn.execute("SELECT * FROM server_habits WHERE user_id=? AND id=?", (user_id, hid)).fetchone()
    if tombstone:
        raise ValueError('habit_deleted')
    if (row and row['source'] != 'local') or not hid.startswith('local_') or data.get('source', 'local') != 'local':
        raise ValueError('provider_habit_readonly')
    if row and row['is_active'] != 0:
        raise ValueError('habit_archived')
    allowed = {'id','name','icon','color','sort_order','category_id','difficulty','repeat_rule','is_active','created_at','updated_at'}
    result = {k: v for k, v in data.items() if k in allowed}
    name = result.get('name', row['name'] if row else None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError('habit_name_required')
    if 'difficulty' in result and result['difficulty'] not in {'trivial', 'easy', 'medium', 'hard'}:
        raise ValueError('invalid_habit_difficulty')
    for field in ('sort_order', 'category_id'):
        if field in result and not (field == 'category_id' and result[field] is None) and type(result[field]) is not int:
            raise ValueError('invalid_habit_integer')
    for field in ('icon', 'color', 'repeat_rule'):
        if field in result and not (field == 'repeat_rule' and result[field] is None) and not isinstance(result[field], str):
            raise ValueError('invalid_habit_text')
    if type(result.get('is_active', 0)) is not int or result.get('is_active', 0) not in (0, 1):
        raise ValueError('invalid_habit_lifecycle')
    result.update(source='local', name=name.strip())
    if result.get('is_active') == 1:
        result.update(archived_at=now, archive_reason='local_user')
    return result
