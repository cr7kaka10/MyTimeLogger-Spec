param([Parameter(Mandatory)][ValidateRange(1, 2147483647)][int]$WindowProcessId, [int]$Attempt = 1)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class VisibleWindow {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int x, int y, int width, int height, bool repaint);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int command);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
'@

$process = Get-Process -Id $WindowProcessId -ErrorAction Stop
$handle = $process.MainWindowHandle
if ($handle -eq [IntPtr]::Zero) { throw "window_handle_unavailable PID=$WindowProcessId attempt=$Attempt" }
$before = New-Object VisibleWindow+RECT
if (-not [VisibleWindow]::GetWindowRect($handle, [ref]$before)) { throw "Cannot read window rect for PID $WindowProcessId." }
$work = [System.Windows.Forms.Screen]::FromHandle($handle).WorkingArea
$width = $before.Right - $before.Left
$height = $before.Bottom - $before.Top
$scale = [Math]::Min(1.0, [Math]::Min(($work.Width * 0.9) / $width, ($work.Height * 0.9) / $height))
$targetWidth = [Math]::Max(1, [int][Math]::Floor($width * $scale))
$targetHeight = [Math]::Max(1, [int][Math]::Floor($height * $scale))
$targetX = $work.Left + [int](($work.Width - $targetWidth) / 2)
$targetY = $work.Top + [int](($work.Height - $targetHeight) / 2)
[void][VisibleWindow]::ShowWindowAsync($handle, 9)
if (-not [VisibleWindow]::MoveWindow($handle, $targetX, $targetY, $targetWidth, $targetHeight, $true)) { throw "Cannot move window for PID $WindowProcessId." }
Start-Sleep -Milliseconds 300
$activated = [VisibleWindow]::SetForegroundWindow($handle)
if (-not $activated) { $activated = (New-Object -ComObject WScript.Shell).AppActivate($WindowProcessId) }
$after = New-Object VisibleWindow+RECT
[void][VisibleWindow]::GetWindowRect($handle, [ref]$after)
$fullyVisible = $after.Left -ge $work.Left -and $after.Top -ge $work.Top -and $after.Right -le $work.Right -and $after.Bottom -le $work.Bottom
$summary = [pscustomobject]@{ pid=$WindowProcessId; attempt=$Attempt; before="$($before.Left),$($before.Top),$($before.Right),$($before.Bottom)"; after="$($after.Left),$($after.Top),$($after.Right),$($after.Bottom)"; work="$($work.Left),$($work.Top),$($work.Right),$($work.Bottom)"; fully_visible=$fullyVisible; activated=$activated } | ConvertTo-Json -Compress
Write-Host "[window] $summary"
if (-not $fullyVisible -or -not $activated) { throw "window_visibility_failed $summary" }
