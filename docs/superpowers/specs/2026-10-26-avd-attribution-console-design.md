# AVD 归因测试控制台 — 设计文档

- 日期：2026-10-26
- 状态：待确认
- 关联：同目录下的 `avd_rounds.py`、`cdp_click.mjs`（只读，不改动）

## 1. 意图

把已经验证过的单机脚本 `avd_rounds.py` 包成一个**本地 Web 应用**：网页里配置推广 URL 和轮数，点开始，看着每一轮跑完，所有过程和结果落到 SQLite，随时回看历史。

用途是安卓归因链路的风控评估测试（验证「每次重建模拟器后是否被计为新用户」），不是生产系统，只在本机跑。

## 2. 目标

- 纯网页操作，日常使用不需要命令行
- 单 worker 串行执行，不并行（已决策）
- URL、rounds 可在页面上配置；每轮重建模拟器（`PLAN=wipe`）
- **中间数据尽量保存**：每一行 stdout/stderr、解析出的每轮事件、每轮 CSV 字段、模拟器启动日志、APK 元数据、运行配置快照
- 原脚本 `avd_rounds.py` 与 `cdp_click.mjs` 一行不改，只通过环境变量和子进程驱动
- 本地单文件 SQLite，无外部服务

## 3. 非目标

- 不并行、不做多 worker（用户已明确选择串行）
- 不做登录、多用户、权限
- 不改手机型号（已选方案 A：接受 `ro.product.model` 不变；B 方案另见 `docs/model-variation-buildprop.md`）
- 不做云端部署、不做移动端适配
- 不修改原脚本，也不做「只改两个常量」的副本（并行方案已放弃）

## 4. 反目标（技术上能做，但算失败）

- 需要改动 `avd_rounds.py` / `cdp_click.mjs` 才能运行的方案
- 包装层改变了测试行为：额外清目录、改轮次判定、改安装方式、缩短/延长脚本里的等待
- 页面关掉或刷新导致正在跑的任务中断（任务必须独立于浏览器存活）
- 为了好看而隐藏原始数据（日志必须原样可查）

## 5. 已定决策

| 项 | 决策 | 说明 |
|---|---|---|
| 技术栈 | Python + FastAPI + uvicorn | 和脚本同语言；本机部署简单 |
| 存储 | SQLite（stdlib `sqlite3`） | 单文件 `data/app.db` |
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 | 页面质量优先；构建产物由 FastAPI 托管，运行时不依赖 Node |
| 实时刷新 | 前端每 2 秒轮询 | 不引入 SSE/WebSocket 依赖 |
| 执行方式 | 后端线程 + `subprocess.Popen` 调原脚本 | 脚本不改 |
| 轮次粒度 | **每轮单独调用一次脚本**（`ROUNDS=1`） | 脚本只在进程结束时写 CSV；逐轮调用让每轮结果立即落库，单轮失败不影响后续 |
| 并发 | 同一时间只允许一个 run | 串行；再次提交进入内存队列 |
| 脚本路径 | 配置项，默认同级 `avd_rounds.py` | 只读使用 |
| SDK 路径 | 配置项，默认 `/Users/yantaowang/Library/Android/sdk` | 当前 shell 的 `ANDROID_HOME` 指向失效的 Caskroom 路径，必须显式传给子进程 |
| APK 落盘 | 只记路径/大小/mtime/sha256，不复制文件 | 100 轮 × 81MB 会把磁盘打满 |
| 取消 | 终止脚本进程组，再 `adb emu kill` 关模拟器 | 已采集数据保留 |
| 环境性失败 | **连续 3 轮**环境失败即中止 | 剩余轮次标记 `skipped`，run 置 `failed` |
| 中断续跑 | **不支持**。取消 / 服务重启即终止 | UI 必须明确提示「终止后只能新建 run」 |
| 后台核对字段 | **不在控制台记录** | 只存脚本能采到的数据；是否计入新用户等仍在控制台外核对 |

### 每轮调用与模拟器生命周期

每轮流程：

1. 后端确保模拟器在线（`adb devices` 里有 `SERIAL`）；不在线则自己启动 AVD 并等待 `sys.boot_completed=1`
2. 以 `ROUNDS=1`、`PLAN=wipe`、`OUT=<run>/round_N.csv` 启动脚本
3. 脚本内部会 `adb emu kill` 并带 `-wipe-data` 重新拉起模拟器，然后跑完「浏览器→下载→安装→打开」
4. 脚本退出后，后端导入本轮 CSV，进入下一轮

脚本自身启动模拟器时不带 `-port`；单实例场景下固定落在 `emulator-5554`，与 `SERIAL` 默认值一致。这是串行方案成立的前提。

