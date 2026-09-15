import tempfile
import unittest
from pathlib import Path

from server.store import ServerSleepStore
from server.domain.source_reward_service import SourceRewardService


class RewardAndLearningCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ServerSleepStore(str(Path(self.temp_dir.name) / "test.db"))
        with self.store._transact() as conn:
            conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'test','x','2026-08-22 00:00:00')")
            self.store.reward_wallet_service.append_ledger_in_txn(conn, 1, 100, "test", "seed", "seed")

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass  # Windows may briefly retain SQLite WAL handles after a test process exits.

    def test_pending_and_custom_spend_modes_are_safe(self):
        templates = self.store.list_rewards(1)
        self.assertEqual({'零食', '网购'}, {item['title'] for item in templates if item['redemption_mode'] == 'custom_spend'})
        pending = self.store.create_reward(1, "稍后绑定", price=10, redemption_mode="pending_binding")
        self.assertEqual(self.store.buy_reward(1, pending), (False, "该商品暂未绑定任务，暂不能兑换"))
        snack = self.store.create_reward(1, "零食", icon="🍿", redemption_mode="custom_spend")
        self.assertEqual(self.store.buy_reward(1, snack, 12.34, "爆米花"), (True, "购买成功"))
        self.assertEqual(self.store.get_gold_balance(1), 87.66)
        self.assertEqual(self.store.buy_reward(1, snack, 1, " "), (False, "请填写购买内容"))
        self.assertEqual(self.store.buy_reward(1, snack, 1, "a" * 121), (False, "购买内容不能超过120个字"))
        self.assertFalse(self.store.buy_reward(1, snack, 12.345, "精度测试")[0])
        with self.store._connect() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?", (f"{snack}:%",)).fetchone())
            self.assertIn("爆米花", conn.execute("SELECT description FROM server_reward_ledger WHERE source_type='store_custom_spend' ORDER BY id DESC LIMIT 1").fetchone()[0])

    def test_checklist_completion_settles_learning_only_after_completion(self):
        with self.store._transact() as conn:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'O',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr',1,'o','KR',1,0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('learn',1,'kr','学习单元',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES('task',1,'清单任务',0,'2026-08-22')")
            conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty) VALUES(1,'learning_objective','o',20,20)")
        reward_item = self.store.create_reward(1, 'O 物品', price=0, unlock_source_type='learning_objective', unlock_source_id='o')
        with self.store._connect() as conn:
            self.assertEqual(('fragment', 1), tuple(conn.execute("SELECT fulfillment_mode,fragment_target_count FROM server_rewards WHERE id=?", (reward_item,)).fetchone()))
        self.store.link_learning_checklist_task(1, 'learn', 'task')
        self.store.auto_unlock_rewards(1)
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM server_learning_tasks WHERE id='learn'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT current_value FROM server_learning_krs WHERE id='kr'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT status FROM server_learning_objectives WHERE id='o'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT coins FROM server_reward_config WHERE user_id=1 AND item_type='task' AND item_id='task'").fetchone()[0], 10)
            self.assertFalse(conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_type='learning_objective_complete'").fetchone())
            self.assertFalse(conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_id LIKE ?", (f'unlock:{reward_item}:%',)).fetchone())
        with self.store._transact() as conn:
            conn.execute("UPDATE server_reward_config SET coins=7,penalty=7 WHERE user_id=1 AND item_type='task' AND item_id='task'")
        self.store.link_learning_checklist_task(1, 'learn', 'task')
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT coins FROM server_reward_config WHERE user_id=1 AND item_type='task' AND item_id='task'").fetchone()[0], 7)
        with self.store._transact() as conn:
            conn.execute("UPDATE server_tasks SET status=2,updated_at='2026-08-22 12:00:00' WHERE id='task'")
        self.store.auto_unlock_rewards(1)
        self.store.auto_unlock_rewards(1)
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM server_learning_objectives WHERE id='o'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='learning_objective_complete'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_id LIKE ?", (f'unlock:{reward_item}:%',)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE reward_id=? AND status='consumed'", (reward_item,)).fetchone()[0], 1)

    def test_learning_objective_can_bind_multiple_item_rewards(self):
        with self.store._transact() as conn:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'O',0,'2026-08-22','2026-08-22')")
        first = self.store.create_reward(1, '书', price=0, unlock_source_type='learning_objective', unlock_source_id='o')
        second = self.store.create_reward(1, '游戏', price=0, unlock_source_type='learning_objective', unlock_source_id='o')
        summary = SourceRewardService(self.store._connect).summary(1, 'learning_objective', 'o')
        self.assertEqual({first, second}, {item['id'] for item in summary['itemRewards']})
        with self.store._transact() as conn:
            conn.execute("UPDATE server_learning_objectives SET status=2 WHERE id='o'")
        self.store.auto_unlock_rewards(1)
        self.store.auto_unlock_rewards(1)
        self.assertEqual(2, len(self.store.list_backpack(1)))

    def test_cancelling_pending_checklist_link_restores_learning_without_rewards(self):
        with self.store._transact() as conn:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'O',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr',1,'o','KR',1,0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('learn',1,'kr','学习单元',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_tasks(id,user_id,title,status,raw_json,updated_at) VALUES('task',1,'清单任务',0,'{\"projectId\":\"project\"}','2026-08-22')")
        self.store.link_learning_checklist_task(1, 'learn', 'task')
        cancellation = self.store.get_learning_checklist_cancellation(1, 'learn')
        self.assertEqual({'checklist_task_id': 'task', 'project_id': 'project', 'provider_missing': False}, cancellation)
        self.assertTrue(self.store.cancel_learning_checklist_task(1, 'learn', 'task'))
        self.assertFalse(self.store.cancel_learning_checklist_task(1, 'learn', 'task'))
        with self.store._connect() as conn:
            self.assertEqual(0, conn.execute("SELECT status FROM server_learning_tasks WHERE id='learn'").fetchone()[0])
            self.assertEqual(0, conn.execute("SELECT current_value FROM server_learning_krs WHERE id='kr'").fetchone()[0])
            self.assertEqual(0, conn.execute("SELECT status FROM server_learning_objectives WHERE id='o'").fetchone()[0])
            self.assertFalse(conn.execute("SELECT 1 FROM server_learning_checklist_links WHERE learning_task_id='learn'").fetchone())
            self.assertFalse(conn.execute("SELECT 1 FROM server_reward_config WHERE item_type='task' AND item_id='task'").fetchone())

    def test_completed_checklist_link_cannot_be_cancelled(self):
        with self.store._transact() as conn:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'O',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr',1,'o','KR',1,0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('learn',1,'kr','学习单元',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_tasks(id,user_id,title,status,raw_json,updated_at) VALUES('task',1,'清单任务',2,'{\"projectId\":\"project\"}','2026-08-22')")
        self.store.link_learning_checklist_task(1, 'learn', 'task')
        self.store.auto_unlock_rewards(1)
        with self.assertRaisesRegex(ValueError, '已完成'):
            self.store.get_learning_checklist_cancellation(1, 'learn')

    def test_reopened_checklist_link_can_be_cancelled_without_reversing_rewards(self):
        with self.store._transact() as conn:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'O',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr',1,'o','KR',1,0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('learn',1,'kr','学习单元',0,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_tasks(id,user_id,title,status,raw_json,updated_at) VALUES('task',1,'清单任务',2,'{\"projectId\":\"project\"}','2026-08-22')")
            conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty) VALUES(1,'learning_objective','o',20,20)")
        self.store.link_learning_checklist_task(1, 'learn', 'task')
        self.store.auto_unlock_rewards(1)
        with self.store._transact() as conn:
            conn.execute("UPDATE server_tasks SET status=0,updated_at='2026-08-23 12:00:00' WHERE id='task'")
        self.store.auto_unlock_rewards(1)
        cancellation = self.store.get_learning_checklist_cancellation(1, 'learn')
        self.assertEqual('task', cancellation['checklist_task_id'])
        self.assertTrue(self.store.cancel_learning_checklist_task(1, 'learn', 'task'))
        with self.store._connect() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM server_learning_checklist_links WHERE learning_task_id='learn'").fetchone())
            self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='learning_objective_complete'").fetchone()[0])

    def test_deleted_checklist_link_is_removed_without_reversing_rewards(self):
        with self.store._transact() as conn:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'O',2,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr',1,'o','KR',1,1,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('learn',1,'kr','学习单元',2,'2026-08-22','2026-08-22')")
            conn.execute("INSERT INTO server_tasks(id,user_id,title,status,deleted_at,updated_at) VALUES('deleted',1,'已删除清单任务',0,'2026-08-23','2026-08-23')")
            conn.execute("INSERT INTO server_learning_checklist_links(user_id,learning_task_id,checklist_task_id,created_at) VALUES(1,'learn','deleted','2026-08-22')")
            conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty) VALUES(1,'task','deleted',10,10)")
            self.store.reward_wallet_service.append_ledger_in_txn(conn, 1, 20, 'learning_objective_complete', 'already-settled', 'already-settled')
        self.store.auto_unlock_rewards(1)
        with self.store._connect() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM server_learning_checklist_links WHERE learning_task_id='learn'").fetchone())
            self.assertFalse(conn.execute("SELECT 1 FROM server_reward_config WHERE item_type='task' AND item_id='deleted'").fetchone())
            self.assertEqual(0, conn.execute("SELECT status FROM server_learning_tasks WHERE id='learn'").fetchone()[0])
            self.assertEqual(0, conn.execute("SELECT current_value FROM server_learning_krs WHERE id='kr'").fetchone()[0])
            self.assertEqual(0, conn.execute("SELECT status FROM server_learning_objectives WHERE id='o'").fetchone()[0])
            self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_id='already-settled'").fetchone()[0])


if __name__ == '__main__':
    unittest.main()
