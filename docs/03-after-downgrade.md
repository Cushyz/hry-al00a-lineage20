# 第二部分：降级后的 LeaOS 安装与修复

本文记录 2026-10-22 至 23 日的成功过程。命令展示当时的操作关系；只有核验版本、设备布局、配套产物和恢复路径后才能用于复现。**容量适配和 init 修复必须同时解决；本仓库尚未提供通用的手机端 init 写入器。**

## 1. 起点和需要的工具

设备为 HRY-AL00a，原厂 EMUI 9.1 已能启动，保留 9.1 原始 GPT，电源键与音量键都正常。不是继续使用此前扩大 preas 的实验分区表。

电脑侧需要 Linux、ADB、fastboot、Python 3.11+；离线改包还需要 Brotli、e2fsprogs（e2fsck、resize2fs、dumpe2fs、debugfs）和 AOSP lpmake/lpdump。准备足够的本地空间存放原包、还原镜像、复核副本及输出；建议至少预留 15 GiB，这不是测得的峰值。

ROM、Recovery、kernel 必须来自同一测试版本。保留原厂恢复材料，以及自己设备的必要备份。本仓库不分发这些文件。

## 2. 先分清白 boot、黑 boot 与 Recovery

| 本文称呼 | 实际含义 | 本台观察 |
|---|---|---|
| 白 boot | 原厂 fastboot | FB LOCKED / USER UNLOCKED，写 odm 被拒 |
| 黑 boot | BootROM 工具加载的 RAM fastboot | 两者显示 UNLOCKED，可完成本次所需写入 |
| LeaOS Recovery | 安装 ROM 与读取设备的恢复环境 | ADB 通常显示 recovery |
| Huawei eRecovery | 联网恢复、紧急备份、重置、重启、关机的原厂界面 | 本次在这里没有可用 ADB |

黑 boot 不是 fastbootd。白 boot 的写入限制不会因为换了尺寸正确的元数据而消失。`wipe-super` 在某一项失败前可能已写了前面的分区；失败不等于完全未改动。

## 3. 原包为什么装不进去

原包针对的布局与本台国行布局不同：

| 物理载体 | 本台 9.1（MiB） | 原 ROM 元数据声明（MiB） |
|---|---:|---:|
| system | 1896 | 1504 |
| cust | 88 | 88 |
| odm | 96 | 96 |
| preas | 136 | 936 |
| product | 1048 | 1000 |
| vendor | 480 | 480 |
| 合计 | 3744 | 4104 |

原包五个逻辑分区共 **3869.22265625 MiB**，也超过本台物理总容量，尚未计入保留区。先前按整数相加得到约 126 MiB 的缺口，是合理的粗估；精确差额约 125.22 MiB。

因此有两个不同的问题：原 LP 元数据把 preas 声明得过大；逻辑文件系统总大小也超过真实可用容量。仅修改一个声明数字不能解决全部问题。

成功方案保留 GPT，只修改 LP 元数据和 product 文件系统：

- 六个物理载体大小改为本台实际值；各保留前 1 MiB。
- group 上限设为 **3738 MiB**，保留 LP 10.0、65536 字节元数据容量、2 个 metadata slot、4096 字节块。
- product ext4 从 **1664 MiB** 缩至 **1400 MiB**；原 product 逻辑分区约 1665.71 MiB，其文件系统尾后是零填充。
- 其余逻辑分区保持大小，总逻辑容量变为 **3603.51171875 MiB**，预算余量约 **134.49 MiB**；另用 lpmake 实际分配验证对齐及 extent 边界。
- 没有为了缩容删应用。缩容前后 586 个目录项、445 个普通文件及 4109 行稳定 inode/扩展属性比较一致，包括可见 SELinux 标签。

**逻辑 product 1400 MiB 可以跨载体分配。不能向只有 1048 MiB 的物理 product 直接 flash 这个镜像。** `system` 此时还承担动态分区元数据及数据载体的角色，不是原厂单一 ext4 的简单替换。

