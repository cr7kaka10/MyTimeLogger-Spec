# 修复习惯 is_active 字段
# 将所有习惯的 is_active 设置为 0（正常/未归档）

$dbPaths = @(
  "d:\WorkSpace\MyTimeLogger-Spec\desktop\local_data\my_time_logger.db",
  "d:\WorkSpace\MyTimeLogger-Spec\server\data\mtl_server.db"
)

foreach ($dbPath in $dbPaths) {
  if (Test-Path $dbPath) {
    Write-Host "处理数据库: $dbPath"
    
    # 使用 sqlite3.exe 修复
    $sqliteExe = "sqlite3.exe"
    
    & $sqliteExe $dbPath "UPDATE habits SET is_active = 0 WHERE is_active = 1;"
    & $sqliteExe $dbPath "UPDATE server_habits SET is_active = 0 WHERE is_active = 1;"
    
    Write-Host "  已将所有 is_active=1 的习惯改为 is_active=0" -ForegroundColor Green
  } else {
    Write-Host "数据库不存在: $dbPath" -ForegroundColor Yellow
  }
}

Write-Host "`n修复完成！请重启应用查看效果。" -ForegroundColor Cyan