## 6. 数据模型

### runs

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| url | TEXT | 本次推广链接 |
| rounds | INTEGER | 计划轮数 |
| avd | TEXT | AVD 名 |
| serial | TEXT | 设备序列号 |
| pkg | TEXT | 包名 |
| plan | TEXT | 固定 `wipe` |
| status | TEXT | queued / running / succeeded / failed / canceled / interrupted |
| exit_code | INTEGER | 最后一个子进程退出码 |
| error | TEXT | 失败摘要 |
| sdk_root | TEXT | 传给子进程的 ANDROID_HOME |
| script_path | TEXT | 实际调用的脚本 |
| model | TEXT | 脚本启动时打印的 `model:` |
| qemu | TEXT | 脚本启动时打印的 `qemu:` |
| out_dir | TEXT | `data/runs/<id>/` |
| created_at / started_at / finished_at | TEXT | ISO 时间 |

### rounds

| 列 | 说明 |
|---|---|
| id, run_id, round_no | 唯一约束 `(run_id, round_no)` |
| action, android_id_before, android_id_after, public_ip | 来自 CSV |
| clicked_at, click_url, apk_url, install_at, open_at | 来自 CSV |
| installer, first_install, channel, app_version, status, apk_src | 来自 CSV |
| log_excerpt | 来自 CSV |
| source | `csv` 或 `stdout`（脚本崩溃没写 CSV 时用 stdout 拼出部分字段） |

平台侧的人工核对结果（是否计入新用户 / 渠道是否正确 / 异常标记）**不入库**。`rounds` 只保存脚本可采集到的字段，后台核对仍在控制台之外进行。

### round_events

`id, run_id, round_no, ts, kind, message`

解析自 stdout，kind 例如：`round_start`、`android_id`、`chrome_tap`、`setup_tap`、`app_tap`、`click_ok`、`click_fail`、`host_download_ok`、`host_download_fail`、`install_attempt`、`cold_boot`、`channel_status`、`no_page`、`no_apk`。

### log_lines

`id, run_id, seq, ts, stream(stdout/stderr), line` — 原样保存，前端按 `seq` 增量拉取。

### apk_artifacts

`id, run_id, round_no, path, size, mtime, sha256, source` — 脚本把宿主机下载的 APK 放在 `/tmp/avd_rounds/roundN.apk`，这里只记录元数据。

### emulator_log_lines

`id, run_id, seq, ts, line` — 脚本把模拟器输出追加到 `/tmp/avd_rounds/emulator_wipe.log`；每次 run 开始时记录 offset，结束时把新增部分入库。

索引：`rounds(run_id, round_no)`、`round_events(run_id, id)`、`log_lines(run_id, seq)`。

## 7. 后端行为

### 启动一个 run

1. 校验 URL、rounds（1–1000）；若已有 running 任务，则排队
2. 建 `runs` 行（queued），创建 `data/runs/<id>/`
3. worker 线程取队列，状态置 running，记录 `started_at`
4. 确保模拟器在线
5. 循环 `r = 1..rounds`：
   - 组装子进程环境变量：`URL`、`PKG`、`AVD`、`SERIAL`、`ROUNDS=1`、`PLAN=wipe`、`OUT=<out_dir>/round_<r>.csv`、`ANDROID_HOME=<sdk_root>`、`PATH=<sdk_root>/platform-tools:$PATH`
   - `Popen([sys.executable, script_path], cwd=脚本目录, stdout=PIPE, stderr=STDOUT, start_new_session=True)`
   - 逐行读取：写 `log_lines`（自增 seq），正则解析事件写 `round_events`，更新运行中的进度
   - 进程退出后：若 `round_<r>.csv` 存在则导入为 `rounds` 行（`source=csv`）；否则用本轮解析到的事件拼一条 `source=stdout` 的部分记录，状态记 `CSV_MISSING`
   - **紧接着**采集 APK 元数据（`/tmp/avd_rounds/round1.apk` 的路径、大小、mtime、sha256）。因为每轮都是 `ROUNDS=1`，这个文件名固定为 `round1.apk`，下一轮会覆盖，必须在本轮结束时立刻采集
   - 若收到取消信号：终止进程组，跳出循环
   - 若连续 3 轮命中「环境失败」，中止循环（见下）
6. 收尾：状态置 succeeded / failed / canceled；记录 `finished_at`、`exit_code`；导入模拟器日志新增部分

### stdout 解析规则