## 4. 准备容量适配产物

见 [离线复现](05-offline-reproduction.md)。本次构建替换了 ZIP 中五项：

```text
unsparse_super_empty.img
dynamic_partitions_op_list
product.new.dat.br
product.transfer.list
product.patch.dat
```

其他条目逐项与原包比较一致。输出是 **unsigned 实验包**；保留原 otacert 文件不意味着改包仍有原作者签名。CRC 和本地 SHA256 可检查一致性，不能代替来源真实性判断。

构建产物还未修复 init。进入刷机阶段前，应已理解第 7 节，并有针对实际设备验证过的写入方案，不能指望刷完容量适配包就启动。

## 5. 安装 Recovery 并初始化动态分区

本次在黑 boot 中使用以下配套镜像：

先从已经核验 SHA256 的原 ROM 提取这三个条目到本地 `rom/`，不要混用其他版本的 Recovery：

```bash
mkdir -p rom
unzip LeaOS-OSS-20.0-20260815-harry.zip boot.img recovery.img recovery_vendor.img -d rom
```

在目标设备的黑 boot 中逐条执行：

```bash
fastboot flash kernel rom/boot.img
fastboot flash recovery_ramdisk rom/recovery.img
fastboot flash recovery_vendor rom/recovery_vendor.img
```

**每条必须成功后再继续**。这里 `boot.img` 刷到华为的 `kernel`，不是照搬其他设备的 `boot` 分区名称。

随后在同一具备权限的环境执行了：

```bash
fastboot wipe-super al00-leaos-lab/output/unsparse_super_empty-al00.img
```

system、cust、odm、preas、product、vendor 六项均返回 OKAY。这个步骤会初始化/覆盖系统动态分区相关区域，不是读取检查，也不是已经正常运行后需要重复执行的维护动作。

`unsparse_super_empty-al00.img` 是元数据输入，供上述 wipe-super 使用，不要当普通 system 镜像直接 flash。离线验证生成的 allocated-layout 镜像也不是刷机产物。

本次 `fastboot reboot recovery` 的表现不稳定：有时进入 LeaOS Recovery，有时返回白 boot 或经过解锁警告进入 eRecovery。因此不能仅凭命令返回 OKAY 判断已进入目标 Recovery。用户通过关机、按键和 USB 状态切换最终回到 LeaOS Recovery；没有形成跨设备稳定的按键秒数教程。

## 6. 在 LeaOS Recovery sideload

确认屏幕是 LeaOS Recovery，在 Apply update → Apply from ADB 后执行：

```bash
adb sideload al00-leaos-lab/output/LeaOS-OSS-20.0-20260815-harry-AL00-EXPERIMENTAL-UNSIGNED.zip
```

本次在确认使用自己核验过的改包后，接受了 Recovery 的签名不匹配提示。来源未知的包不能照此忽略告警。

电脑显示 `Total xfer: 0.97x` 不是失败判据。应查看手机最后的 **Install completed with status 0**，并保存完整日志：

```bash
mkdir -p private-reports
adb pull /tmp/recovery.log private-reports/rom-recovery.log
```

如仍出现 `preas size is too small` 或 `update_dynamic_partitions` 失败，停在 Recovery 核对布局和包；不要用扩大 GPT 或反复格式化碰碰运气。

## 7. 安装成功后仍循环重启：修复 init

本次确实先经历了启动循环。单独的橙色解锁提示不能说明根因；Recovery 的 dmesg 主要记录当前 Recovery，也不能自动当作上一轮 Android 启动日志。

通过正常启动阶段的早期日志、只读 OEMINFO 和 ROM 二进制分析，定位到 `libinit_variants` 读取机型名的兼容性问题。`HRY-AL00a` 是 9 字节，而这版 init 使用 8 字节缓冲区和 checked-copy 容量，会触发失败路径。

