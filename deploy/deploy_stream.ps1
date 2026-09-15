$path = $args[0]
if (-Not (Test-Path $path)) {
    Write-Error "File not found: $path"
    exit 1
}
$size = (Get-Item $path).Length
$stream = [System.IO.File]::OpenRead($path)
$buffer = New-Object byte[] 65536
$stdout = [System.Console]::OpenStandardOutput()
$total = 0
$last = (Get-Date)

while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
    $stdout.Write($buffer, 0, $read)
    $total += $read
    if ((Get-Date) - $last -gt [TimeSpan]::FromMilliseconds(500)) {
        $p = [math]::Floor(($total / $size) * 100)
        Write-Progress -Activity 'Uploading Payload (Do NOT close window)' -Status "$p% Complete" -PercentComplete $p
        $last = (Get-Date)
    }
}
Write-Progress -Activity 'Uploading Payload' -Completed
$stream.Close()
