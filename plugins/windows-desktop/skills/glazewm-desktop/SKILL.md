---
name: glazewm-desktop
description: 在一台 Windows 电脑上一键装好/复原 GlazeWM 平铺窗口 + YASB 状态栏（顶部显示当前工作区编号 + 本机负载圆点，点开看明细）。用户说「在这台电脑上装一下平铺桌面/glazewm 环境」「新电脑配一下 GlazeWM」「状态栏看不到第几个工作区」「Alt+Shift+数字 没反应」「YASB 一直 Loading」「工作区跑错屏」时使用。只适用于 Windows；Linux/Mac 上不要用。
---

# GlazeWM + YASB 平铺桌面

来源：作者在一台「笔记本横屏在左 + 竖屏在右」的双屏环境上反复试出来的最终形态。
目标是换一台 Windows 电脑，跑一个脚本就得到同样的桌面。

## 装出来是什么样

- **GlazeWM**：9 个工作区。双屏时 1-5 固定在最左屏、6-9 在右边那块；单屏时不绑定。
  键位：`Alt+1..9` 切工作区，`Alt+Shift+1..9` 把窗口丢过去并跟过去，
  `Alt+Shift+A/F` 把整个工作区挪到左/右屏，`Alt+Shift+R` 重载配置。
- **YASB**（替代 GlazeWM 自带的 Zebar）：每块屏顶部一条细栏。
  左边是本屏的工作区编号，当前那个蓝底。
  右边是 `🟢local C12 M45`：圆点按阈值变色（CPU 60/85、内存 80/90、C 盘 85/95，绿/橙/红）。
  左键点开一行明细，再点收起；鼠标悬停也能看到。

## 怎么装

在普通权限的 PowerShell 里运行（作为 Claude Code 插件安装时用第一行；直接克隆仓库时在本目录下用第二行）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/skills/glazewm-desktop/install.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

脚本可重复跑，六步依次是：
1. winget 装 GlazeWM、YASB，已装就跳过；
2. 发现 Zebar 时问要不要卸；
3. 按屏幕数写 `~/.glzr/glazewm/config.yaml` 和 `~/.config/yasb/{config.yaml, styles.css, scripts/local-yasb.ps1}`，旧文件先备份成 `*.bak-时间戳`；
4. GlazeWM 加进 HKCU Run 开机自启；
5. 发现 Alt+Shift 冲突时问要不要改；
6. 启动或重载。

交互式的确认（y/N）要**用户自己在终端里答**。AI 代跑时标准输入是空的，所有提问都会按「否」处理，所以不会卸 Zebar、不会改快捷键。

**AI 代为检查时只用 `-RenderOnly <目录>`**，它只把生成的配置写到那个目录。
**不要**用 `powershell -Command "<检查代码>" <路径>` 这种写法做语法检查：`-Command` 会把后面的路径拼进命令里执行，结果是把 install.ps1 整个真跑一遍——实际发生过两次。
语法检查要写成独立的 .ps1，用 `-File check.ps1 -Path <文件>` 调用。

## 踩过的坑（改配置前先看）

