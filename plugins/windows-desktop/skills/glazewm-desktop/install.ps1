<#
  glazewm-desktop 安装脚本：GlazeWM 平铺窗口 + YASB 状态栏（工作区编号 + 本机负载）

  用法（在目标 Windows 电脑上，普通权限的 PowerShell 里跑；装软件/卸 Zebar 时会弹 UAC）：
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -RenderOnly <目录>
      └ 只按本机（屏幕数量、安装路径）生成配置写到 <目录>，不装软件、不改任何设置，预览/排错用

  可重复运行：已装的软件跳过，已存在的配置先备份成 *.bak-时间戳 再覆盖。
  注意：本文件必须保存为「UTF-8 带 BOM」，否则 PowerShell 5.1 读中文会乱码。
#>
param([string]$RenderOnly)
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { throw '只支持 Windows。' }

$Assets   = Join-Path $PSScriptRoot 'assets'
$GlazeExe = Join-Path $env:ProgramFiles 'glzr.io\GlazeWM\glazewm.exe'
$YasbExe  = Join-Path $env:ProgramFiles 'Yasb\yasb.exe'
$GlazeCfg = Join-Path $HOME '.glzr\glazewm\config.yaml'
$YasbDir  = Join-Path $HOME '.config\yasb'

function Ask([string]$q) { (Read-Host "$q [y/N]") -match '^(y|yes)$' }
function Write-Utf8([string]$path, [string]$text) {
  New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
  [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false))
}
function Backup-File([string]$path) {
  if (Test-Path $path) {
    $bak = "$path.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item $path $bak
    Write-Host "    已备份 → $bak"
  }
}

# ───────────── 按本机生成配置 ─────────────
Add-Type -AssemblyName System.Windows.Forms
$screens = [Windows.Forms.Screen]::AllScreens.Count

$glaze = Get-Content -Raw -Encoding UTF8 (Join-Path $Assets 'glazewm-config.yaml')
# 模板里写的是 winget 的默认安装位置；ProgramFiles 被改过的机器按实际路径替换
$glaze = $glaze.Replace('C:\Program Files\Yasb\yasb.exe', $YasbExe)
if ($screens -lt 2) {
  # 单屏：绑到不存在的 monitor 1 没意义，去掉绑定让 GlazeWM 自己分配
  $glaze = (($glaze -split "`r?`n") | Where-Object { $_ -notmatch '^\s*bind_to_monitor:' }) -join "`r`n"
}
$yasbCfg = Get-Content -Raw -Encoding UTF8 (Join-Path $Assets 'yasb-config.yaml')
$yasbCss = Get-Content -Raw -Encoding UTF8 (Join-Path $Assets 'yasb-styles.css')
$localPs = Join-Path $Assets 'local-yasb.ps1'   # 直接复制，保住 BOM
$lunarPy = Join-Path $Assets 'lunar-yasb.py'

# 农历/黄历/八卦组件要 Python + lunar_python。找不到、或路径带空格（YASB 按空格切命令）就从中栏去掉它
$pythonExe = $null
foreach ($cand in @(@('py', '-3'), @('python'))) {
  try {
    $out = & $cand[0] @($cand[1..9] | Where-Object { $_ }) -c 'import sys; print(sys.executable)' 2>$null
    $exe = ($out | Select-Object -Last 1)
    if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Path $exe)) { $pythonExe = $exe; break }
  } catch { }
}
if ($pythonExe -and $pythonExe -match ' ') {
  Write-Warning "Python 路径「$pythonExe」含空格，YASB 无法调用，农历组件已跳过。"
  $pythonExe = $null
}
if ($pythonExe) {
  $yasbCfg = $yasbCfg.Replace('__PYTHON__', $pythonExe)
  # python.exe 不会像 PowerShell 那样展开 $env:USERPROFILE，脚本路径写成绝对路径
  $yasbCfg = $yasbCfg.Replace('$env:USERPROFILE\.config\yasb\scripts\lunar-yasb.py', (Join-Path $YasbDir 'scripts\lunar-yasb.py'))
} else {
  $yasbCfg = $yasbCfg.Replace('center: ["clock", "lunar"]', 'center: ["clock"]')
}

