# 刷机步骤（不含原理）

本页只列操作与判断点。原理、证据和排查见 [docs/](docs/) 各章。

## 前提

- 机型 HRY-AL00a，已恢复到 **EMUI 9.1.0.226** 并能正常启动；
- `USER LockState: UNLOCKED`；
- 能短接进入黑 boot（RAM fastboot），能进入 LeaOS Recovery；
- 电脑有 `adb`、`fastboot`、`python3`，以及 `brotli`、`e2fs*`、`lpmake`、`lpdump`（仅第 2 步需要）。

## 0. 本目录里的文件

| 路径 | 说明 |
|---|---|
| `LeaOS-OSS-20.0-20260815-harry.zip` | 原始 ROM，改包的唯一输入 |
| `MindTheGapps-13.0.0-arm64-20231025_200931.zip` | GApps（Android 13 / arm64） |
| `Recovery-OSS-Harry.7z` | Recovery 原始压缩包 |
| `rom/boot.img`、`rom/recovery.img`、`rom/recovery_vendor.img` | 已解好的 Recovery 三件套 |
| `rom/unsparse_super_empty.img` | 原始空 super 元数据（仅供参考，刷机用的是适配后的那份） |
| `al00-leaos-lab/scripts/` | 改包脚本 |
| `scripts/patch-init.py` | 生成 init 修复文件（仅电脑上操作） |

## 1. 确认三件套（已解好可跳过）

```bash
ls -l rom/boot.img rom/recovery.img rom/recovery_vendor.img
```

需要重新解出时：

```bash
7z x -y -orom Recovery-OSS-Harry.7z
```

## 2. 生成容量适配包（已有成品可跳过）

```bash
python3 al00-leaos-lab/scripts/build.py
python3 al00-leaos-lab/scripts/verify_product.py
ls -l al00-leaos-lab/output/
```

必须看到：

```text
al00-leaos-lab/output/unsparse_super_empty-al00.img
al00-leaos-lab/output/LeaOS-OSS-20.0-20260815-harry-AL00-EXPERIMENTAL-UNSIGNED.zip
```

> `build.py` 会校验输入 ROM 的 SHA256；不是 `9958ee9b…7a81a` 会直接拒绝。

## 3. 进入黑 boot

1. 断电池排线，等 10 秒，接回。
2. 镊子压住测试点与屏蔽罩，保持压住插线，插上瞬间松手。
3. 确认：

```bash
lsusb | grep 3609
```

4. 运行 exploit（按实验环境的封装）：

```bash
KIRIN_BOOTLOADER=fastboot_dec.img python3 exploit_fixed.py
```

5. 看到 `Bootloader downloaded!` 后确认：

```bash
fastboot devices
```

## 4. 刷 Recovery 三件套

```bash
fastboot flash kernel            rom/boot.img
fastboot flash recovery_ramdisk  rom/recovery.img
fastboot flash recovery_vendor   rom/recovery_vendor.img
```

三条都要 `OKAY`。

## 5. 初始化动态分区

```bash
fastboot wipe-super al00-leaos-lab/output/unsparse_super_empty-al00.img
```

必须看到 system、cust、odm、preas、product、vendor **六项全部 OKAY**。任何一项失败就停下，不要继续。

## 6. 进入 LeaOS Recovery

```bash
fastboot reboot recovery
```

`OKAY` 不代表已进入。以屏幕为准：

- 出现 **Reboot system now / Apply update / Factory reset / Advanced** → 成功；
- 出现白色 fastboot、解锁警告、或华为 eRecovery（下载最新版本并恢复等五个按钮）→ 未进入。关机后重新短接，再试一次；必要时用按键组合进入。

## 7. 格式化数据

在 LeaOS Recovery 里：

```text
Factory reset → Format data/factory reset → 输入 yes
```

## 8. 刷入适配包

```text
Apply update → Apply from ADB
```

电脑：

```bash
adb sideload al00-leaos-lab/output/LeaOS-OSS-20.0-20260815-harry-AL00-EXPERIMENTAL-UNSIGNED.zip
```

判断标准是手机屏幕最后的 **`Install completed with status 0`**，不是电脑上的 `Total xfer` 比值。过程中出现签名不匹配提示时，只有在你确认用的是自己生成的包才继续。

保存日志：

```bash
adb pull /tmp/recovery.log private-reports/rom-recovery.log
```

## 9. 首次启动

重启后等待 5–10 分钟。

- **进入设置向导 / 桌面** → 跳到第 10 步；
- **循环重启** → 需要 init 修复。本目录**不提供**手机端写入器；修复后的 `init` 整个文件 SHA256 应为：

```text
379a9bbf5a920aacfdc8805caafd34334fc6c3f8e2f89229fa0b15c01e1dcbe1
```

  没有可用的写入器时，停在这里，不要反复格式化或重刷。

## 10. 刷 GApps

回到 LeaOS Recovery：

```text
Apply update → Apply from ADB
adb sideload MindTheGapps-13.0.0-arm64-20231025_200931.zip
```

同样以手机最后 **status 0** 为准。

```bash
adb pull /tmp/recovery.log private-reports/gapps-recovery.log
```

## 11. 完成检查

- 能进入桌面，Wi-Fi 可连接；
- 设置 → 关于手机，系统为 Android 13 / LineageOS 20；
- 插卡后能识别并拨打电话；
- 需要时再登录 Google 账号并完成 Play 认证。

## 12. 常见卡点

| 现象 | 处理 |
|---|---|
| `preas size is too small` | 用的不是适配包，回到第 2 步 |
| `update_dynamic_partitions` 失败 | `wipe-super` 没成功或用的不是适配后的空元数据 |
| `reboot recovery` 后回 fastboot | 正常现象，重新短接再试 |
| 刷完一直重启 | init 未修复（第 9 步） |
| 签名不匹配 | 只对自建包继续；来源不明不要刷 |
| 刷写中途掉线 | 设备仍在 fastboot，重跑对应步骤即可 |

详细现象与边界见 [docs/06-troubleshooting.md](docs/06-troubleshooting.md)。