| 现象 | 原因 | 处理 |
|---|---|---|
| `Alt+Shift+数字` 没反应 | Windows「切换输入语言」快捷键占了 Left Alt+Shift | `HKCU\Keyboard Layout\Toggle` 的 `Language Hotkey`（或 `Layout Hotkey`）为 `1` 就是冲突，改成 `3`（未分配），注销后生效。旧的 `Hotkey` 值不用管：实测它仍是 1 时照样正常。这是系统设置，AI 不代改，只给命令或让 install.ps1 在用户确认后改 |
| 装 GlazeWM 顺带装了 Zebar，每次开机弹出来 | GlazeWM 安装包捆绑 Zebar，默认配置里有 `shell-exec zebar` | 模板已改成启动 YASB。卸 Zebar 时**别用** `winget uninstall glzr-io.glazewm`：winget 把 Zebar 挂在 GlazeWM 的 ID 下，可能连 GlazeWM 一起卸掉。要按 Zebar 自己的 MSI 产品码 `msiexec /X{GUID}`，而且要管理员权限 |
| 工作区跑错屏 | `bind_to_monitor` 按物理位置从左往右数（0 = 最左），不是 Windows 的显示器编号 | 左右反了就把 0/1 互换 |
| 改了绑定，已开着的工作区还在原来那块屏 | GlazeWM 重载配置不会搬已经存在的工作区 | `Alt+数字` 切过去，再 `Alt+Shift+A/F` 挪过去，或者重启 GlazeWM |
| 工作区栏只显示一个编号 | GlazeWM 按需创建工作区，YASB 只显示已经存在的那几个 | 想常驻就给每个工作区加 `keep_alive: true` |
| YASB custom 组件显示「Windows PowerShell / Copyright…」 | YASB 用 `run_cmd.split(" ")` 硬切，不认引号，引号成了路径的一部分，PowerShell 退回交互模式 | `run_cmd` 里的路径**不能加引号、不能有空格**；用户名带空格的机器上 local 组件用不了（install.ps1 会警告） |
| YASB custom 组件永远 `Loading...` | 设了 `exec_options.encoding` 以后 Popen 返回的是 str，YASB 还要再 `.decode("utf-8")`，后台线程直接崩掉，没有任何提示 | **不要设 `encoding`**。脚本里用 `[Console]::OutputEncoding = UTF8` 输出 UTF-8 字节 |
| 中文、emoji 变乱码 | PowerShell 5.1 读没有 BOM 的脚本时按系统代码页解析 | 仓库里所有 .ps1 都存成 **UTF-8 带 BOM**。在 pwsh 7 里重新保存要用 `-Encoding utf8BOM`，7 里的 `utf8` 不带 BOM |
| `& glazewm.exe query …` 或 `command …` 报「The requested operation requires elevation」 | glazewm.exe 带 uiAccess，只能用 ShellExecute 启动；`&` 和带输出重定向的 `Start-Process` 走的都是 CreateProcess | 发命令用 `Start-Process glazewm.exe -ArgumentList 'command','…' -Wait`。要读状态就直接连 IPC `ws://localhost:6123`，发 `query monitors`、`query focused`，不需要提权 |
| 快捷键时灵时不灵，要先分清是按键没到还是命令失败 | — | ① 通过 IPC 发 `command move --workspace N` 测命令本身；② 开一个记事本，用 `keybd_event` 模拟真实按键测快捷键。两步都成功就说明 GlazeWM 没问题，问题在按键当时的条件：焦点在哪个窗口、那个窗口是不是管理员权限、按的是左边还是右边的 Alt/Shift |
| 只有 `Alt+Shift+1~4` 按不出来，模拟按键却正常 | **键盘硬件按不出这组三键组合**。实测一把折叠键盘上，左 Shift、左 Alt 和左侧数字键共用内部线路，三键同按时第三个键丢了；左 Alt + 右 Shift 正常 | 换成右 Shift，或者给同一条命令在 `bindings` 里再加一组不冲突的组合。先在那把键盘上试出哪组组合能按出来，再去改配置 |
| 两块屏上的负载数字对不上 | YASB 每块屏各有一份组件，各自定时跑取数脚本，前后差约 1 秒，拿到的是不同时刻的采样 | 已改为共享缓存：`%LOCALAPPDATA%\yasb-load-cache\` 加一个具名互斥锁，先到的那份取数并写缓存，后到的等锁后直接读。缓存有效期（local 3 秒）必须小于 `run_interval`（5 秒），否则会一直读旧数据。改间隔时两个值要一起调 |
| `yasb.log` 里有 `Windows fatal exception: code 0xc0000139`，堆栈停在 `QWebSocket()` | 被 faulthandler 打印出来的一个已处理异常 | 无害，栏正常显示就不用管 |

## 文件

- `install.ps1`：安装和复原入口，带 `-RenderOnly` 预览模式
- `assets/glazewm-config.yaml`：GlazeWM 配置模板
- `assets/yasb-config.yaml`、`assets/yasb-styles.css`：YASB 配置和样式，只含工作区和 local 两个组件
- `assets/local-yasb.ps1`：本机负载取数脚本，输出 `{brief, detail}` JSON，只读 CIM，不联网

改桌面布局：改 `assets/` 里的模板，各机重跑 install.ps1。
若现有 YASB 配置里挂了模板之外的 Beszel 组件，重跑时脚本会检测到并问要不要覆盖——想保留就答 N。