if ($RenderOnly) {
  Write-Utf8 (Join-Path $RenderOnly 'glazewm\config.yaml') $glaze
  Write-Utf8 (Join-Path $RenderOnly 'yasb\config.yaml') $yasbCfg
  Write-Utf8 (Join-Path $RenderOnly 'yasb\styles.css') $yasbCss
  New-Item -ItemType Directory -Force -Path (Join-Path $RenderOnly 'yasb\scripts') | Out-Null
  Copy-Item $localPs (Join-Path $RenderOnly 'yasb\scripts\local-yasb.ps1') -Force
  Copy-Item $lunarPy (Join-Path $RenderOnly 'yasb\scripts\lunar-yasb.py') -Force
  Write-Host "检测到 $screens 块屏幕；配置已生成到 $RenderOnly（未安装软件、未改动系统）。"
  return
}

if ($HOME -match ' ') {
  Write-Warning "用户目录「$HOME」里有空格：YASB 按空格切分命令，状态栏右侧的 local 负载会一直显示 Loading…，其余功能不受影响。"
}

# ───────────── 1. 安装软件 ─────────────
Write-Host '[1/6] 安装 GlazeWM / YASB'
foreach ($p in @(@{ Id = 'glzr-io.glazewm'; Exe = $GlazeExe }, @{ Id = 'AmN.yasb'; Exe = $YasbExe })) {
  if (Test-Path $p.Exe) { Write-Host "    已安装：$($p.Id)"; continue }
  winget install --id $p.Id -e --accept-source-agreements --accept-package-agreements
  if (-not (Test-Path $p.Exe)) { throw "$($p.Id) 装完仍找不到 $($p.Exe)" }
}

# ───────────── 2. Zebar（GlazeWM 安装包会顺带装上，本方案用 YASB 代替）─────────────
Write-Host '[2/6] 检查 Zebar'
$zebar = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -eq 'Zebar' } | Select-Object -First 1
if (-not $zebar) {
  Write-Host '    未安装，跳过'
} elseif (Ask '    检测到 Zebar，本方案用 YASB 代替它。卸载 Zebar？（会弹 UAC）') {
  Get-Process zebar -ErrorAction SilentlyContinue | Stop-Process -Force
  # 注意别用 winget uninstall：它把 Zebar 挂在 glzr-io.glazewm 这个 ID 下，按 ID 卸可能把 GlazeWM 一起卸掉
  Start-Process msiexec.exe -ArgumentList "/X$($zebar.PSChildName) /quiet /norestart" -Verb RunAs -Wait
  Write-Host "    Zebar 已卸载：$(-not (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$($zebar.PSChildName)"))"
}

# ───────────── 3. 写配置 ─────────────
Write-Host "[3/6] 写配置（检测到 $screens 块屏幕$(if ($screens -lt 2) { '，已去掉 bind_to_monitor' })）"
$yasbCfgPath = Join-Path $YasbDir 'config.yaml'
$writeYasb = $true
if ((Test-Path $yasbCfgPath) -and ((Get-Content -Raw $yasbCfgPath) -match 'beszel')) {
  # 模板里没有 Beszel（多机负载监控）组件；现有配置若自己加过，直接覆盖就没了，所以先问
  $writeYasb = Ask '    现有 YASB 配置里有 Beszel 组件，覆盖后会丢掉它（已备份）。仍然覆盖？'
}
Backup-File $GlazeCfg
Write-Utf8 $GlazeCfg $glaze
Write-Host "    $GlazeCfg"
if ($writeYasb) {
  Backup-File $yasbCfgPath
  Backup-File (Join-Path $YasbDir 'styles.css')
  Write-Utf8 $yasbCfgPath $yasbCfg
  Write-Utf8 (Join-Path $YasbDir 'styles.css') $yasbCss
  New-Item -ItemType Directory -Force -Path (Join-Path $YasbDir 'scripts') | Out-Null
  Copy-Item $localPs (Join-Path $YasbDir 'scripts\local-yasb.ps1') -Force
  Copy-Item $lunarPy (Join-Path $YasbDir 'scripts\lunar-yasb.py') -Force
  Write-Host "    $YasbDir\{config.yaml, styles.css, scripts\local-yasb.ps1, scripts\lunar-yasb.py}"
  if ($pythonExe) {
    & $pythonExe -c 'import lunar_python' 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host '    安装 lunar_python（农历组件依赖）'
      & $pythonExe -m pip install --user -q lunar_python
      if ($LASTEXITCODE -ne 0) { Write-Warning 'lunar_python 安装失败，农历组件会一直显示 农历 …；手动跑：pip install lunar_python' }
    }
  } else {
    Write-Host '    未找到可用 Python，农历/黄历/八卦组件已跳过（装 Python 后重跑本脚本即可）'
  }
} else {
  Write-Host '    保留现有 YASB 配置'
}

