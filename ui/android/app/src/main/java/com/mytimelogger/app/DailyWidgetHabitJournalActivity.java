package com.mytimelogger.app;

import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import com.google.gson.JsonObject;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/** 桌面组件用户点击后显示的轻量日志窗口，不打开应用清单。 */
public final class DailyWidgetHabitJournalActivity extends AppCompatActivity {
    private static final Set<String> IN_FLIGHT = Collections.synchronizedSet(new HashSet<>());
    private TextView status;
    private JsonObject command;
    private WidgetTimerRuntimeStore.Config runtime;
    private String mood = "🙂";

    static JsonObject pendingCommand(DailyWidgetStore store, String commandId) {
        if (commandId == null || !commandId.matches("[A-Za-z0-9._:-]{1,128}")) return null;
        JsonObject snapshot = store.snapshot();
        JsonObject pending = store.pending();
        for (String key : pending.keySet()) {
            JsonObject value = pending.getAsJsonObject(key);
            if (commandId.equals(value.get("commandId").getAsString())
                    && "habit".equals(value.get("kind").getAsString())
                    && "complete".equals(value.get("action").getAsString())
                    && DailyWidgetHeadlessExecutor.valid(snapshot, value, DailyWidgetStore.today())) return value;
        }
        return null;
    }

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        DailyWidgetStore store = new DailyWidgetStore(this);
        command = pendingCommand(store, getIntent().getStringExtra("commandId"));
        if (command == null) { finish(); return; }
        String id = command.get("commandId").getAsString();
        if (!IN_FLIGHT.add(id)) { finish(); return; }
        status = new TextView(this);
        status.setPadding(32, 28, 32, 28);
        status.setText("正在确认习惯打卡…");
        setContentView(status);
        new Thread(() -> {
            DailyWidgetHeadlessExecutor.Outcome result;
            try { result = DailyWidgetHeadlessExecutor.run(getApplicationContext(), command); }
            catch (RuntimeException error) { result = new DailyWidgetHeadlessExecutor.Outcome("failed", "网络未确认，点击可重试"); }
            store.ack(id, result.status);
            DailyWidgetProvider.refresh(getApplicationContext());
            IN_FLIGHT.remove(id);
            Boolean enabled = null;
            if ("applied".equals(result.status)) {
                runtime = new WidgetTimerRuntimeStore(getApplicationContext()).read();
                if (runtime != null && runtime.verifiedUserId.equals(command.get("userId").getAsString())
                        && runtime.generation == command.get("generation").getAsLong())
                    enabled = new DailyWidgetJournalClient().promptEnabled(runtime, command.get("id").getAsString());
            }
            final DailyWidgetHeadlessExecutor.Outcome outcome = result;
            final Boolean prompt = enabled;
            runOnUiThread(() -> { if (!isFinishing() && !isDestroyed()) onResult(outcome, prompt); });
        }, "DailyHabitJournal").start();
    }

    private void onResult(DailyWidgetHeadlessExecutor.Outcome result, Boolean prompt) {
        if (!"applied".equals(result.status)) { status.setText(result.message); return; }
        if (Boolean.TRUE.equals(prompt)) showJournal();
        else if (prompt == null) { Toast.makeText(this, "打卡已记录，日志暂不可用", Toast.LENGTH_LONG).show(); finish(); }
        else { Toast.makeText(this, "习惯已记录", Toast.LENGTH_SHORT).show(); finish(); }
    }

    private void showJournal() {
        setTitle("打卡日志");
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 16, 24, 16);
        TextView title = new TextView(this);
        title.setText("打卡成功 · 记录一下今天的感受");
        root.addView(title);
        LinearLayout moods = new LinearLayout(this);
        for (String emoji : new String[] {"😭", "☹️", "😐", "🙂", "🥰"}) {
            Button button = new Button(this);
            button.setText(emoji);
            button.setAllCaps(false);
            button.setTextSize(22);
            button.setPadding(0, 0, 0, 0);
            button.setOnClickListener(view -> { mood = emoji; title.setText("已选 " + emoji + " · 记录一下今天的感受"); });
            moods.addView(button, new LinearLayout.LayoutParams(0, (int) (56 * getResources().getDisplayMetrics().density), 1));
        }
        root.addView(moods);
        EditText note = new EditText(this);
        note.setHint("今天做得怎么样？可留空");
        note.setMinLines(3);
        note.setMaxLines(6);
        root.addView(note);
        Button save = new Button(this);
        save.setText("保存日志");
        save.setOnClickListener(view -> saveJournal(save, note));
        root.addView(save);
        Button skip = new Button(this);
        skip.setText("跳过");
        skip.setOnClickListener(view -> finish());
        root.addView(skip);
        Button disable = new Button(this);
        disable.setText("以后不再提示这个习惯");
        disable.setOnClickListener(view -> disablePrompt(disable));
        root.addView(disable);
        setContentView(root);
    }

    private WidgetTimerRuntimeStore.Config currentRuntime() {
        WidgetTimerRuntimeStore.Config current = new WidgetTimerRuntimeStore(this).read();
        return current != null && runtime != null && current.generation == runtime.generation
                && current.verifiedUserId.equals(runtime.verifiedUserId) ? current : null;
    }

    private void saveJournal(Button save, EditText note) {
        String text = note.getText().toString().trim();
        if (text.length() > 1900) { Toast.makeText(this, "日志最多 1900 字", Toast.LENGTH_SHORT).show(); return; }
        WidgetTimerRuntimeStore.Config current = currentRuntime();
        if (current == null) { Toast.makeText(this, "登录状态已变化", Toast.LENGTH_SHORT).show(); return; }
        save.setEnabled(false);
        String entry = mood + (text.isEmpty() ? "" : " " + text);
        new Thread(() -> {
            boolean saved = new DailyWidgetJournalClient().save(current, command.get("id").getAsString(),
                    command.get("date").getAsString(), entry);
            runOnUiThread(() -> { if (saved) finish(); else {
                save.setEnabled(true); Toast.makeText(this, "日志保存失败，请重试", Toast.LENGTH_SHORT).show();
            } });
        }, "SaveHabitJournal").start();
    }

    private void disablePrompt(Button disable) {
        WidgetTimerRuntimeStore.Config current = currentRuntime();
        if (current == null) { Toast.makeText(this, "登录状态已变化", Toast.LENGTH_SHORT).show(); return; }
        disable.setEnabled(false);
        new Thread(() -> {
            boolean changed = new DailyWidgetJournalClient().disable(current, command.get("id").getAsString());
            runOnUiThread(() -> { if (changed) finish(); else {
                disable.setEnabled(true); Toast.makeText(this, "设置未保存，请重试", Toast.LENGTH_SHORT).show();
            } });
        }, "DisableHabitJournalPrompt").start();
    }
}
