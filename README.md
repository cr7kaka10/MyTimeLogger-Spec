# MyTimeLogger

MyTimeLogger 是一套把时间记录、学习计划、任务习惯、运动饮食、睡眠分析和金币奖励放在一起的个人管理软件。Windows 桌面端与 Android 端共用业务逻辑，通过自己的服务端同步数据。

本文按 **2026-09-13（北京时间，UTC+8）仓库现有代码**编写。历史提案描述的是设计意图，可能尚未实施；与本文核对的实现不一致时，以实际运行版本为准。历史评分读取对应版本的结算快照，不会因为文档更新而自动改分。

## 目录

- [1. 先选使用方式](#choose)
- [2. 软件能做什么](#features)
- [3. 本地使用：Windows 从零启动](#local)
- [4. 首次登录和第一条记录](#first-use)
- [5. Android 安装和连接](#android)
- [6. 服务端部署使用](#server)
- [7. 日常功能使用说明](#usage)
- [8. 可选外部服务配置](#integrations)
- [9. 数据保存、备份与恢复](#backup)
- [10. 常见问题](#faq)
- [11. 项目结构与开发检查](#development)

<a id="choose"></a>

## 1. 先选使用方式

| 你的情况 | 按哪条路线操作 | 需要准备什么 |
| --- | --- | --- |
| 只想在自己的 Windows 电脑上使用 | 从第 3 节开始 | 源码、Python、Node.js；服务端和桌面端都在本机运行 |
| 电脑和手机都要用，电脑可一直开机 | 先完成第 3、4 节，再看第 5 节 | 上述环境，加 Android APK；手机能访问电脑 |
| 希望电脑关机后手机仍能同步、分析 | 从第 6 节部署独立服务端 | 一台常开服务器，再安装 Windows EXE 或 Android APK |
| 已有人提供服务地址和安装包 | 直接看第 4 节和第 7 节 | EXE/APK、服务地址、自己的账号；不必安装开发环境 |

**本地使用也需要首次连接 MyTimeLogger 服务端完成注册、登录和初始化。**已登录设备的一部分操作会先写入本地 SQLite，网络恢复后再同步；注册、跨设备同步、服务端结算、AI 分析和外部服务操作仍需要服务端可达。

### 三个容易混淆的入口

| 地址 / 程序 | 用途 |
| --- | --- |
| MyTimeLogger Windows EXE / Electron、Android APK | 正式客户端，日常计时、记录和管理都在这里操作 |
| `http://127.0.0.1:5173` | Vite 开发资源服务，供开发态 Electron 加载界面；普通浏览器没有受支持的本地数据库适配，不能当完整客户端使用 |
| `http://127.0.0.1:8000` | FastAPI 服务端；`/ping` 检查存活，`/docs` 看 API，`/login` 登录服务端网页，`/config` 配置个人集成 |

独立部署服务端不会自动发布一套完整浏览器版客户端。正式 EXE/APK 自带前端资源，连接远程服务时也不需要服务器运行 Vite 或 Electron。

<a id="features"></a>

## 2. 软件能做什么

底部导航当前为 **计时、时间书、学习、清单、运动、睡眠、设置**。顶部快捷按钮提供时间目标、背包、奖励商店、管理方案和金币流水入口。

| 功能 | 当前能力 | 外部服务依赖 |
| --- | --- | --- |
| 计时 | 分类正计时、输入/输出专注流程、备注、会话小结、状态切换 | 基础记录不需要外部账号；aTimeLogger 备份可选 |
| 时间书 | 按日期查看时间线、补录/编辑会话、日记、闪念卡片 | AI 整理、润色等增强能力需要个人模型配置 |
| 学习 | 目标 Objective → 关键结果 KR → 最小执行任务；JSON 导入、AI 辅助规划、加入清单 | 手工管理可用；AI 和滴答联动分别需要对应配置 |
| 清单 | 日期视图中的任务和习惯、完成状态、任务专注、来源奖励 | 滴答清单 / TickTick 的读取和写回需要个人绑定 |
| 运动 | 按方案版本查看七日计划、训练打卡、饮食状态、体重/体脂记录、评分 | MyTimeLogger 服务端；不依赖 TickTick |
| 睡眠 | 图片上传、睡眠分析、完整分析、评分、日记及历史报告 | 图片识别和报告需要个人视觉/文本模型配置 |
| 目标与奖励 | 时间目标、金币账本、奖励购买、背包物品及来源奖励 | 服务端负责对应结算和同步 |
| 管理方案 | 方案查看、预览、应用、历史版本和相关导入导出 | AI 生成需要模型配置；应用前按界面预览影响 |
| 多端同步 | 同一服务端、同一账号的客户端数据同步；离线待发送队列 | MyTimeLogger 服务端 |
| Android 小组件 | 手机桌面上查看和控制普通分类计时、刷新状态 | 先在 App 登录初始化；输入/输出回 App 操作 |

**先跑通基础计时，再按需配置外部服务。**未绑定滴答、aTimeLogger、AI 或 S3，不应阻止你验证登录与普通时间记录。

<a id="local"></a>

## 3. 本地使用：Windows 从零启动

以下命令均在 **Windows PowerShell** 执行。除非明确说明另开窗口，工作目录都是项目根目录，即能看到本 README、`server`、`ui`、`desktop` 的目录。逐步执行；某一步报错时先看第 10 节，不要继续粘贴后面的步骤。

### 3.1 安装工具

| 工具 | 本文使用的版本要求 | 安装时注意 |
| --- | --- | --- |
| [Git for Windows](https://git-scm.com/install/windows) | 可正常执行 `git` | 下载 x64 Setup；已有完整源码 ZIP 时可不使用 Git，更新时推荐 Git |
| [Python Windows 下载](https://www.python.org/downloads/windows/) | 优先使用 3.12.x | 使用安装器，勿选嵌入式包；勾选添加到 PATH。项目使用系统 `python` / `pip`，不使用 Conda |
| [Node.js + npm](https://nodejs.org/en/download) | **Node.js 22 或更高的兼容版本** | 选择 Windows x64 安装器，自带 npm；当前 Capacitor CLI 8.4.1 声明 Node.js `>=22`，不要只满足旧启动脚本的 Node 20 检查 |
| [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/) | 仅原生模块需要从源码编译时安装 | 在下载页找到 Build Tools，选择“使用 C++ 的桌面开发”，包含 MSVC 和 Windows SDK |

从工具官方网站获取安装程序。安装完重新打开 PowerShell，逐条检查：

```powershell
git --version
python --version
python -m pip --version
node --version
npm.cmd --version
```

只在 PC 使用时，不需要 Docker、Android Studio、JDK 或 Android 模拟器。

### 3.2 下载项目

下面以 `D:\WorkSpace\MyTimeLogger-Spec` 为例；可以改成自己的目录。已有源码就直接进入已有目录，不要覆盖或重新克隆到同一个非空目录。

```powershell
New-Item -ItemType Directory -Force -Path D:\WorkSpace
Set-Location D:\WorkSpace
git clone --branch dev https://github.com/cr7kaka10/MyTimeLogger-Spec.git
Set-Location D:\WorkSpace\MyTimeLogger-Spec
```

如果仓库需要权限，用你有权限的 Git 账号登录；不要把密码或访问令牌写进命令、README 或截图。也可下载有权限访问的源码 ZIP，解压后进入实际含有 `server`、`ui`、`desktop` 的目录。

本文核对的是 `dev` 分支，因此示例显式克隆 `dev`。使用其他分支、旧 tag 或旧安装包时，功能和菜单可能不同；多端使用尽量采用同一批已验证源码构建的客户端和服务端。

### 3.3 首次安装依赖

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-dev.ps1
```

这个脚本会检查 Python 和 Node.js，安装服务端 Python 依赖，以及 `core`、`ui`、`desktop` 三套 npm 依赖，并检查、按需重建 Electron 使用的 `better-sqlite3` 原生模块。首次需要下载较多文件。

**成功标志：**最后出现 `[bootstrap] All required dependencies are ready.`。只看到 `node_modules` 文件夹不代表安装完整。

若需要分开定位失败步骤，可在根目录逐条执行：

```powershell
python -m pip install -r .\requirements.txt
npm.cmd --prefix core ci
npm.cmd --prefix ui ci
npm.cmd --prefix desktop ci
npm.cmd --prefix desktop run rebuild:native
npm.cmd --prefix desktop run check:native
```

服务端依赖的正式入口是根目录 `requirements.txt`，它引用 `server/requirements.txt`；不要照历史 Python 桌面界面的文档安装另一套依赖。

### 3.4 启动服务端：PowerShell 窗口 A

```powershell
Set-Location D:\WorkSpace\MyTimeLogger-Spec
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000
```

窗口会持续输出日志，保持打开。看到 Uvicorn 在 `127.0.0.1:8000` 监听且没有异常退出，继续下一步。

在**另一个 PowerShell 窗口**检查：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/ping -TimeoutSec 10
```

正常会返回 JSON 信息，而不是连接失败。也可在浏览器访问服务端的 `/docs` 查看 API 文档。首次启动会创建数据库与默认运行配置，不需要安装 MySQL/PostgreSQL，也不需要手工建表。

如果后面要让手机经局域网访问，先在窗口 A 按 `Ctrl+C` 停止，再改成：

```powershell
python -m uvicorn server.server:app --host 0.0.0.0 --port 8000
```

`0.0.0.0` 是监听范围，**不能填到客户端服务地址里**。电脑本机仍填 `127.0.0.1`，手机填电脑的局域网 IP。

### 3.5 启动前端资源服务：PowerShell 窗口 B

```powershell
Set-Location D:\WorkSpace\MyTimeLogger-Spec
npm.cmd --prefix ui run dev
```

**成功标志：**显示 `http://127.0.0.1:5173/`，并保持运行。如果 Vite 自动换到 5174，说明 5173 已占用；先确认占用来源，不能继续假定 Electron 会加载 5174。

### 3.6 启动桌面客户端：PowerShell 窗口 C

```powershell
Set-Location D:\WorkSpace\MyTimeLogger-Spec
$env:MTL_DEV_SERVER_URL = 'http://127.0.0.1:5173'
$env:MTL_LOAD_DEV_SERVER = '1'
npm.cmd --prefix desktop start
```

**成功标志：**出现 MyTimeLogger 桌面窗口和登录页。接着完成第 4 节。

三个进程的关系：A 提供账号和业务服务，B 提供开发界面资源，C 是真正的桌面客户端。不要把打开 5173 的浏览器页面当成 C。

### 3.7 下次启动与退出

- 下次使用重复 3.4、3.5、3.6 即可，不必每次重装依赖；更新源码后再运行一次依赖检查。
- 桌面窗口的关闭按钮会隐藏到系统托盘。完全退出时，右键 MyTimeLogger 托盘图标 → **退出应用**。
- 本地服务端和 Vite 在各自窗口按 `Ctrl+C` 停止。不要按进程名批量终止 `node`、`electron` 或 IDE。
- 若想不再依赖 Vite，按第 6.6 节打包 EXE；本机作为服务端时，Python 服务仍需运行。

### 3.8 `start-all.bat` 适合什么情况

根目录的一键启动是 **Server + Vite + PC + Android 模拟器的完整开发入口**：

```powershell
.\start-all.bat
```

它会先安装/检查依赖，再检查 Android 条件。当前脚本固定使用 AVD 名称 `aTimeLogger_Extraction_API35` 和 `emulator-5554`；需要事先在 Android Studio 创建匹配的 AVD，并具备 JDK/SDK。没有 Android 环境时可能在 PC 启动前就停止，因此首次只用 PC 请走前面的三个窗口步骤。

日志位于 `tests/runtime/startup-logs/`，Android 摘要为 `android-*.summary.json`。只有最终各端 ready 才表示完整启动成功；脚本可能重启它识别出的本项目实例，不应在正在进行的重要计时中途反复运行。

<a id="first-use"></a>

## 4. 首次登录和第一条记录

### 4.1 注册或登录

1. 打开正式桌面客户端或 Android App。
2. 在服务端地址栏填写**完整服务根地址**，例如 `http://127.0.0.1:8000`。不要加 `/docs`、`/api` 或 `/config`。
3. 新服务器没有默认账号密码。切换到 **注册**，填写自己的用户名、密码，点击 **注册并登录**。
4. 已有账号时选择 **登录**。同一个人使用多台设备，应连接同一服务端并登录同一账号，不要在手机另注册一个账号。
5. 等待初始数据加载完成，看到分类网格和底部导航后再开始操作。

**服务管理者应首先注册：**当前代码把首个注册的默认用户视为服务管理者，具有服务级配置和全库备份操作权限。部署者应在把服务器交给其他用户前完成自己的注册。

登录会保持；设置中可以手动退出。更换服务器前先确认当前记录已同步，再退出并在登录页填写新地址。仅修改服务地址不会把旧服务器的全部数据搬到新服务器。

### 4.2 用一条普通计时验证安装

1. 进入 **计时**。
2. 选择一个普通分类，例如“娱乐”（以当前分类网格为准）；第一次验证先不选“输入”“输出”。
3. 确认顶部开始正计时，等待十几秒。
4. 点击顶部红色 **停止** 按钮；如果出现小结/确认面板，按提示保存。
5. 进入 **时间书**，选择今天，查看时间线是否出现刚才的分类、起止时间和时长。
6. 回到计时页，观察同步状态。第二台设备登录同一账号后，在同一天的时间书中查看记录。

本机能看到记录说明本地记录链路可用；第二台设备也能看到，才说明跨设备同步链路已跑通。

<a id="android"></a>

## 5. Android 安装和连接

### 5.1 已有 APK

1. 将可信来源的 MyTimeLogger APK 传到手机。
2. 在手机文件管理器中点击安装；如系统询问安装来源权限，只为当前安装工具按需开启。
3. 打开 App，按下面的地址表填写服务端，再注册或登录。
4. 允许需要使用的通知等权限。App 界面资源已包含在 APK 内，不依赖电脑的 5173 端口。

当前工程最低 `minSdkVersion=24`（Android 7.0）。仓库提供的简易构建流程输出 **Debug APK**，由调试签名签署，适合自用/测试；它不是应用商店正式签名发布流程。

### 5.2 自己构建 APK

先完成第 3.2、3.3 节，再安装 [Android Studio](https://developer.android.com/studio)。在 SDK Manager 安装 **Android SDK Platform 36、对应 Build-Tools、Platform-Tools**；需要模拟器时另装 Emulator 和系统镜像。准备 **JDK 21**，将 `JAVA_HOME` 指向 JDK 根目录。

默认安装位置可按以下例子设置；路径不同时换成实际位置：

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
& "$env:JAVA_HOME\bin\java.exe" -version
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\build-android.ps1
```

确认 `java -version` 显示 **21**；Android Studio 自带 JBR 的版本可能不同，脚本不会接受其他主版本。构建脚本会依次打包 Web 资源、同步 Capacitor、执行 `assembleDebug`，无需连接手机或启动模拟器。

成功产物：`deploy/artifacts/MyTimeLogger-debug.apk`。代码更新后重新构建并覆盖安装；不要用卸载/清除 App 数据作为常规更新步骤。

### 5.3 手机到底填哪个地址

| 场景 | 客户端服务端地址 |
| --- | --- |
| Windows 本机连接本机服务 | `http://127.0.0.1:8000` |
| 真机与电脑在同一局域网 | `http://电脑局域网IPv4:8000`，例如 `http://192.168.1.100:8000` |
| Android Studio 标准模拟器访问宿主电脑 | `http://10.0.2.2:8000` |
| 通过 ADB reverse 映射到宿主机 | `http://127.0.0.1:8000`，仅映射有效期间可用 |
| 独立服务器 | 部署者提供的地址，例如 `https://mtl.example.com` 或测试用 `http://服务器IP:8000` |

**手机里的 `127.0.0.1` 是手机自己。**没有 ADB 映射时，它不会指向你的电脑。

在电脑上查看局域网地址：

```powershell
Get-NetIPConfiguration
```

选择正在联网的 Wi-Fi/以太网适配器 IPv4，不要选回环、VPN 或不使用的虚拟网卡。真机连接时，服务端需按 3.4 节监听 `0.0.0.0`，手机与电脑网络可互通，并在 Windows 防火墙中允许该服务的 TCP 8000 入站访问；不要直接关闭防火墙。

先用手机浏览器访问 `http://电脑IPv4:8000/ping`。能返回 JSON 后，再到 App 登录。标准模拟器或 USB 调试还可使用：

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices
& "$env:ANDROID_HOME\platform-tools\adb.exe" -s emulator-5554 reverse tcp:8000 tcp:8000
```

将 `emulator-5554` 换成 `devices` 输出的目标设备序列号。此映射可能随重连/重启失效。

Debug 构建包含明文 HTTP 的开发配置；正式 Android 发布应使用 HTTPS 服务地址。仅改 URL 中的 `http` 为 `https` 不会自动让服务器具备证书和 TLS。

### 5.4 手机桌面小组件

先打开 App、登录并完成初始化，再长按手机桌面 → 小组件 → MyTimeLogger，添加计时小组件。普通分类支持开始、切换和停止；“输入”“输出”在小组件中不可操作，要回到 App。可使用刷新按钮更新显示。账号切换后先回 App 完成初始化，再使用小组件。

<a id="server"></a>

## 6. 服务端部署使用

这条路线把 FastAPI 与数据库放在常开服务器。客户端安装在个人电脑/手机；用户电脑关机不会停止服务器。

### 6.1 准备服务器

推荐优先使用仓库的 `server/docker-compose.yml`。它已包含构建、端口映射、持久化目录、重启策略和健康检查。

本文远程示例假定你已经有：

- 一台可通过 SSH 访问、可以运行 Linux 容器的服务器。
- 服务器已安装 **Docker Engine、Docker Compose 插件和 Git**，SSH 账号有执行 Docker 和写入自己主目录的权限。
- 服务器能下载源码、Python 基础镜像和 pip 依赖；本地 Windows 有 OpenSSH 客户端。
- 云安全组及服务器防火墙允许所需 SSH 端口；测试期的应用端口仅对需要使用的来源开放。

若这些条件尚未具备，先使用服务器平台提供的 Docker 环境，或按 [Docker Engine 官方安装指引](https://docs.docker.com/engine/install/)选择自己的服务器系统完成初始化。下面不假定某个 Linux 发行版，也不要求在 Windows 执行 Linux 安装命令。

**已有同名容器或旧数据时，先确认其来源并备份。**Compose 固定使用容器名 `mytimelogger-sleep-server`，不能与旧部署入口创建的同名容器同时运行。

### 6.2 检查 SSH 与 Docker

在 **Windows PowerShell** 设置本次部署参数。`example.com`、账号和端口都必须替换成实际值：

```powershell
$mtlServerHost = 'example.com'
$mtlSshUser = 'deploy-user'
$mtlSshPort = 22
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker version"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose version"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "git --version"
```

首次连接时核对服务器主机指纹，然后按提示使用 SSH 密钥或密码。`docker version` 必须显示服务端信息；仅安装了 Docker 客户端不够。

### 6.3 在服务器取源码、构建和启动

以下每条命令仍从 Windows PowerShell 发出；引号里的 Git/Docker 命令在远端执行。源码放在 SSH 账号主目录下的 `MyTimeLogger-Spec`。

```powershell
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "git clone --branch dev https://github.com/cr7kaka10/MyTimeLogger-Spec.git MyTimeLogger-Spec"
```

已克隆过则跳过。私有仓库需要服务器自己的读取权限；不要把 Git 令牌写进命令。

准备 Compose 环境文件。**从本地项目根目录执行**，并仅在新部署时创建：

```powershell
Copy-Item .\server\.env.example .\server\.env
notepad.exe .\server\.env
```

保存为：

```dotenv
MYTIMELOGGER_ENVIRONMENT=production
SLEEP_SERVER_PORT=8000
```

`.env` 只放这些运行参数，不放用户密码、TickTick Token、AI Key 或 S3 密钥；它应保持在 Git 之外。已有环境文件不要直接覆盖。

上传后启动：

```powershell
scp -P $mtlSshPort .\server\.env "${mtlSshUser}@${mtlServerHost}:MyTimeLogger-Spec/server/.env"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml up -d --build"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml ps"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml logs --tail 80"
```

首轮构建需要等待基础镜像和依赖下载。**成功标志：**容器持续运行并通过健康检查，日志没有启动异常。

从 Windows 检查实际网络可达性：

```powershell
Invoke-RestMethod -Uri "http://${mtlServerHost}:8000/ping" -TimeoutSec 10
```

若配置了其他 `SLEEP_SERVER_PORT`，将此处与客户端地址里的 `8000` 一起替换。容器内部仍监听 8000。

有 Docker Desktop 的 Windows 电脑也能先在本机验证同一 Compose：在项目根目录执行 `docker compose -f .\server\docker-compose.yml up -d --build`，然后访问本机 `/ping`。不要同时运行占用同一 8000 端口的 Python 服务。

### 6.4 注册服务管理者，再交付给用户

1. 确认 `/ping` 可达。
2. 部署者先访问 `http://服务器地址:8000/login`，或使用正式客户端，注册第一个账号。
3. 用这个账号完成必要的个人模型和服务备份配置；不使用这些能力时可稍后配置。
4. 将服务根地址、同版本 EXE/APK 交给其他用户。
5. 其他人各自注册 MyTimeLogger 账号；同一个人的 PC 和手机用同一账号。
6. 按第 4.2 节验证 PC 写记录、手机回读。

### 6.5 域名、HTTPS 与网络

Compose 默认直接发布宿主机 8000 端口，**没有自动安装反向代理或 HTTPS 证书**。公网长期使用时，应在服务器平台的反向代理/网关中：

1. 将自己的域名解析到服务器。
2. 为该域名启用可信 HTTPS 证书。
3. 将整个域名根路径代理到 FastAPI 的 8000 端口，保留路径、鉴权头和查询参数。
4. 允许流式/SSE 响应，关闭这类响应的代理缓冲，并为较长的分析请求设置合理等待时间。
5. 从实际客户端验证登录、`/ping`、同步和图片上传，再限制外部对 8000 的直接访问。

客户端填写如 `https://mtl.example.com`。当前设置页打开“我的服务配置”时，会给未显式带端口的地址补上 `8000`；如果走默认 HTTPS 443，出现打不开配置页时，直接在浏览器访问 `https://mtl.example.com/config`，不要为了这个按钮额外公开 8000。

### 6.6 构建 Windows EXE 并分发

在 Windows 项目根目录完成依赖安装后执行：

```powershell
npm.cmd --prefix ui run build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\check-wincodesign.ps1
npm.cmd --prefix desktop run dist
```

成功产物：`desktop/dist/MyTimeLogger-1.0.0-portable.exe`（版本号以 `desktop/package.json` 为准）。把 EXE 交给 Windows x64 用户，用户打开后填写服务地址即可；用户不需要安装 Node.js、Python 或 Docker。

打包若提示 winCodeSign 符号链接权限，按诊断开启 Windows 开发者模式并重新打开终端，或在有相应权限的终端操作。打包产物不包含你的服务端数据库和个人外部账号配置。

仓库也有 `deploy/build-desktop.ps1`，但它目前加载 `deploy/config.ps1`，直接调用会要求部署目标环境变量。只构建客户端时可使用上面的 npm 命令，避免为打包 EXE 填写无关 SSH 参数。

### 6.7 更新、重启与停止

更新前先按第 9 节备份。确认远端源码没有未提交修改、使用的分支正确后：

```powershell
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "git -C MyTimeLogger-Spec status --short"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "git -C MyTimeLogger-Spec pull --ff-only"
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml up -d --build"
```

如 `pull --ff-only` 失败，先处理分支或本地修改，不要直接强制重置。更新后重新检查容器、`/ping`、登录和一条记录的同步；有客户端变更时同步重打 EXE/APK。

日常运维命令：

```powershell
# 重启现有容器，不重建镜像
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml restart"
# 临时停止，数据目录保留
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml stop"
# 再启动已有容器
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker compose -f MyTimeLogger-Spec/server/docker-compose.yml start"
```

Compose 配置了 `unless-stopped`：Docker 服务随宿主机启动时可恢复未被手工停止的容器。`restart` 不会把新源码构建进镜像；升级要用 `up -d --build`。

### 6.8 现有部署脚本的适用边界

`deploy/deploy-test.bat` / `deploy/deploy-all.ps1` 提供交互菜单；`deploy/config.example.env` 是 SSH 目标模板，字段为 `MTL_SERVER_HOST`、`MTL_SERVER_PORT`（SSH 端口）、`MTL_SERVER_USER`、`MTL_REMOTE_DIR`、`MTL_APP_PORT`（业务端口）。这与 Compose 的 `server/.env` 是两套入口，不能混填。

当前 `deploy/deploy-server.ps1` 使用本机构建、导出、上传的路径，内部仍调用 `gzip` 并通过 PowerShell 管道传递镜像二进制。标准 Windows PowerShell 不一定具备所需工具与二进制管道条件，因此本文的新用户主路线使用远端 Compose 构建。不要在失败后把脚本最后的“部署完成”字样当作网络可达证明，应检查 `/ping` 和容器日志。

<a id="usage"></a>

## 7. 日常功能使用说明

### 7.1 计时、专注和分类

1. 打开 **计时**，点击分类开始；普通分类显示累计时间。
2. 点击另一个分类可以切换当前活动。需要说明时点击顶部分类/备注区域填写计时备注。
3. “输入”“输出”使用结构化专注流程，可能依次进入专注、短休息、长休息和小结；按当时出现的面板完成确认。
4. 点击红色停止按钮结束；需要小结时保存小结后，再到时间书确认记录。
5. **设置 → 分类管理**可管理分类；设置页也可调整专注/休息参数、声音和支持的平台快捷键。

Windows 默认 `Alt+C` 触发状态切换，`Alt+Z` 隐藏窗口；以设置中的实际快捷键和是否注册成功为准。PC 的状态切换可能弹出备注面板，可确认或稍后填写；Android 的该状态切换路径会直接切换，不弹出这张备注面板。

### 7.2 时间书：查记录、补录和日记

1. 进入 **时间书**，在日期栏选择要查看的日期。
2. 在时间线中查看已结束的记录；使用排序按钮切换先后顺序。
3. 点击记录进入编辑；漏记时点击时间线旁的 **+ 添加**，填写分类、开始/结束时间和备注，再保存。
4. Android 会话编辑的时间格式为 `YYYY-MM-DD HH:mm:ss`，例如 `2026-09-13 14:05:00`，使用 24 小时制；PC 使用原生日期时间控件。
5. 填写晨间/晚间日记；带 Markdown 的文本输入按界面提示保存，支持的输入框可用 `Ctrl+Enter`。
6. 闪念可记录想法，后续查看、修改或删除；AI 处理、分类和润色结果需要相应服务可用。

界面默认以北京时间的业务日期组织记录。跨午夜的会话、历史锁定和服务端统计应以页面返回结果为准。

### 7.3 学习：从目标拆到今天能做的一步

1. 进入 **学习** → **创建新目标 (Objective)**，填写目标标题等信息。
2. 在目标下点击 **添加关键结果 (KR)**，例如“读完前三章”。
3. 在 KR 下添加 **最小执行单元**，例如“阅读第一章并整理 3 条笔记”，选择相应时间分类。
4. 做完后点击任务前的完成控件；需要安排进当天清单时使用 **加入清单**，等待操作成功。
5. 已有规划 JSON 时，先下载页面提供的标准模板，按模板填写，再使用 **验证并导入**；不要直接导入任意格式。
6. 配置个人文本模型后，可使用目标的 AI 辅助入口生成/调整规划，再检查结果。

“加入清单”涉及滴答联动时，需要先绑定 TickTick；未配置或外部写入失败时，查看任务旁的错误/重试提示，不要连续重复创建同一任务。

### 7.4 清单：任务与习惯

1. 先按第 8.2 节绑定自己的滴答/TickTick 账号。
2. 打开 **清单**，选择日期；页面进入时会发起清单刷新，也可点击顶部 **同步待办与习惯**。
3. 等待任务、习惯和状态加载完成，再操作目标项目的完成/取消或任务专注按钮。
4. 操作后观察该项状态与同步提示；外部连接失败时保留当前数据，恢复网络后重试。
5. 需要关联金币或物品时，在项目的来源奖励入口查看/编辑，完成后到金币流水核对。

未绑定外部账号时，不能凭“登录成功”期待出现滴答数据。不要将其他人的 Token 导入自己的账号。

**两种同步的区别：**

| 同步 | 数据经过哪里 | 如何触发 |
| --- | --- | --- |
| 小同步（core） | 客户端 ↔ MyTimeLogger 服务端 | 启动、定时、恢复网络、业务变更及非清单页面的同步 |
| 清单大同步（checklist） | 客户端 ↔ 服务端 ↔ TickTick | 清单页面进入刷新、同步按钮及该页面对应操作 |

计时、睡眠或运动提示网络问题时，先检查 MyTimeLogger `/ping`；绑定 TickTick 不是修复小同步的前置步骤。

### 7.5 运动、饮食和身体记录

1. 进入 **运动**，先核对方案版本和日期；需要回到今天时点击 **今**。
2. 在 **今日数据记录**填体重（公斤）和体脂率（%），点击 **保存**。
3. 完成训练后点击对应圆形控件打卡，查看项目与总分变化。
4. V4 饮食条目有待办、完成、失败三态：左键点击待办为完成；PC 右键可标记失败；可操作的终态左键可撤销。不要把右键功能假定为手机长按。
5. 查看 **今日评分**及同步提示；“打卡已保存，等待同步”表示本地已有记录，仍需等待服务端确认。

当前 V4 的权重为运动训练 **75**、饮食约束 **15**、身体记录 **10**。北京时间 **09:00** 后补填身体数据可以保留原始值，但不补回已经失去的当日评分资格或撤销对应处罚。饮食主动标记失败记 0 分，本身不产生截止未完成的 -20 处罚；截止仍待办则按当前规则结算。

不同方案版本是整套规则与事实的边界，不只切换一个分数公式。历史锁定日、截止失败项和旧版本可能不可编辑；具体以控件状态和服务端快照为准。

### 7.6 睡眠：上传到报告

1. 按第 8.3 节配置自己的视觉模型和文本模型。
2. 进入 **睡眠**，在日历选中这次睡眠应归属的日期。
3. 点击 **上传图片**，选择睡眠统计截图，等待上传提示。
4. 点击 **睡眠分析**生成普通睡眠报告；需要完整内容时使用 **完整分析**。
5. 观察进度与错误提示，等待服务端处理完成；上传成功并不等于报告生成成功。
6. 在 **AI 分析报告**阅读结果。PC 可点击 **全屏**查看目录并跳转章节。
7. 填写当天晨间/晚间日记，查看各自的奖励状态。确认数据有误且确需重新分析时再使用 **强制分析**，这可能重新调用模型。

当前睡眠 V4 以服务端快照显示八项、总分 100；“9 点前生成睡眠报告”取**服务端成功生成报告的时间**，不是图片上传时间或客户端同步时间。普通报告成功生成也会记录该时间。

当前代码中 V4 新结算的八项全满分奖励为 **+200 金币**，旧的已结算 +100 快照保留；运动全完成奖励仍为 +100。确认无主睡眠时睡眠评分为 0，并产生对应 -200 处罚，其他独立命中的规则仍按流水核对。仅缺失有效入睡时间会保持待定，不再执行旧的“中午仍无记录 -100”规则。

这些是软件内的行为评分规则。遇到旧记录金额不同，先看日期、规则版本和流水来源，不要直接删除历史账目重新生成。

### 7.7 时间目标、金币、奖励与背包

- 顶部 **🎯 时间目标**：设置时间目标，查看完成进度。
- 顶部 **金币数值**：打开账本，查看收入、支出、来源与详情；支持页面提供的 CSV 导出。
- 顶部 **🎁 奖励商店**：配置/查看奖励，按价格购买后查看钱包与背包变化。
- 顶部 **🎒 我的背包**：查看获得的物品、碎片及可用操作。
- 顶部 **🧭 管理方案**：查看方案及历史，涉及应用/导入时先检查预览，再确认。

设置里的 **统计起始日期 / 重新拉取并重算金币**属于重建操作，会预览账本、背包等影响并要求确认短语。它不是首次运行或普通同步失败的必做步骤。

<a id="integrations"></a>

## 8. 可选外部服务配置

### 8.1 打开自己的服务配置

在客户端 **设置 → 我的服务配置**，或直接用浏览器访问 `http://服务地址:端口/config`。浏览器可能跳转到 `/login`，使用**同一服务端上的 MyTimeLogger 账号**登录；这次网页登录与 EXE/App 的登录存储分开。

配置页目前提供“我的 TickTick”“我的 S3”“我的大模型”。个人配置保存在服务端当前用户范围内；新账号不会自动继承部署者的 AI/TickTick 凭据。`server/config.json` 用于运行、CORS、日志和登录限制，不是填写个人外部密钥的地方。

### 8.2 滴答清单 / TickTick

1. 在自己的服务配置页找到滴答配置。
2. 选择与账号匹配的 Host：国内滴答使用 `dida365.com`，国际 TickTick 使用 `ticktick.com`。
3. 填入当前服务集成能够使用的个人 **Access Token**，按需设置同步间隔，点击 **保存配置**。
4. 回客户端进入清单，执行 **同步待办与习惯**，检查是否返回自己的任务和习惯。

目前配置页接收现成 Token，没有完整的“一键授权获取 Token”流程。若没有可用 Token，先向该账号/集成的维护者确认获取方式及类型；普通 MyTimeLogger 登录密码不是 TickTick Token。配置显示已保存只说明有凭据，成功同步才说明外部连接可用。

### 8.3 AI 文本与视觉模型

在 **我的大模型**分别填写：

| 配置组 | 必填项 | 用途 |
| --- | --- | --- |
| 文本模型 | Base URL、模型名、API Key | 文本分析、报告与支持的 AI 规划/处理 |
| 视觉模型 | Base URL、模型名、API Key | 睡眠截图识别等图片输入 |
| 文本/视觉备用模型 1、2 | 对应 URL、模型名、Key，按需填写 | 主模型失败时的备用配置 |

Base URL 和模型名按你实际使用的兼容模型服务填写，不要填聊天网站地址。视觉模型必须支持图片输入。可用同一家服务的 Key，但仍要填写页面要求的两个配置组。保存后用一张睡眠截图验证完整链路；仅看到“已配置”不代表模型已调用成功。

已保存的秘密字段留空通常表示保留原值，不表示清除；替换凭据时输入新值再保存。模型调用使用你配置的服务账号及其额度。

### 8.4 aTimeLogger 备份

1. 客户端进入 **设置 → 服务连接 → aTimeLogger备份**。
2. 填自己的 aTimeLogger 账号和密码，点击 **登录**。
3. 等待验证成功。后续已完成时间记录由 MyTimeLogger 服务端异步备份到该账号。
4. 出现待备份/失败计数时查看失败详情；必要时点击 **重试备份**。

MyTimeLogger 账号与 aTimeLogger 账号是两个系统的账号。未绑定不会影响普通本地计时；“MyTimeLogger 刚刚同步”也不等于 aTimeLogger 已备份完成。

### 8.5 S3 与配置导入导出

个人配置页可保存 S3 Endpoint、Bucket、Region、Access Key、Secret Key 和路径前缀；这是当前用户的配置。**服务端全库快照**读取首个注册的服务管理者的 S3 配置，状态与手动触发受管理者权限限制。普通用户保存自己的 S3 信息，不等于启用了服务端全库容灾。

管理员配置后，在配置页查看备份状态并点击 **立即备份**，以实际成功时间、对象与错误信息判断结果。TLS 证书失败应修复 Endpoint 证书链。

两种“导出”要分清：

| 入口 | 内容与用途 |
| --- | --- |
| 客户端设置的 **导出完整配置 / 导入完整配置** | 客户端偏好配置，经过导出过滤；不代替数据库备份，也不是服务配置导入格式 |
| 网页 `/config` 的 **导出配置 / 导入配置** | 个人 TickTick、S3、AI 服务配置，格式 `mytimelogger.user-service-config.v1`；**导出包含保存的服务密钥**，只用于本人安全保存和迁移 |

不要把网页服务配置导出文件发给其他用户、提交 Git 或上传到公开问题单。导入会替换当前账号对应的配置部分；导入前确认账号、服务器和文件来源正确。

<a id="backup"></a>

## 9. 数据保存、备份与恢复

### 9.1 数据在哪里

| 数据 | 当前默认位置 |
| --- | --- |
| 本机 Python 服务数据库 | `server/data/mtl_server.db` |
| Compose 服务数据库 | 宿主机源码目录的 `server/data/mtl_server.db`，映射至容器 `/app/server/data/mtl_server.db` |
| Compose 附件 / 报告 / 日志 | 宿主机 `server/attachments/`、`server/reports/`、`server/log/`，分别映射容器同类目录及 `/app/reports` |
| Windows 开发客户端账号库 | `desktop/local_data/accounts/acct-*.db`；账号隔离存储，不应只寻找旧 `my_time_logger.db` |
| Windows 打包客户端 | Electron `userData/local_data/accounts/`，通常在该用户 `%APPDATA%` 下的应用目录；不在 EXE 旁边 |
| Android | 应用私有 SQLite 和偏好/安全存储；清除 App 数据或卸载会影响本地未同步内容 |
| 开发启动日志 | `tests/runtime/startup-logs/` |
| 本地分析技能默认报告兜底 | `assets/tmp/`；可通过 `MYTIMELOGGER_REPORTS_DIR` 等实际运行配置覆盖，默认不是 Obsidian 目录 |

Compose 的四个绑定目录使数据在容器重建后仍保留。它没有自动持久化容器内部的 `server/config.json`；如果改了容器内运行配置，需要另行记录并通过受控挂载管理，不能期待重建后自动保留。

同步不是完整备份：删除和错误操作也可能同步。数据库还可能包含所有用户的业务数据和服务配置，应限制备份访问权限。

### 9.2 手工备份 Docker 服务数据库

仓库容器包含 SQLite 一致性备份脚本。Windows PowerShell 发出：

```powershell
ssh -p $mtlSshPort -l $mtlSshUser $mtlServerHost "docker exec mytimelogger-sleep-server /app/server/scripts/backup_sqlite.sh"
```

成功会输出 `sqlite backup completed:` 及容器内文件路径。默认写入 `/app/server/data/backups/app-北京时间戳.db`，对应远端源码 `server/data/backups/`；脚本会清理该目录超过 14 天的对应快照。

将本次输出中的文件名替换到下面的示例，下载到 Windows：

```powershell
New-Item -ItemType Directory -Force -Path .\backups-local
scp -P $mtlSshPort "${mtlSshUser}@${mtlServerHost}:MyTimeLogger-Spec/server/data/backups/app-2026-09-13-030000.db" .\backups-local\
```

`backups-local` 是示例自建目录，备份应另存到有访问控制的位置，不要提交。SQLite 快照不包含独立图片、报告文件；需要完整迁移时同时保存 `attachments`、`reports` 及必要的运行配置。

**本文的 Compose 启动不会安装每天 03:00 的宿主机定时任务。**部分旧部署脚本会安装该任务，不代表 Compose 也会。无人值守容灾应由管理员配置并验证 S3 自动备份，或在运维系统中按北京时间安排上述备份命令；确认实际产物和异地副本。

### 9.3 本机 Python 服务备份

在服务端窗口按 `Ctrl+C` 停止写入，确认进程退出后，复制整个数据目录；不要只在运行中复制一个 SQLite 主文件而漏掉 WAL。

```powershell
$mtlBackupStamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Force -Path .\backups-local
Copy-Item -LiteralPath .\server\data -Destination ".\backups-local\server-data-$mtlBackupStamp" -Recurse
```

附件和报告另行复制。完成后按第 3.4 节启动服务。桌面端本地缓存要备份时，也先从托盘完全退出应用，再复制该客户端整个 `local_data` 目录。

### 9.4 恢复与迁移原则

1. 确认备份所属服务器、时间点和账号范围；全库恢复会影响所有用户。
2. 保留当前数据库、WAL/SHM、附件和运行配置的一份可回退副本。
3. 将所有写入该库的服务停掉，在独立恢复目录验证备份，不覆盖正在运行的数据库。
4. S3 `.db.gz` 必须连同匹配 manifest 下载，可先在本地校验解压：

```powershell
python .\server\restore_s3_snapshot.py --snapshot .\backups-local\snapshot.db.gz --manifest .\backups-local\snapshot.db.gz.manifest.json --output .\backups-local\mtl_server.restored.db
```

5. 该工具只验证并生成新的 SQLite 文件，**不会自动替换正式库**。由部署者在停服后将验证过的文件放到正式数据路径，并处理旧库及其配套 WAL/SHM；不要把新主库与旧 WAL 混用。
6. 用与快照兼容的应用版本启动，检查 `/ping`、登录、最近记录、钱包和多端回读，再恢复日常使用。

从本地迁移到独立服务器时，可按上述原则迁移服务端库和附件；不要把 Electron 账号缓存库直接冒充服务端库。新服务器注册新账号并改 URL，也不会自动迁移原服务端的全部业务和凭据。

<a id="faq"></a>

## 10. 常见问题

| 现象 | 优先检查 / 处理 |
| --- | --- |
| `python` / `node` / `git` 找不到 | 安装对应工具、确认 PATH、重新打开终端；`python --version` 应是真正的 Python |
| `npm.ps1` 被执行策略阻止 | 使用本文的 `npm.cmd`；运行项目 PowerShell 脚本可用示例中的单次 `-ExecutionPolicy Bypass` |
| 缺少 Python 模块 | 从项目根目录执行 `python -m pip install -r .\requirements.txt`，确认启动用的是同一个 Python |
| `EBADENGINE` / Capacitor 无法执行 | 核对 Node.js 22+；旧脚本检查通过不能代替锁文件依赖要求 |
| `better-sqlite3` / `NODE_MODULE_VERSION` 错误 | 执行 `npm.cmd --prefix desktop run rebuild:native`，再执行 `check:native`；编译失败时检查 C++ Build Tools 和 SDK |
| `vite` / `electron` 不存在 | 重新运行依赖检查，或对报错子项目执行 `npm.cmd --prefix 子目录 ci`；不要从别的项目复制 `node_modules` |
| `unsafe_reparse_point` | 依赖目录是 Junction/符号链接等不安全复用路径；先确认真实目标，由目录管理者整理成正常本地依赖目录，再安装 |
| 8000 被占用 | 用下方命令查看所属 PID，确认是旧项目服务还是别的软件；在原窗口正常退出，或统一调整服务端与客户端端口 |
| Vite 启动在 5174、Electron 白屏 | Electron 默认加载 5173；解决 5173 占用或将 `MTL_DEV_SERVER_URL` 改为实际 Vite 地址 |
| 浏览器 5173 提示数据库不可用 | 使用 Electron/EXE 或 APK；当前不支持纯浏览器存储运行 |
| `start-all.bat` 卡在 Android 检查 | 只用 PC 就按第 3.4–3.6 节启动；完整入口需指定名称的 AVD、JDK/SDK |
| 注册失败“用户已存在” | 在当前服务器改为登录；不同服务器的同名账号不是同一份数据 |
| 登录 401 | 检查账号密码和服务地址；全新服务端要先注册。连续失败可能触发登录限流，默认锁定配置为 5 次/300 秒 |
| 手机无法连接 | 手机不要填无映射的 `127.0.0.1`；检查服务监听、局域网、VPN、无线客户端隔离及防火墙，先用手机浏览器访问 `/ping` |
| HTTP cleartext 错误 | Debug APK 与正式包的网络策略不同；正式发布用 HTTPS，局域网开发使用当前 Debug 构建 |
| `/ping` 正常，任务为空 | 再核对个人 TickTick 绑定、选中日期和清单同步；`/ping` 只证明服务可达 |
| 计时显示网络不可用 | 首查 FastAPI `/ping`、服务端进程和日志；不是要求先配置滴答 |
| 已配置 AI，但分析失败 | 核对当前登录用户、Base URL、模型名、Key、模型图片能力、服务端对外网络和额度；查看实际报错 |
| 设置打开服务配置的端口不对 | 默认 HTTPS 443 反代场景，手工打开正确域名的 `/config`，见第 6.5 节 |
| S3“立即备份”无权限 | 使用首个注册的服务管理者账号；个人可保存服务配置不等于拥有全库备份权限 |
| Docker 容器 running 但外部不能连 | 看 health、日志、安全组、防火墙、端口映射；用真实客户端网络验证，不只看容器 ID |
| 更新服务端后功能没变化 | 是否只执行了 `restart`？新源码需 `up -d --build`；客户端改动也需更新 EXE/APK |
| 新设备没有旧记录 | 确认同一服务器、同一账号、原设备已同步；不要先清库、卸载或重建金币 |

本机端口与日志检查：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
Get-ChildItem .\server\log -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name,LastWriteTime
Get-ChildItem .\tests\runtime\startup-logs -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 10 Name,LastWriteTime
```

反馈问题时提供客户端版本/平台、操作步骤、北京时间、错误文案和相关脱敏日志。不要附带原始数据库、登录令牌或个人服务配置导出。

<a id="development"></a>

## 11. 项目结构与开发检查

```text
MyTimeLogger-Spec/
├── README.md                 本文：用户使用和部署说明
├── requirements.txt          当前 Python 服务依赖入口
├── start-all.bat              PC + Android 完整开发启动
├── core/                     TypeScript 业务、计时、数据库与同步
├── ui/                       React 界面、Vite 和平台适配
│   └── android/              Capacitor Android 原生工程与小组件
├── desktop/                  Electron 主进程、IPC、原生 SQLite、打包配置
├── server/                   FastAPI、领域服务、个人集成和数据库
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.example
│   └── scripts/backup_sqlite.sh
├── shared/protocol/          跨端同步契约
├── scripts/                  本地启动、依赖检查与诊断
├── deploy/                   部署/EXE/APK 构建脚本
├── tests/                    服务端、脚本等测试及运行产物
```

开发者可在根目录执行以下检查；普通用户不需要先跑测试才能使用：

```powershell
npm.cmd --prefix core test
npm.cmd --prefix core run typecheck
npm.cmd --prefix ui run typecheck
npm.cmd --prefix ui run build
```

## 12. 许可证与商业授权

本项目以 [PolyForm Noncommercial License 1.0.0](LICENSE) 进行源码可见发布，不是 OSI 定义的开源软件。

非商业用途可按照 [LICENSE](LICENSE) 的条款使用、修改和分发。商业用途不由该许可授予；请先阅读 [商业授权说明](COMMERCIAL-LICENSE.md)，并通过仓库 Issue 发起咨询。请勿在公开 Issue 中提交密钥、个人资料、付款信息或合同内容。

本说明仅用于帮助理解，发生冲突时以 [LICENSE](LICENSE) 的完整条款为准。