# ───────────── 4. GlazeWM 开机自启 ─────────────
Write-Host '[4/6] GlazeWM 开机自启'
$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if ((Get-ItemProperty $run -ErrorAction SilentlyContinue).GlazeWM -ne $GlazeExe) {
  Set-ItemProperty -Path $run -Name 'GlazeWM' -Value $GlazeExe
  Write-Host '    已加入（当前用户登录时启动；YASB 由 GlazeWM 的 startup_commands 带起）'
} else { Write-Host '    已存在' }

# ───────────── 5. Alt+Shift 冲突 ─────────────
Write-Host '[5/6] 检查 Alt+Shift 输入法快捷键'
$tog = 'HKCU:\Keyboard Layout\Toggle'
$t = Get-ItemProperty $tog -ErrorAction SilentlyContinue
# 取值：1 = Left Alt+Shift，2 = Ctrl+Shift，3 = 未分配。
# 不看旧的 'Hotkey' 值：实测它仍是 1 时，只要 Language Hotkey=3，Alt+Shift+数字 就已正常
$conflict = @('Language Hotkey', 'Layout Hotkey') | Where-Object { $t.$_ -eq '1' }
$needLogoff = $false
if (-not $conflict) {
  Write-Host '    没有冲突'
} else {
  Write-Host "    Windows 把 Left Alt+Shift 设成了切换输入法（$($conflict -join ', ')），会吃掉 GlazeWM 的 Alt+Shift+数字 等快捷键。"
  if (Ask '    改成「未分配」？（需要注销重新登录才生效；也可以不改，之后自己去「高级键盘设置 → 输入语言热键」里改）') {
    foreach ($k in $conflict) { Set-ItemProperty -Path $tog -Name $k -Value '3' }
    $needLogoff = $true
    Write-Host '    已改'
  }
}

# ───────────── 6. 启动 / 重新加载 ─────────────
Write-Host '[6/6] 启动'
if (Get-Process glazewm -ErrorAction SilentlyContinue) {
  # glazewm.exe 带 uiAccess：用 & 直接调（CreateProcess）会报「需要提权」，Start-Process 走 ShellExecute 才行
  Start-Process $GlazeExe -ArgumentList 'command', 'wm-reload-config' -WindowStyle Hidden -Wait
  # startup_commands 只在 GlazeWM 启动时跑一次，reload 不会拉起 YASB，这里手动重启它
  Get-Process yasb -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 1
  Start-Process $YasbExe
  Write-Host '    GlazeWM 已重新加载配置，YASB 已重启'
} else {
  Start-Process $GlazeExe
  Write-Host '    GlazeWM 已启动（它会带起 YASB）'
}

Write-Host ''
Write-Host '完成。'
if ($needLogoff) { Write-Host '  ⚠ 输入法快捷键改动要注销重新登录后才生效。' }
if ($screens -ge 2) {
  Write-Host '  · 工作区 1-5 固定在最左屏，6-9 在右边那块（按物理位置从左往右数）。左右反了就把配置里的 bind_to_monitor 0/1 互换。'
  Write-Host '  · 已经打开过的工作区不会因为重载配置而换屏：Alt+数字 切过去，再 Alt+Shift+A/F 挪到左/右屏，或重启 GlazeWM。'
}
