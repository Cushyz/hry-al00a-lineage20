# 写在最前

除了这一段之外，所有的内容都由LVM产生。降级的和解BL锁的工作由deepseek v4.1 falsh (1017) 在dsh中完成（约用9h），后面的烧录镜像由GPT Astra 6（约用5h）完成。请看成果：

![[./screenshots/04-success-launcher-with-gapps.jpg]]

本次刷机电脑的软件环境是Fedora 44（过程中少量使用了qemu虚拟机上的windows11 iot ltsc，给这个东西安openssh又折腾了好久😂，主要用来中途尝试一些windows工具，不出所料的是，windows在这么短的时间内进行了一次自动更新😰）。
耗费的大部分时间其实在我手工进入进非官方fastboot模式，此外，后文中说的进入VCOM模式我在后面摸索出了更简单的方法：
1. 断开电池；
2. 插上usb线；
3. 多次尝试短接第二排的第二个触点和屏蔽罩（或者任何接地点）直到电脑上出现信息；
4. 接上电池（如果不接上电池会重启无法进入fastboot）。
   
以及我还有一个提示：手机里面有一个塑料罩必须拆掉才能把电池排线扣下来，然而这个塑料罩上面有金属触点😂，如果你不把它安上是不能导通开机键的，如果你发现你的开机键或者音量键失灵了，请不要慌张😂。
那么，现在开始享受AI写的东西吧：

# 荣耀 10 青春版 HRY-AL00a：LeaOS 安装与修复记录

在一台国行 **HRY-AL00a / Kirin 710** 上，恢复 EMUI 9.1 原始分区布局后，成功启动 LeaOS-OSS 20.0（Android 13），安装 MindTheGapps，并完成桌面与通话测试的记录。

**成功的关键是两项独立修复：保持原始 GPT，适配动态分区容量；修复 ROM 的 `init` 读取 9 字节机型名时使用 8 字节缓冲区的问题。** 只完成前一项，会出现“安装成功但启动循环”。

记录截止：2026-10-23（Asia/Shanghai）。这是单台设备的实验记录，不是 LeaOS 官方发行版，也不是适用于全部荣耀/华为机型的一键教程。

## 免责声明

- 本仓库是**单台设备的实验记录与社区互助成果**，不是华为、荣耀、LineageOS、LeaOS、MindTheGapps 或任何上游项目的官方发布，与上述主体无隶属、授权或背书关系。
- 解锁引导程序、刷写分区、改写动态分区元数据、修改 `init`、清空数据等操作**均有风险**，可能导致设备无法启动、数据永久丢失、保修失效。请自行评估并承担后果。
- 内容按**现状**提供，不附带任何明示或暗示担保（包括但不限于适用性、正确性、不侵权）；作者与贡献者不对任何直接或间接损失负责。
- 动手前请自行确认：机型与固件版本、设备当前分区布局、文件来源与校验值，并保留可回退的原厂固件与备份。
- 本仓库**不再分发**厂商固件、ROM、GApps 等第三方二进制；随附文件仅用于本地复现，其版权与许可归各自上游，使用前请遵守相应条款。
- **不要在来源不明的安装包上忽略签名告警**。本记录中"接受签名不匹配"的前提是：包由使用者自己按本仓库步骤生成并可校验。

## 只想刷机

看 [FLASHING.md](FLASHING.md)：只列操作顺序和判断点，不解释原理。

## 本目录包含的文件

| 文件 | 大小 | SHA256（前 16 位） | 用途 |
|---|---:|---|---|
| `LeaOS-OSS-20.0-20260815-harry.zip` | 1.0 GB | `9958ee9b21517538` | 原始 ROM，改包输入 |
| `MindTheGapps-13.0.0-arm64-20231025_200931.zip` | 368 MB | `3ff2edaa75406eb4` | GApps |
| `Recovery-OSS-Harry.7z` | 28 MB | `17d40c40374b8ce2` | Recovery 原始包 |
| `rom/boot.img` | 24 MB | `aaf956be87deafc4` | 刷 `kernel` |
| `rom/recovery.img` | 32 MB | `2b05ceb79dbbf4b3` | 刷 `recovery_ramdisk` |
| `rom/recovery_vendor.img` | 16 MB | `34ff1b3bd7d57c89` | 刷 `recovery_vendor` |
| `rom/unsparse_super_empty.img` | 4.9 KB | `c95c8e6b6f560ac2` | 原始空 super（仅供参考） |

