# updateObjective 方法实现总结

## 任务信息
- **任务 ID**: Task-2 子任务
- **任务描述**: 修改 `useLearning.ts` 中的 `updateObjective` 方法，支持更新所有字段（包括新增的 duration、baseline、target_description）
- **实现时间**: 2026-06-09

## 实现内容

### 1. 方法签名变更

**修改前**：
```typescript
const updateObjective = useCallback((id: string, newTitle: string) => {
  // ...
}, [])
```

**修改后**：
```typescript
const updateObjective = useCallback((id: string, data: { 
  title?: string; 
  duration?: number; 
  baseline?: string; 
  target_description?: string 
} | string) => {
  // ...
}, [])
```

### 2. 核心特性

#### 2.1 向后兼容性
- 支持旧代码传入字符串参数（只更新标题）
- 自动检测参数类型，字符串自动转换为 `{ title: data }`

```typescript
// 旧代码（仍然有效）
updateObjective('some-id', '新标题')

// 新代码
updateObjective('some-id', { title: '新标题', duration: 30 })
```

#### 2.2 动态 SQL 构建
- 只更新传入的字段（不会覆盖其他字段）
- 使用参数化查询防止 SQL 注入
- 自动更新 `updated_at` 字段

```typescript
// 示例：只更新 duration 和 baseline
updateObjective('some-id', {
  duration: 30,
  baseline: '当前现状描述'
})
// 生成 SQL: UPDATE learning_objectives SET duration = ?, baseline = ?, updated_at = ? WHERE id = ?
```

#### 2.3 支持的字段
- `title`: 目标标题（字符串）
- `duration`: 持续天数（数字，可选）
- `baseline`: 当前现状（字符串，可选）
- `target_description`: 预期目标（字符串，可选）

### 3. 实现细节

```typescript
const updateObjective = useCallback((id: string, data: { 
  title?: string; 
  duration?: number; 
  baseline?: string; 
  target_description?: string 
} | string) => {
  getDatabase().then(db => {
    // 1. 类型检测与转换
    const updateData = typeof data === 'string' ? { title: data } : data
    
    const now = new Date().toISOString().replace('T', ' ').slice(0, 19)
    
    // 2. 动态构建 UPDATE 语句
    const fields: string[] = []
    const values: any[] = []
    
    if (updateData.title !== undefined) {
      fields.push('title = ?')
      values.push(updateData.title)
    }
    if (updateData.duration !== undefined) {
      fields.push('duration = ?')
      values.push(updateData.duration)
    }
    if (updateData.baseline !== undefined) {
      fields.push('baseline = ?')
      values.push(updateData.baseline)
    }
    if (updateData.target_description !== undefined) {
      fields.push('target_description = ?')
      values.push(updateData.target_description)
    }
    
    // 3. 始终更新 updated_at
    fields.push('updated_at = ?')
    values.push(now)
    
    // 4. 添加 WHERE 条件参数
    values.push(id)
    
    // 5. 执行更新（至少有一个字段需要更新）
    if (fields.length > 1) {
      const sql = `UPDATE learning_objectives SET ${fields.join(', ')} WHERE id = ?`
      db.runRaw(sql, values)
      db.enqueueSync('learning_objectives', id)
      setRefreshTrigger(prev => prev + 1)
    }
  })
}, [])
```

## DoD 验证

✅ **已完成**：
- [x] 方法参数支持对象格式（包含 title、duration、baseline、target_description）
- [x] 向后兼容：支持字符串参数（自动转换为 `{ title: data }`）
- [x] 动态构建 SQL 语句，只更新传入的字段
- [x] `updated_at` 字段始终自动更新
- [x] 使用参数化查询，防止 SQL 注入
- [x] 无 TypeScript 类型错误（已通过 `tsc --noEmit` 验证）

⏳ **待验证**（需要实际运行测试）：
- [ ] 旧代码调用点（`LearningPage.tsx` 中的 `onUpdate`）功能正常
- [ ] 新增字段正确写入数据库
- [ ] 部分字段更新时，其他字段保持原值
- [ ] 传入 `null` 值时正确设置为 NULL

## 兼容性说明

### 现有调用点
- **文件**: `ui/src/components/Learning/LearningPage.tsx`
- **调用**: `onUpdate={(newTitle) => updateObjective(obj.id, newTitle)}`
- **状态**: ✅ 兼容（传入字符串，自动转换为 `{ title: newTitle }`）

### 未来扩展
Task-4 将修改 `ObjectiveCard` 组件，支持编辑所有字段。届时需要：
1. 修改 `onUpdate` prop 类型：`(data: { title?: string; duration?: number; baseline?: string; target_description?: string }) => void`
2. 传递完整的对象参数，而不是单独的 `newTitle`

## 测试建议

### 单元测试
```typescript
describe('updateObjective', () => {
  it('should support string parameter (backward compatibility)', () => {
    updateObjective('id-1', '新标题')
    // 验证数据库：只有 title 和 updated_at 被更新
  })

  it('should update single field', () => {
    updateObjective('id-1', { duration: 30 })
    // 验证数据库：只有 duration 和 updated_at 被更新
  })

  it('should update multiple fields', () => {
    updateObjective('id-1', {
      title: '新标题',
      duration: 30,
      baseline: '现状',
      target_description: '目标'
    })
    // 验证数据库：所有字段都被更新
  })

  it('should handle null values', () => {
    updateObjective('id-1', { baseline: null })
    // 验证数据库：baseline 被设置为 NULL
  })
})
```

### 集成测试
1. 启动应用
2. 创建一个学习目标（只填写标题）
3. 使用旧的编辑功能（单击编辑图标，修改标题）
4. 验证标题更新成功，其他字段为空
5. 使用新的编辑功能（Task-4 完成后）
6. 填写完整信息（标题、持续时长、现状、预期目标）
7. 验证所有字段都正确保存

## 相关文件
- **实现文件**: `ui/src/hooks/useLearning.ts`
- **调用文件**: `ui/src/components/Learning/LearningPage.tsx`
- **测试清单**: `ui/src/hooks/useLearning.test-manual.md`
- **Schema 定义**: `core/models/Schema.ts`（Task-1 已完成）

## 注意事项
1. 该方法依赖 Task-1（数据库 Schema 升级）已完成
2. 新增字段在数据库中必须支持 NULL 值（旧数据兼容）
3. TypeScript 接口 `LearningObjective` 已包含新增字段的定义（可选）
4. 未来 Task-4 会修改 UI 组件以支持完整表单编辑
