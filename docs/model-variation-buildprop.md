# 备选方案：改 build.prop 改变机型（当前未启用）

- 日期：2026-10-26
- 状态：**未启用，仅留档**。当前项目按方案 A 执行：接受 `ro.product.model` 不变。
- 适用场景：后续需要验证归因平台是否按机型 / Build 指纹做聚类或风控时。

## 为什么 `-prop` 不行（已实测）

用 `Pixel_6_API_34_B` 启动：

```bash
emulator -avd Pixel_6_API_34_B -no-window -no-snapshot -no-audio \
  -prop ro.product.model="Pixel 7" \
  -prop ro.product.brand=google \
  -prop ro.product.manufacturer=Google \
  -prop ro.product.device=panther
```

开机后实测：

| 属性 | 期望 | 实际 |
|---|---|---|
| `ro.product.model` | Pixel 7 | `sdk_gphone64_arm64` |
| `ro.product.device` | panther | `emu64a` |
| `ro.build.fingerprint` | — | `google/sdk_gphone64_arm64/emu64a:14/UE1A.230829.036.A4/12096271:user/release-keys` |

结论：这些 `ro.*` 属性在系统镜像的 `build.prop` 里已经定义且只读，qemu 的 `-prop` 覆盖不了。要改只能改镜像内容本身。

## 前提条件

1. **必须用可 root 的镜像**：`system-images;android-34;google_apis;arm64-v8a`
   - `google_apis_playstore` 镜像禁用 `adb root`，这条路走不通
   - 当前测试用的就是 playstore 镜像，所以现有 AVD 不能直接改
2. **Chrome 可用性要先确认**：`avd_rounds.py` 依赖 Chrome + CDP。`google_apis` 镜像通常带 Chrome，但下载前请先确认；如果不带，需要另外装 Chrome APK。
3. 磁盘预留：系统镜像 + AVD 约 10GB。
4. 机型属性必须**成套一致**，只改 `ro.product.model` 会被 `Build.FINGERPRINT` / `Build.DEVICE` 等互相矛盾地暴露。

## 操作步骤（未验证，按前提前提执行）

```bash
SDK=$HOME/Library/Android/sdk
export ANDROID_SDK_ROOT=$SDK

# 1. 下载可 root 的镜像
$SDK/cmdline-tools/latest/bin/sdkmanager \
  "system-images;android-34;google_apis;arm64-v8a"

# 2. 新建 AVD（不要复制现有 AVD 目录，否则 android_id / 镜像内容会共享）
echo no | $SDK/cmdline-tools/latest/bin/avdmanager create avd \
  -n Pixel_Model_A \
  -k "system-images;android-34;google_apis;arm64-v8a" \
  -d pixel_6

# 3. 必须带 -writable-system 启动，否则 remount 不生效
$SDK/emulator/emulator -avd Pixel_Model_A -no-snapshot -writable-system

# 4. 取得 root 并重新挂载
$SDK/platform-tools/adb root
$SDK/platform-tools/adb remount
# 若 remount 失败，可能需要先关 verity：
#   adb disable-verity && adb reboot
#   重启后再次 adb root && adb remount

# 5. 修改属性文件（Android 10+ 是动态分区，实际路径可能是
#    /system/system/build.prop 而不是 /system/build.prop，先 ls 确认）
adb shell 'ls -l /system/build.prop /system/system/build.prop /vendor/build.prop /product/build.prop'
adb pull /system/system/build.prop /tmp/build.prop
# 编辑以下属性，保持内部一致：
#   ro.product.model=Pixel 7
#   ro.product.brand=google
#   ro.product.manufacturer=Google
#   ro.product.device=panther
#   ro.product.name=panther
#   ro.build.product=panther
#   ro.build.fingerprint=google/panther/panther:14/UE1A.230829.036.A4/12096271:user/release-keys
adb push /tmp/build.prop /system/system/build.prop
# /vendor/build.prop、/product/build.prop 里若也有同名属性，需要同步改

# 6. 重启并验证
adb reboot
adb shell getprop ro.product.model
adb shell getprop ro.build.fingerprint
```

## 需要验证的问题

- `-wipe-data` 只清 userdata，`-writable-system` 的 overlay 是否保留（预期保留，但必须实测）
- `adb remount` 在该镜像上是否一次成功；失败时 `disable-verity` 的具体流程
- 改完后 Chrome、OpenInstall、目标 App 是否仍正常（有些 App 会校验 Build 一致性）
- `ro.product.model` 到底在哪个分区文件里（system / vendor / product 都可能有）
- 系统镜像自带的 Chrome 是否存在；不存在时如何安装且保证 CDP 可用

## 风险与限制

- 这属于「改机」，和测试方案文档 八.5「使用改机工具规避平台识别属于刷量对抗，不在本方案范围内」的边界冲突。仅在确认测试目的包含「平台是否按机型聚类」时再启用。
- 只改属性无法消除模拟器特征：`ro.kernel.qemu=1`、传感器缺失、基带缺失、`ro.hardware` 等仍然存在。
- `installerPackageName=null`（宿主机下载 + `pm install`）和单一出口 IP 这两个更大的信号不会因为改机型而消失。
- 改完的 AVD 是一个新的「机型」样本，`android_id` 仍由 userdata 决定，和机型无关。

## 如果太重

替代做法：接受 `ro.product.model` 不变，只换系统镜像版本（API 34 / 35 / 36）或镜像类型（`google_apis` / `google_apis_playstore`），让 `ro.build.id`、`ro.build.fingerprint` 里的版本段产生差异。这不需要 root，也不会碰改机边界，但 `sdk_gphone64_arm64` 这个 model 不会变。