"""只对用户明确确认的精确ID执行镜像删除；不会修改滴答远端。"""
import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.db_wrapper import ServerDBWrapper
from server.ticktick_config import load_ticktick_settings, begin_habit_round
from server.ticktick_client import TickTickClient
from server.habit_lifecycle_contract import HabitLifecycleContract, validate_habit_list
from server.habit_lifecycle_identity import provider_habit_id
from server.domain.habit_confirmed_deletion import confirm_deleted_habit


async def main(args):
    path = Path(args.database).resolve(strict=True)
    conn = sqlite3.connect(str(path)); conn.row_factory = sqlite3.Row
    uid = args.user_id; targets = []
    for value in args.target:
        hid, name = value.split('=', 1)
        row = conn.execute('SELECT * FROM server_habits WHERE user_id=? AND id=?', (uid,hid)).fetchone()
        if not row or row['name'] != name or row['source'] != 'ticktick': raise ValueError('target_identity_mismatch')
        targets.append(dict(row))
    settings = load_ticktick_settings(conn, uid)
    if not settings.enabled: raise ValueError('provider_not_configured')
    if args.apply:
        conn.execute('BEGIN IMMEDIATE'); binding, round_id = begin_habit_round(conn, uid, settings); conn.commit()
    else:
        baseline = conn.execute('SELECT binding_id,round FROM server_habit_provider_bindings WHERE user_id=?', (uid,)).fetchone()
        if not baseline: raise ValueError('habit_binding_baseline_required')
        binding, round_id = baseline
    async with TickTickClient(settings.access_token, settings.host, verify_tls=settings.verify_tls) as client:
        listed = await client.get_habits(); validate_habit_list(listed, HabitLifecycleContract(settings.host))
        ids = {row['id'] for row in listed}
        details = {row['id']: await client.get_habit_detail(provider_habit_id(uid,row['id'])) for row in targets}
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    db = ServerDBWrapper(); db.log_path = str(path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        versions = [confirm_deleted_habit(conn,db,uid,row,binding,round_id,ids,details[row['id']],args.evidence,now) for row in targets]
        conn.commit() if args.apply else conn.rollback()
        print(json.dumps(dict(applied=args.apply,names=[r['name'] for r in targets],versions=versions,time=now), ensure_ascii=False))
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True); parser.add_argument('--user-id', required=True, type=int)
    parser.add_argument('--target', required=True, action='append', help='准确的本地ID=用户确认的名称')
    parser.add_argument('--evidence', required=True); parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args()))