完整校验值：

```text
9958ee9b21517538cbb42d7f1c79e96fb4449173945594d574516175ec17a81a  LeaOS-OSS-20.0-20260815-harry.zip
3ff2edaa75406eb4214402fca6906d4b413ab50afdb1af033d9e396992338d0b  MindTheGapps-13.0.0-arm64-20231025_200931.zip
17d40c40374b8ce2335d9404accd37c7eb6d1b83b8dc6cdedd314b3f6a4b7aeb  Recovery-OSS-Harry.7z
aaf956be87deafc463bbdbdda22ca1dc5ea833a0cf74c5aa7e2d67da386aa4d4  rom/boot.img
2b05ceb79dbbf4b30d9ce0b3e78f4a3fbc5372317e7cd1ae9fb7c729ce00880e  rom/recovery.img
34ff1b3bd7d57c893abcddf69e8bd5e5cdebb8096fa64d5c1284ed2c56fee72f  rom/recovery_vendor.img
c95c8e6b6f560ac21ea4290db01189d9f254df600a09b6dcf61acb53de5f370e  rom/unsparse_super_empty.img
```

> 以上是本地完整性校验值，不是上游发行者签名。`rom/boot.img` 与 `evidence/validation.json` 中记录的 LeaOS kernel 哈希一致。

## 现场照片

| 文件 | 内容 |
|---|---|
| [01-failure-liblp-update-dynamic-partitions.jpg](screenshots/01-failure-liblp-update-dynamic-partitions.jpg) | 未做容量适配时 sideload 失败：`liblp` 报分区表不可读，`update_dynamic_partitions` 断言失败 |
| [02-failure-unlocked-warning-then-fastboot.jpg](screenshots/02-failure-unlocked-warning-then-fastboot.jpg) | 解锁后的启动警告页；此时会自动继续，最终回到 fastboot |
| [03-success-about-phone.jpg](screenshots/03-success-about-phone.jpg) | 成功启动后「关于手机」：Android 13 / LineageOS 20-20260815-RELEASE-harry / HRY-AL00a |
| [04-success-launcher-with-gapps.jpg](screenshots/04-success-launcher-with-gapps.jpg) | 成功进入桌面，GApps 已生效（Google、Play 商店、身份验证器） |

照片只用于展示现象，不含账号、号码或串号；IMEI 一栏在拍摄时处于未展开状态。03 拍摄时尚未识别到 SIM（界面显示“无法获取”），后续插卡与通话验证见 [验证章节](docs/07-validation.md)。

## 许可

本仓库按内容分别授权：

| 范围 | 许可 |
|---|---|
| 代码：`scripts/`、`patches/`、`al00-leaos-lab/scripts/` | **MIT**，见 [LICENSE](LICENSE) |
| 文档与图片：`README.md`、`CONTRIBUTING.md`、`FLASHING.md`、`docs/`、`screenshots/` | **CC BY-SA 4.0**，见 [LICENSE-docs](LICENSE-docs) |

转载或引用文档、照片请注明来源并保留本仓库链接；修改后的衍生内容需以相同协议发布。

`rom/`、`*.zip`、`*.7z` 以及 `al00-leaos-lab/` 下的构建产物**不属于**上述授权范围：它们是第三方或本地生成的二进制，版权与许可归各自上游，随附目的仅为本地复现。

## 阅读顺序