| 正则 | 事件 |
|---|---|
| `^=== round (\d+)/(\d+) \((\w+)\) ===` | round_start |
| `^\s+android_id: (\S+) -> (\S+)` | android_id |
| `^\s+cold boot with -wipe-data` | cold_boot |
| `^\s+click ok: (\w+) apk: (.*)` | click_ok / click_fail |
| `^\s+host download ok: (\d+) bytes` | host_download_ok |
| `^\s+host download failed` | host_download_fail |
| `^\s+install attempt (\d+) : (.*)` | install_attempt |
| `^\s+(chrome\|setup\|app) tap: (.*)` | *_tap |
| `^\s+channel: (.*) \| status: (\w+)` | channel_status |
| `^model: (.*)` / `^qemu: (.*)` / `^plan: (.*)` | run_meta |

解析失败的行照样进 `log_lines`，不丢。

### 已定实现细节（builder 审后）

- CSV 列名映射：`reset` → `action`，`openinstall_channel` → `channel`，其余同名列直接使用
- 脚本的轮次号永远是 1（`=== round 1/1`、CSV 的 `round` 列都是），一律忽略，以 worker 自己的计数器作为 `round_no`
- 子进程 `cwd` 设为脚本所在目录（`cdp_click.mjs` 是按脚本目录解析的）；`script_path` 默认 `../avd_rounds.py`
- 子进程环境加 `PYTHONUNBUFFERED=1`，保证 stdout 能逐行读到
- `NO_PAGE` / `NO_APK` / `BOOT_FAIL` 这些早退分支脚本不会打印独立事件，worker 根据 CSV `status` 合成对应的 `round_events`
- 每轮 CSV 使用独立文件名 `round_<r>.csv`，不会互相覆盖；APK 则固定是 `round1.apk`，必须在轮末立刻采集元数据

### 环境性失败与中止

「环境失败」只指**环境/流程层面的失败**，具体是这些轮次状态：

`BOOT_FAIL`、`NO_PAGE`、`NO_APK`、`CLICK_FAIL`、`INSTALL_FAIL`、`CSV_MISSING`

**不包含** `OPEN_FAIL` 和 `OPEN_NO_CHANNEL`——这两种说明 App 已经启动、只是脚本没在 90 秒内等到 `MainActivity` 或 4 秒内没读到 channelCode，属于实验结果本身，不是环境坏了。之前的 100 轮里有 88 轮 `OPEN_FAIL`，如果把它算进中止条件，长跑会立刻被杀掉。

连续 3 轮环境失败 → 停止循环，剩余轮次写入 `rounds` 并标记 `skipped`，run 状态 `failed`，`error` 记录触发的状态序列（例如 `BOOT_FAIL x3`），同时 `adb emu kill` 收尾。

### 取消

`POST /api/runs/{id}/cancel` 设置 cancel 标志；worker 对当前子进程发送 `SIGTERM` 到进程组，3 秒后仍未退出则 `SIGKILL`。

模拟器由脚本用 `start_new_session=True` 启动，不在脚本进程组里，所以必须单独清理：

1. `adb -s SERIAL emu kill`
2. 2 秒后复查 `adb devices`，如果 `SERIAL` 还在，重试一次
3. 仍在的话，按进程兜底：`pkill -f -- "-avd <AVD>"`

已入库数据保留，run 状态 `canceled`。**取消是终态，不支持续跑**；UI 的取消按钮旁要写明「取消后只能重新开始」。服务重启时，上次遗留的 `running` 行启动时标记为 `interrupted`，同样是终态。

## 8. API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 单页 |
| GET/PUT | `/api/config` | sdk_root、script_path、默认 URL / AVD / rounds |
| POST | `/api/runs` | `{url, rounds, avd?}`，返回 run id |
| GET | `/api/runs` | 历史列表（分页） |
| GET | `/api/runs/{id}` | 运行详情 + 进度 |
| GET | `/api/runs/{id}/rounds` | 每轮结果 |
| GET | `/api/runs/{id}/events?after_id=` | 事件增量 |
| GET | `/api/runs/{id}/logs?after_seq=&limit=` | 原始日志增量 |
| POST | `/api/runs/{id}/cancel` | 取消 |
| GET | `/api/runs/{id}/export.csv` | 从 DB 重新导出 CSV |

## 9. 前端

React + TypeScript + Vite + Ant Design 5，桌面端单页应用。布局用 AntD `Layout`：左侧历史运行侧栏，右侧主区域。

主区域自上而下：

