# useLearning.ts - updateObjective 方法测试清单

## 测试场景

### 1. 向后兼容性测试（传入字符串）
```typescript
// 旧代码：直接传入字符串更新标题
updateObjective('some-id', '新标题')

// 预期行为：
// - 只更新 title 字段
// - updated_at 自动更新
// - 其他字段不变
```

### 2. 更新单个字段（传入对象）
```typescript
// 只更新 duration
updateObjective('some-id', { duration: 30 })

// 预期行为：
// - 只更新 duration 字段
// - updated_at 自动更新
// - title、baseline、target_description 不变
```

### 3. 更新多个字段
```typescript
// 更新所有字段
updateObjective('some-id', {
  title: '新标题',
  duration: 30,
  baseline: '当前现状描述',
  target_description: '预期目标描述'
})

// 预期行为：
// - 所有传入的字段都被更新
// - updated_at 自动更新
```

### 4. 更新部分字段
```typescript
// 只更新 title 和 baseline
updateObjective('some-id', {
  title: '新标题',
  baseline: '新的现状描述'
})

// 预期行为：
// - 只更新 title 和 baseline
// - duration 和 target_description 保持原值
// - updated_at 自动更新
```

### 5. 传入 null 值
```typescript
// 清空 baseline 字段
updateObjective('some-id', {
  baseline: null
})

// 预期行为：
// - baseline 被设置为 NULL
// - 其他字段不变
```

## 数据库验证

执行更新后，检查数据库：

```sql
SELECT id, title, duration, baseline, target_description, updated_at 
FROM learning_objectives 
WHERE id = 'some-id';
```

## 类型检查

确保没有 TypeScript 类型错误：
```bash
cd ui
npm run typecheck  # 或 tsc --noEmit
```

## DoD 检查清单

- [x] `updateObjective` 方法参数类型正确（支持字符串和对象）
- [x] 向后兼容：传入字符串时自动转换为 `{ title: data }`
- [x] 动态构建 SQL 语句，只更新传入的字段
- [x] `updated_at` 字段始终更新
- [x] 无 TypeScript 类型错误
- [ ] 需要实际运行测试验证数据库写入
