# AVD 归因测试控制台

把原来的 `../avd_rounds.py` 包成一个本地部署的全栈应用：后端 FastAPI + SQLite 负责调度、留痕，
前端 React + Ant Design 单页负责发起运行、看进度和查明细。脚本本身**不改动**。

- 目标：每轮重建模拟器 → 打开浏览器 → 下载安装 → 唤起 App，把中间数据全部落库
- 平台侧「是否计入新用户 / 渠道是否正确」这类后台核对仍然要人工完成，控制台只记录脚本能采集到的数据

## 目录

```
backend/          FastAPI + worker + SQLite 访问层 + pytest
frontend/         Vite + React 18 + TypeScript + Ant Design 5
docs/             设计文档、计划、型号变化说明
data/             运行时生成（app.db、每轮 CSV、config.json）
```

## 环境要求

- Python 3.9+（本项目在 3.9.12 上验证）
- Node 18+（本项目在 22.18.0 上验证）
- Android SDK：`platform-tools/adb`、`emulator`、至少一个可启动的 AVD
- 含 Chrome 的系统镜像（脚本用 CDP 点击下载按钮），例如
  `system-images;android-34;google_apis_playstore;arm64-v8a`

## 安装

```bash
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

## 启动（一键）

```bash
./start.sh
```

已在跑就先停再起，所以同一条命令就是重启。前端源码比 `dist` 新时自动重新构建。

| 命令 | 作用 |
|------|------|
| `./start.sh` | 启动 / 重启 |
| `./start.sh stop` | 停止（连同它拉起的 `avd_rounds.py` 一起收掉，避免残留一个还在抹机器的孤儿进程） |
| `./start.sh status` | 是否在跑、健康检查、有无残留脚本 |
| `./start.sh logs` | 跟踪 `data/server.log` |
| `./start.sh --no-build` | 跳过前端构建 |
| `./start.sh --port 9000` | 换端口（也可用 `PORT=9000 ./start.sh`） |

打开 <http://127.0.0.1:8787>。

手动等价命令（`./start.sh` 内部就是这些）：

```bash
cd frontend && npm run build && cd ..
python3 -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8787
```

前端热更新开发模式：终端 A 跑上面的 uvicorn，终端 B：

```bash
cd frontend && npm run dev      # 5173，/api 已代理到 127.0.0.1:8787
```

## 配置

配置存在 `data/config.json`，也可通过 `GET/PUT /api/config` 读写：

| 键 | 说明 |
|---|---|
| `sdk_root` | Android SDK 根目录，默认 `~/Library/Android/sdk` |
| `script_path` | `avd_rounds.py` 的绝对路径 |
| `default_url` | 新建运行表单预填的推广链接 |
| `default_avd` | 默认 AVD |
| `default_rounds` | 默认轮数 |

## ANDROID_HOME 的坑

本机 shell 里的 `ANDROID_HOME` 指向 `/opt/homebrew/Caskroom/android-sdk`，那里没有 `adb`，
而且 `adb` 不在 `PATH` 里。控制台自己的所有 adb/emulator 调用都走 `sdk_root` 下的绝对路径，
传给子进程的环境也会覆盖 `ANDROID_HOME` 和 `PATH`，所以**不需要改 shell**。

只有手工直接跑脚本时才需要：

```bash
ANDROID_HOME=$HOME/Library/Android/sdk \
PATH=$HOME/Library/Android/sdk/platform-tools:$PATH \
ROUNDS=1 python3 ../avd_rounds.py
```

## AVD 准备

- 已可用：`Pixel_6_API_34`、`Pixel_6_API_34_B`（都由 API 34 playstore 镜像创建，Chrome 在位）
- `Medium_Phone_API_36` 缺 android-36 镜像，启动会失败；端口守卫会把这种失败报成
  `expected emulator-5554, found emulator-<port>`
- 手机型号（`ro.product.*`）无法用 `emulator -prop` 覆盖，实测无效。如需型号变化，
  见 `docs/model-variation-buildprop.md` 里的 build.prop 方案（需要可 root 的 `google_apis` 镜像）

## 数据

- SQLite：`data/app.db`（WAL 模式）
- 每轮 CSV：`data/runs/<run_id>/round_<n>.csv`
- 入库内容：原始 stdout/stderr 逐行日志、解析出的结构化事件、每轮 CSV 行、APK 元数据
  （路径 / 大小 / mtime / SHA-256，不复制 APK 文件）、模拟器日志新增部分
- APK 固定落在 `/tmp/avd_rounds/round1.apk`，每轮都会被覆盖，所以 worker 在每轮结束立刻采集元数据

## 行为约束

- 串行执行：同一时刻只有一个 run 在跑，新提交排队
- 连续 3 轮「环境失败」自动中止，剩余轮次标记 `skipped`：
  `BOOT_FAIL`、`NO_PAGE`、`NO_APK`、`CLICK_FAIL`、`INSTALL_FAIL`、`CSV_MISSING`
- `OPEN_FAIL` / `OPEN_NO_CHANNEL` 属于实验结果，不计入中止条件
- **取消是终态，取消后不能续跑**，只能重新开始
- 服务重启时，遗留的 `running` 记录会被标记为 `interrupted`（同样是终态）

## 脚本只读

`avd_rounds.py` 和 `cdp_click.mjs` 保持原样，`backend/tests/test_scripts_untouched.py`
用 SHA-256 守住两条脚本，被改动时测试直接失败。

## 测试

```bash
cd backend && python3 -m pytest
```

前端类型检查与构建：

```bash
cd frontend && npx tsc --noEmit && npm run build
```