1. **新建运行卡片**：URL 输入框（预填默认值）、rounds `InputNumber`、AVD `Select`（扫描 `~/.android/avd/*.ini`）、开始按钮。有任务在跑时按钮禁用并提示排队；取消按钮旁明确写「取消后不能续跑」。
2. **当前运行概览**：`Statistic` 展示轮次进度、成功、无 channel、失败、已用时长；`Progress` 条显示 `x / rounds`；状态用 `Tag` 上色（OK 绿、OPEN_NO_CHANNEL 橙、OPEN_FAIL 红、skipped 灰、running 蓝）。
3. **轮次表**：AntD `Table`，列有 round、action、android_id 前→后、status、channel、apk_src、点击/打开时间；支持排序与按 status 过滤；行展开可看该轮的 `log_excerpt` 和事件。
4. **事件时间线**：AntD `Timeline`，显示最近的 tap / click / download / install / channel 事件。
5. **原始日志**：`Collapse` 折叠面板，深色等宽字体区域，按 `seq` 增量追加并自动滚到底部。

历史侧栏列出 run（状态、URL、轮数、时间），点进去看同样的详情。

页面每 2 秒轮询 `GET /api/runs/{id}` 与增量接口；刷新页面后从 DB 恢复，不依赖前端内存。视觉上以 AntD 默认主题为基础，统一色板与间距，必要时通过 `ConfigProvider` 调 token，不做花哨动效。

## 10. 运行与部署

```
cd avd_attribution_console/frontend
npm install
npm run build                    # 产物 frontend/dist

cd ..
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn
.venv/bin/python -m app          # 监听 127.0.0.1:8787
```

前端开发模式：`npm run dev`（Vite，代理 `/api` 到 8787），后端同时运行。运行时不依赖 Node，构建好的 `dist/` 由 FastAPI 静态托管。

目录：

```
avd_attribution_console/
  app/
    main.py          # FastAPI + 路由
    worker.py        # 串行任务执行、子进程、解析
    db.py            # schema、连接、查询
    parser.py        # stdout 正则解析 + CSV 导入
    config.py        # 配置读写
  frontend/
    package.json, vite.config.ts
    src/               # React + TS + AntD
  data/              # app.db、runs/<id>/
  docs/
```

前置条件（写进 README）：

- AVD 已创建、系统镜像里带 Chrome
- `ANDROID_HOME` 必须是真实 SDK；当前 shell 的环境变量是错的，应用会用自己的配置覆盖
- `adb` 通过 `PATH` 或 `sdk_root/platform-tools` 找到
- 三份原件（脚本、cdp_click、备份）保持只读

## 11. 风险与已知限制

- **脚本崩溃 → 本轮 CSV 缺失**：用 stdout 解析的 `source=stdout` 部分记录兜底，但 `log_excerpt` 等字段会空；UI 要显式标记 partial，不能静默当成功。
- **channelCode 只读一次（4 秒后）**：脚本行为，包装层不修正。UI 要提示 `OPEN_NO_CHANNEL` 可能是假阴性。
- **同 IP、`installerPackageName=null`、`model` 相同**：这些字段在详情页要显眼展示，避免使用者过度解读。
- **连续失败的中止口径**：`OPEN_FAIL` / `OPEN_NO_CHANNEL` 不计入环境失败——它们在之前的 100 轮里占 89%，属于脚本判定口径问题，不是环境故障。只有连续 3 轮 `BOOT_FAIL` / `NO_PAGE` / `NO_APK` / `CLICK_FAIL` / `INSTALL_FAIL` / `CSV_MISSING` 才中止。
- **取消是终态**：取消或服务重启后不能续跑，只能新建 run。UI 必须写清楚，避免误以为能接着跑。
- **模拟器冷启动慢**：单轮可能 2–8 分钟；100 轮 5–10 小时。后端必须支持页面关闭后继续跑。
- **磁盘**：日志每 run 几 MB；`/tmp/avd_rounds/` 的 APK 由脚本自己覆盖写，不主动清理。

## 12. 留给 builder 的决定

- 日志写库策略：逐行 commit 还是 500ms 批量（只要崩溃时不丢已读行）
- 解析正则的容错和单测覆盖
- 前端具体样式与表格排序
- 进程重启后，上次 `running` 的 run 在启动时标记为 `interrupted` 并展示原因
- 是否需要「导出某个 run 的全部原始日志」下载入口

## 13. 验收标准

1. 网页上填 URL、rounds=3，点开始，能连续跑完 3 轮，`PLAN=wipe`，每轮 Android ID 变化
2. 关闭浏览器再打开，任务继续跑，页面能恢复进度
3. 每轮的 CSV 字段、stdout 每一行、解析事件、模拟器日志都能在页面/DB 里查到
4. 取消后进程和模拟器都被停掉，已跑完的轮次数据不丢；页面明确提示「已终止，不能续跑」
5. 模拟一个必然 `BOOT_FAIL` 的环境（例如把 `AVD` 改成不存在的名字），连续 3 轮后 run 自动中止，剩余轮次显示 `skipped`
6. `avd_rounds.py` 与 `cdp_click.mjs` 的 sha256 与备份一致