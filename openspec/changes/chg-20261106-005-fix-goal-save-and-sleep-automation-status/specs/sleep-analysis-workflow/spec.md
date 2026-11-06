## ADDED Requirements

### Requirement: 自动化进度与本次任务一致
Android 睡眠页 MUST 根据同一日期及任务编号的持久化状态展示上传、OCR、报告请求、报告生成、重试与终态。

#### Scenario: 图片上传后 OCR 排队
- **GIVEN** 自动化已收到上传任务编号
- **WHEN** 服务端返回 queued 或 running
- **THEN** 页面显示 OCR 正在排队或识别，并在安排重试时显示下次重试时间

#### Scenario: OCR 完成后报告生成
- **GIVEN** 本次 OCR 任务状态为 uploaded
- **WHEN** 自动化发起报告请求并取得报告任务编号
- **THEN** 页面更新为报告生成阶段，不继续显示等待 OCR

#### Scenario: 报告完成或失败
- **GIVEN** 本次任务有日期和任务编号
- **WHEN** 服务端返回该任务的可用报告或明确失败
- **THEN** 页面显示完成或具体失败原因；历史报告不得代替本次成功状态
