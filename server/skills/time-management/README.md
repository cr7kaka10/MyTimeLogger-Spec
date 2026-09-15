# 时间管理技能 (Time Management Skill)

整合 aTimeLogger 时间记录和华为运动健康睡眠数据，生成深度时间管理分析报告。

## 功能特性

- 📱 **aTimeLogger 数据提取** - 自动获取时间记录，处理跨天记录
- ⌚ **华为健康睡眠解析** - 从截图提取睡眠数据，计算睡眠指标
- 🤖 **AI 深度分析** - 生成洞察和改善建议
- 📊 **可视化报告** - Markdown 格式报告，含时间分配图表
- ⏰ **入睡/醒来时间计算** - 结合两项数据计算过渡时间

## 安装

Python 3.12 的基础 FastAPI 服务不包含 PaddleOCR；仅需本地截图 OCR 时，在项目根目录执行：

```pwsh
python -m pip install --requirement .\server\skills\time-management\requirements.txt
```

解析器当前使用 PaddleOCR 2.x API；外部服务配置由登录用户在服务端配置页维护，不写入此目录。

## 使用方法

### 生成完整报告

```pwsh
python generate_full_report.py 2026-03-18
```

## 报告内容

- 执行摘要和效率评分
- 睡眠数据概览（含入睡/醒来用时）
- 时间使用分析和分配图表
- 详细时间记录表
- AI 深度洞察
- 行动建议
- 数据对比（aTimeLogger vs 华为健康）

## 计算公式

- **入睡用时** = 华为健康入睡时间 - aTimeLogger「睡觉」开始时间
- **醒来用时** = aTimeLogger「睡觉」结束时间 - 华为健康醒来时间
- **睡眠周期** = 睡眠时长(分钟) / 90
- **清醒时长** = (醒来时间 - 入睡时间) - 睡眠时间

## 目录结构

```
time-management/
├── SKILL.md                 # 技能说明
├── README.md               # 本文件
├── config.example.json # 无秘密配置模板
├── generate_full_report.py # 报告生成主程序
├── modules/
│   ├── atimelogger_extractor.py
│   ├── screenshot_parser.py
│   ├── ai_analyzer.py
│   └── report_generator.py
├── huawei_health_data/     # 睡眠数据存储
└── reports/                # 报告输出目录
```

## 许可证

MIT License
