param([int[]]$Candidates = @(5173, 5300, 5301, 5302, 5303, 5304, 5305, 5306, 5307, 5308, 5309))

$ErrorActionPreference = 'Stop'
$address = [Net.IPAddress]::Parse('127.0.0.1')
foreach ($port in $Candidates) {
    if ($port -lt 1 -or $port -gt 65535) { continue }
    $listener = [Net.Sockets.TcpListener]::new($address, $port)
    try {
        $listener.Start()
        Write-Output $port
        exit 0
    } catch {
        # 系统排除端口与其他进程占用都会导致绑定失败。
    } finally {
        $listener.Stop()
    }
}
[Console]::Error.WriteLine("[start] vite_port_unavailable candidates=$($Candidates -join ',')")
exit 2
