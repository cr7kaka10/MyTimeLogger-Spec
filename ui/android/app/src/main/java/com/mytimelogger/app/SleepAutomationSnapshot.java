package com.mytimelogger.app;

import org.json.JSONObject;

final class SleepAutomationSnapshot {
    final String stage, sleepDate, mediaUri, requestId, reason;
    final int attempt;
    final long updatedAt;

    SleepAutomationSnapshot(String stage, String sleepDate, String mediaUri, String requestId,
                            int attempt, String reason, long updatedAt) {
        this.stage = stage; this.sleepDate = sleepDate; this.mediaUri = mediaUri;
        this.requestId = requestId; this.attempt = attempt; this.reason = reason; this.updatedAt = updatedAt;
    }

    JSONObject json() throws Exception { return new JSONObject().put("stage", stage).put("sleepDate", sleepDate)
            .put("mediaUri", mediaUri).put("requestId", requestId).put("attempt", attempt)
            .put("reason", reason).put("updatedAt", updatedAt); }

    static SleepAutomationSnapshot parse(String raw) throws Exception { JSONObject j = new JSONObject(raw); return new SleepAutomationSnapshot(
            j.getString("stage"), j.getString("sleepDate"), j.optString("mediaUri"), j.optString("requestId"),
            j.optInt("attempt"), j.optString("reason"), j.getLong("updatedAt")); }
}
