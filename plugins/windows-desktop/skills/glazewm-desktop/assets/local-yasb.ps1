<#
  本机负载 · YASB 状态栏专用（一次性取数版）
  数据来自本机 CIM，不联网。输出 JSON：brief 给状态栏，detail 给点开后的明细。

  多屏共享缓存：YASB 每块屏各有一份组件、各自定时调本脚本（前后差约 1 秒），各取各的会让两块屏
  数字对不上。所以先到的那份取数并写缓存，后到的在互斥锁上等它写完、直接读缓存——两块屏同一份数据。

  用法： powershell -NoProfile -ExecutionPolicy Bypass -File local-yasb.ps1
  注意：本文件必须保存为「UTF-8 带 BOM」，否则 PowerShell 5.1 读中文会乱码。
#>

$Config = @{
  Name = 'local'
  Warn = 60; Hot = 85          # CPU：橙 / 红
  MemWarn = 80; MemHot = 90
  DiskWarn = 85; DiskHot = 95
  CacheTtlSec = 3              # 须小于 YASB 的 run_interval（5 秒），保证每轮都会真正取一次数
}
$CacheFile = Join-Path $env:LOCALAPPDATA 'yasb-load-cache\local.json'

function Get-Level([double]$v, [double]$warn, [double]$hot) { if ($v -ge $hot) { 2 } elseif ($v -ge $warn) { 1 } else { 0 } }

function Get-LocalJson {
  # LoadPercentage 是最近一秒的平均值，单次查询即可；PerfFormattedData 在新进程里首次取样常为 0，故不用
  $cpu  = [double](Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
  $os   = Get-CimInstance Win32_OperatingSystem
  $memTotal = [double]$os.TotalVisibleMemorySize / 1MB   # KB -> GB
  $memUsed  = $memTotal - ([double]$os.FreePhysicalMemory / 1MB)
  $mem  = if ($memTotal -gt 0) { $memUsed / $memTotal * 100 } else { 0 }
  $c    = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
  $diskTotal = [double]$c.Size / 1GB
  $diskUsed  = $diskTotal - ([double]$c.FreeSpace / 1GB)
  $disk = if ($diskTotal -gt 0) { $diskUsed / $diskTotal * 100 } else { 0 }

  $level = @(
    (Get-Level $cpu $Config.Warn $Config.Hot),
    (Get-Level $mem $Config.MemWarn $Config.MemHot),
    (Get-Level $disk $Config.DiskWarn $Config.DiskHot)
  ) | Measure-Object -Maximum

  $icons = @('🟢', '🟠', '🔴')
  $brief = "{0}{1} C{2} M{3}" -f $icons[[int]$level.Maximum], $Config.Name, [Math]::Round($cpu), [Math]::Round($mem)
  $detail = "{0}  CPU {1}%  ·  内存 {2}% ({3:N1}/{4:N1} GB)  ·  磁盘C {5}% ({6:N0}/{7:N0} GB)" -f `
    $Config.Name, [Math]::Round($cpu), [Math]::Round($mem), $memUsed, $memTotal, [Math]::Round($disk), $diskUsed, $diskTotal
  @{ brief = $brief; detail = $detail } | ConvertTo-Json -Compress
}

# 5.1 默认按系统代码页写 stdout，emoji/中文会乱码，强制 UTF-8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$mutex = New-Object Threading.Mutex($false, 'Local\yasb-load-local')
try { [void]$mutex.WaitOne(15000) } catch [Threading.AbandonedMutexException] { }   # 上一个持锁进程被杀也照常往下走
try {
  $fi = Get-Item $CacheFile -ErrorAction SilentlyContinue
  if ($fi -and ((Get-Date) - $fi.LastWriteTime).TotalSeconds -lt $Config.CacheTtlSec) {
    [IO.File]::ReadAllText($CacheFile, [Text.Encoding]::UTF8)
  } else {
    $json = Get-LocalJson
    New-Item -ItemType Directory -Force -Path (Split-Path $CacheFile) | Out-Null
    [IO.File]::WriteAllText($CacheFile, $json, (New-Object Text.UTF8Encoding $false))
    $json
  }
} finally { try { $mutex.ReleaseMutex() } catch { } }