最终修复六条 ARM64 指令，同时扩大分配、清零、checked-copy 容量及短字符串构造；保留完整机型名和边界检查，不改 OEMINFO，不冒充其他型号。详见 [补丁分析](04-init-model-fix.md)。

现场是在未挂载相关系统分区的 LeaOS Recovery 中，由严格绑定设备和 LP 元数据的脚本备份、写入一个已有 4 KiB 数据块，再完整回读 init 确认哈希。**这里不是通用固定偏移刷写方法**，本仓库有意不发布可对任意设备执行该写入的命令。

修改后进入了设置向导及桌面。之后恢复原 ROM 的 LeaOS kernel、移除临时诊断 kernel，再次正常启动。无需把诊断 kernel 当日常依赖，也不应复制早期废弃的 boot-loglevel7 镜像。

## 8. GApps：本次采用先验证 ROM、再清数据安装

本台先确认无 GApps 的 ROM 能启动，随后用户确认测试数据可清除。实际顺序：回到 LeaOS Recovery → 核对映射、空间、init → 恢复出厂设置 → 不启动 Android，立即 sideload GApps → 核验 → 启动。

测试包是 Android 13 / arm64 / SDK 33 的 `MindTheGapps-13.0.0-arm64-20231025_200931.zip`，不是任意最新版。

| 分区 | 安装前实测可用 MiB | 估算需求 MiB（含 10 MiB 缓冲） |
|---|---:|---:|
| system | 75.1 | 10.0 |
| product | 844.5 | 537.7 |
| system_ext | 64.5 | 25.8 |

首次进入 Recovery 时可能还没有 `/dev/block/mapper/system`；本次通过 Advanced → Mount /system 建立映射，随后只读检查。**这不表示 init 原始块写入时可以保持挂载**，两类操作要求不同。

恢复出厂设置清除内部应用、设置和文件；不是格式化 system/product，也不是运行 Huawei 联网修复。保持 Recovery，选择 Apply from ADB 后：

```bash
adb sideload MindTheGapps-13.0.0-arm64-20231025_200931.zip
adb pull /tmp/recovery.log private-reports/gapps-recovery.log
```

实际日志含签名验证告警、Scudo OOM 字样和首次复制遇到符号链接的问题；后续安装器仍完成，最后 status 0。我们没有仅据此宣布成功，而是逐个核对选定的 31 个 GApps 文件以及 init，共 32 项全部匹配，并确认 addon.d 脚本存在。结果不能推广为“所有类似告警都可忽略”。

不要在此阶段重新 sideload 原 ROM 或仅容量适配的旧实验包，否则会覆盖 init 修复。恢复出厂设置与覆盖系统分区是不同操作。

## 9. 进入桌面与日常使用

成功启动后的系统信息与桌面见 [screenshots/03](../screenshots/03-success-about-phone.jpg) 和 [screenshots/04](../screenshots/04-success-launcher-with-gapps.jpg)。

网络暂不能连接 Google 时，可在设置向导提供选项的情况下跳过登录，进入桌面配置 Wi-Fi 和代理，再登录。没有验证所有版本向导都允许离线跳过。

本次随后安装/配置应用；文件管理器和中文输入法可作为普通 APK 单独安装，不需要为此刷 ROM。需要 ADB 时先在新系统启用 USB 调试并授权电脑：

```bash
adb install path/to/application.apk
```

中国移动卡后来可识别并能接打电话，LTE 注册成功；此前开机热插拔、卡槽及旧日志状态混在一起，不能由最初的“无 SIM”直接判定基带不兼容。交换两张卡并重启后，仅一个逻辑电话可用，用户接受单卡加 SD 的使用方向；SD 卡本身尚未逐项测试。

先保持当前可用系统，逐步验证移动数据网页、相机、声音、指纹、存储、待机和重启。不要直接 OTA；任何新版都需要重新核验布局、init 和 Recovery。
