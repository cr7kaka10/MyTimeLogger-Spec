"""碎片合成批次的不可变来源证明。"""
from __future__ import annotations

import hashlib


class RewardFragmentProvenance:
    @staticmethod
    def _id(prefix, *parts):
        digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:32]
        return f"{prefix}:{digest}"

    @classmethod
    def record_batch(cls, conn, user_id, batch_id, reward_id, rule_version, measure_mode,
                     required_units, output_quantity, output_ledger_id, occurred_at,
                     provenance_kind="exact"):
        record_id = cls._id("fragment-batch", user_id, batch_id)
        values = (record_id, user_id, batch_id, str(reward_id), int(rule_version), measure_mode,
                  int(required_units), int(output_quantity), output_ledger_id, occurred_at,
                  provenance_kind, occurred_at, occurred_at)
        conn.execute("""INSERT OR IGNORE INTO server_reward_fragment_batches
            (id,user_id,batch_id,reward_id,rule_version,measure_mode,required_units,output_quantity,
             output_ledger_id,occurred_at,provenance_kind,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
        row = conn.execute("SELECT * FROM server_reward_fragment_batches WHERE user_id=? AND batch_id=?",
                           (user_id, batch_id)).fetchone()
        expected = values[3:11]
        actual = tuple(row[key] for key in ("reward_id", "rule_version", "measure_mode", "required_units",
                                             "output_quantity", "output_ledger_id", "occurred_at", "provenance_kind"))
        if actual != expected:
            raise ValueError("fragment_batch_conflict")
        return record_id

    @classmethod
    def append_contributions(cls, conn, user_id, batch_id, contributions, created_at):
        for fragment_id, before_units, units in contributions:
            contribution_id = cls._id("fragment-contribution", user_id, batch_id, fragment_id, before_units, units)
            conn.execute("""INSERT OR IGNORE INTO server_reward_fragment_contributions
                (id,user_id,batch_id,fragment_id,units,before_units,after_units,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (contribution_id, user_id, batch_id, fragment_id, int(units), int(before_units),
                 int(before_units) + int(units), created_at))
        return cls.summary(conn, user_id, batch_id)

    @staticmethod
    def summary(conn, user_id, batch_id):
        row = conn.execute("""SELECT batch.required_units*batch.output_quantity expected_units,
                   COALESCE(SUM(contribution.units),0) actual_units, batch.provenance_kind,
                   batch.reward_id,batch.output_ledger_id
            FROM server_reward_fragment_batches batch
            LEFT JOIN server_reward_fragment_contributions contribution
              ON contribution.user_id=batch.user_id AND contribution.batch_id=batch.batch_id
            WHERE batch.user_id=? AND batch.batch_id=? GROUP BY batch.id""", (user_id, batch_id)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def batch_for_fragment(conn, user_id, fragment_id):
        """定位碎片实际参与的精确合成批次及完整贡献，不猜测历史来源。"""
        batch = conn.execute("""SELECT batch.* FROM server_reward_fragment_contributions contribution
            JOIN server_reward_fragment_batches batch
              ON batch.user_id=contribution.user_id AND batch.batch_id=contribution.batch_id
            WHERE contribution.user_id=? AND contribution.fragment_id=?
            ORDER BY contribution.created_at DESC LIMIT 1""", (user_id, str(fragment_id))).fetchone()
        if not batch:
            return None
        result = dict(batch)
        result["contributions"] = [dict(row) for row in conn.execute(
            """SELECT * FROM server_reward_fragment_contributions
               WHERE user_id=? AND batch_id=? ORDER BY created_at,id""",
            (user_id, result["batch_id"]),
        ).fetchall()]
        action = conn.execute("""SELECT source_type FROM server_reward_ledger
            WHERE user_id=? AND source_id=? AND source_type IN ('backpack_use','backpack_discard')
            ORDER BY created_at LIMIT 1""", (user_id, result["output_ledger_id"])).fetchone()
        result["output_action"] = str(action["source_type"]) if action else None
        return result

    @classmethod
    def migrate_user(cls, conn, user_id, stamp):
        rewards = conn.execute("""SELECT r.id,r.fragment_rule_version FROM server_rewards r
            WHERE r.user_id=? AND r.fragment_measure_mode='count' AND r.fulfillment_mode='fragment'
              AND NOT EXISTS (SELECT 1 FROM server_reward_source_bindings b
                WHERE b.user_id=r.user_id AND b.reward_id=r.id
                  AND (b.drop_min_units IS NOT NULL OR b.drop_max_units IS NOT NULL))""", (user_id,)).fetchall()
        for reward in rewards:
            abnormal = conn.execute("""SELECT 1 FROM server_reward_fragments
                WHERE user_id=? AND reward_id=? AND status='active' AND expires_at>?
                  AND consumed_units=0 AND progress_units<>1 LIMIT 1""", (user_id, reward["id"], stamp)).fetchone()
            if abnormal:
                version = int(reward["fragment_rule_version"] or 1) + 1
                conn.execute("UPDATE server_rewards SET fragment_rule_version=?,updated_at=? WHERE user_id=? AND id=?",
                             (version, stamp, user_id, reward["id"]))
                conn.execute("""UPDATE server_reward_fragments SET progress_units=1,rule_version=?,updated_at=?
                    WHERE user_id=? AND reward_id=? AND status='active' AND expires_at>?
                      AND consumed_units=0""", (version, stamp, user_id, reward["id"], stamp))
        events = conn.execute("""SELECT e.fragment_id batch_id,e.reward_id,e.quantity,e.created_at,
                   r.fragment_rule_version,r.fragment_measure_mode,r.fragment_target_count,
                   MIN(l.id) output_ledger_id,COUNT(l.id) ledger_count
            FROM server_backpack_events e JOIN server_rewards r
              ON r.user_id=e.user_id AND r.id=e.reward_id
            LEFT JOIN server_reward_ledger l ON l.user_id=e.user_id AND l.source_type='reward_buy'
              AND l.source_id='unlock:'||e.reward_id||':fragment:'||e.fragment_id
            WHERE e.user_id=? AND e.event_type='fragment_composed'
            GROUP BY e.id HAVING COUNT(l.id)=1""", (user_id,)).fetchall()
        for event in events:
            if conn.execute("SELECT 1 FROM server_reward_fragment_batches WHERE user_id=? AND batch_id=?",
                            (user_id, event["batch_id"])).fetchone():
                continue
            threshold = int(event["fragment_target_count"] or 1) if event["fragment_measure_mode"] == "count" else 100
            fragments = conn.execute("""SELECT id,progress_units,consumed_units FROM server_reward_fragments
                WHERE user_id=? AND reward_id=? AND compose_batch_id=?""",
                (user_id, event["reward_id"], event["batch_id"])).fetchall()
            exact = bool(fragments) and all(int(row["progress_units"]) == int(row["consumed_units"] or 0) for row in fragments)
            exact = exact and sum(int(row["progress_units"]) for row in fragments) == threshold * int(event["quantity"])
            kind = "exact" if exact else "legacy_attested"
            cls.record_batch(conn, user_id, event["batch_id"], event["reward_id"],
                             event["fragment_rule_version"], event["fragment_measure_mode"], threshold,
                             event["quantity"], event["output_ledger_id"], event["created_at"], kind)
            if exact:
                cls.append_contributions(conn, user_id, event["batch_id"],
                                         [(row["id"], 0, row["progress_units"]) for row in fragments], event["created_at"])