1. [降级到 EMUI 9.1](docs/01-downgrade-to-emui9.md)：BootROM 入口、RAM fastboot、固件解包、分区刷写与首次启动。
2. [解锁 USER 锁](docs/02-unlock-userlock.md)：两种锁状态、补丁地址、按电源键确认、持久性。
3. [降级后的安装过程](docs/03-after-downgrade.md)：本文的主体，包含入口、容量适配、安装、启动修复与 GApps。
4. [机型名解析问题](docs/04-init-model-fix.md)：原因、六条指令、验证和适用边界。
5. [离线复现工具](docs/05-offline-reproduction.md)：容量改包与 init 文件补丁；不操作手机。
6. [现象与排查](docs/06-troubleshooting.md)：白/黑 fastboot、Recovery、sideload、SIM 等。
7. [验证范围与证据摘要](docs/07-validation.md)。

## 已验证与未验证

| 项目 | 本次结果 |
|---|---|
| 降级到 EMUI 9.1（保留原始 GPT） | 成功，见 [降级章节](docs/01-downgrade-to-emui9.md) |
| USER 锁解锁（打补丁跳过校验，非解锁码） | 成功，见 [解锁章节](docs/02-unlock-userlock.md) |
| 保留 EMUI 9.1 原始 GPT | 成功，无需扩大物理 preas |
| LeaOS Recovery / sideload | 成功 |
| 原版 init + 容量适配包 | 启动循环 |
| 修复 init 后启动 | 进入设置向导及桌面 |
| 恢复原始 LeaOS kernel，移除诊断 kernel | 回读校验通过，之后正常进入系统 |
| GApps | 31 个选定载荷文件及 init 共 32 项校验通过，用户完成后续设置 |
| 中国移动 SIM | 单卡识别、LTE 注册、接打电话成功 |
| Wi-Fi | 用户完成连接及应用配置 |
| 双 SIM | 本次只观察到一个可用逻辑电话；未修复、未确认根因 |
| 移动数据实际联网、相机、指纹、SD 卡、长期待机 | 未完成逐项验收 |
| NFC | 日志曾有服务异常，未解决；不据此认定此硬件应支持 NFC |

## 使用前必须理解

- 本仓库的容量构建脚本生成的 ZIP **不包含 init 修复**，不能当作完整可启动成品。
- 本仓库没有通用手机端 init 安装器。原现场写入器依赖该设备已采集的 LP 元数据与块映射，不能直接移植到其他手机。
- `wipe-super`、ROM 安装与恢复出厂设置会覆盖相应分区或清除数据；不要把成功案例当成数据保留方案。
- 暂不直接 OTA 升级或勾选随系统更新 Recovery。更新可能覆盖 init 修复和本次适配，需要重新核验。
- 不上传固件、ROM、GApps、APK、OEMINFO、基带备份或原始日志。仓库仅包含文字、源码和精选的非个人证据。

## 版本与来源

- 测试底包：EMUI `9.1.0.226(C00E225R3P1)`，原始布局。
- 测试 ROM：`LeaOS-OSS-20.0-20260815-harry.zip`。
- 测试 GApps：`MindTheGapps-13.0.0-arm64-20231025_200931.zip`。
- [LeaOS 原作者发布帖](https://xdaforums.com/t/rom-huawei-13-leaos-oss-for-honor-lite-10-hry-lx1.4798466/)
- [LeaOS 下载目录](https://sourceforge.net/projects/altairfr-huawei/files/LeaOS-OSS/)
- [测试的 MindTheGapps 版本](https://github.com/MindTheGapps/13.0.0-arm64/releases/tag/MindTheGapps-13.0.0-arm64-20231025_200931)
- [AOSP 动态分区文档](https://source.android.com/docs/core/ota/dynamic_partitions/implement)
- [AOSP LP 元数据格式](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/liblp/include/liblp/metadata_format.h)

上述链接用于归属与背景；测试结论来自本次本地文件分析和设备实测，不表示链接中的最新版仍与本文相同。感谢 LeaOS、LineageOS、AOSP、MindTheGapps、Rime 等上游项目；本仓库不是这些项目的官方支持渠道。

协作与公开前检查见 [CONTRIBUTING.md](CONTRIBUTING.md)。许可证尚待仓库所有者选择；上游软件保留各自许可，本仓库不重新授权上游二进制。
