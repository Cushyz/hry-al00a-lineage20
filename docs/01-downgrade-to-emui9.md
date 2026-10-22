# 第一部分 A：从 EMUI 10 降级到 EMUI 9.1

本页记录把国行 **HRY-AL00a** 从 EMUI 10 刷回 **EMUI 9.1.0.226** 并恢复原始分区布局的过程。它是第二部分（LeaOS 安装）的**起点准备**，不是 LeaOS 安装本身。

## 0. 适用范围与交付状态

| 项 | 本页记录的值 |
|---|---|
| 机型 | HRY-AL00a（Kirin 710 / Hi6260），国行 |
| 起始固件 | EMUI **10.0.0.168**(C00E70R3P7)，Android 10 (SDK 29)，动态分区，`super` = 3608 MiB |
| 目标固件 | EMUI **9.1.0.226**(C00E225R3P1)，Android 9 |
| 交付状态 | 9.1 能实际进入系统；原始 GPT；可再次进入 RAM fastboot |
| 不覆盖 | 其他机型、其他批次固件、其他底包 |

风险与前提：

- 全程清空用户数据，且需要拆机短接；本页不提供数据保留方案。
- 不同批次的 GPT 可能不同。**动手前必须先从自己的固件包解析出分区表并核对尺寸**（见第 5 节），不要照抄本页的数字。
- 本页只记录一次成功与若干次失败；不保证其他设备复现结果相同。

## 1. 三种启动环境与两种锁

这台设备上会同时存在多种"看起来都是 fastboot"的环境，必须先分清，否则很容易把"写入被拒"误判成镜像损坏。

| 本文称呼 | USB ID | 进入方式 | 写入能力 | 锁状态显示 |
|---|---|---|---|---|
| **VCOM / BootROM** | `12d1:3609` | 断电后短接 + 插线 | 只能走 BootROM 协议 | 无 |
| **黑 boot**（RAM fastboot） | `18d1:d00d` | 由 BootROM 协议加载到内存 | 可写（加载的镜像默认跳过 FB 检查） | 两项均显示 `UNLOCKED` |
| **白 boot**（原厂 fastboot） | `18d1:d00d` | 音量下 + 插线；或解锁警告后自动进入 | 受 FB 限制，多数写入被拒 | `FB LOCKED` / `USER UNLOCKED` |
| **LeaOS Recovery** | ADB 设备 | 刷入对应分区后 | `adb sideload` | — |
| **华为 eRecovery** | `12d1:107e` | 启动失败后自动进入 | 无可用 ADB | — |

两个锁是不同维度：

- **USER 锁**：写在 `oeminfo` 里，决定能否启动非官方系统；解锁后持久（见 [解锁章节](02-unlock-userlock.md)）。
- **FB 锁**：fastboot 刷写锁。白 boot 下保持 `LOCKED`，会拒绝 `odm` 等分区写入（`Command not allowed`）；黑 boot 因为加载的是打过补丁的镜像，显示 `UNLOCKED`。

> 不要把黑 boot 的 `UNLOCKED` 当成白 boot 的限制已永久解除。判断"能不能刷"要看**当前是哪种 boot**，而不是只看某一次 `lock-state info` 的输出。

## 2. 材料

| 材料 | 说明 |
|---|---|
| 9.1 完整售后包 | `update_sd_base.zip`、`update_sd_cust_*.zip`、`update_sd_preload_*.zip` 三个文件 |
| 10.0.0.168 完整包 | 回退用，至少保留到 9.1 稳定启动之后 |
| BootROM exploit | `map220v/kirin710_bootrom_exploit`，需按第 3、4 节的容错说明打补丁 |
| fastboot 镜像 | exploit 配套的 `fastbootdec.img`（约 4.67 MB） |
| 主机环境 | Linux、`python3` + `pyserial`、`fastboot` |
| 工具 | 小号十字螺丝刀、镊子、绝缘胶带（拆后盖、断电池、短接） |
| 解包脚本 | 能从 `UPDATE.APP` 取出分区镜像的工具，例如 `HuaweiFirmwareExtractor` 一类脚本 |
| 封装脚本 | 本页提到的 `scripts/unlock.sh`、`tools/hw_extract.py` 属于实验环境的封装，**未随本仓库发布**；按文中说明自行准备等价工具即可 |

## 3. 进入 BootROM（VCOM）

**必须先真正断电。** 电池仍连接时，长按电源 15 秒有时只是重启，BootROM 的传输状态会保留，导致下一步一直失败。

步骤：

1. 拆后盖，断开电池排线，等 10 秒（必要时按住电源键 5 秒放电）。
2. 接回电池排线，此时设备处于关机状态。
3. 镊子一端压住测试点，另一端压住金属屏蔽罩，**保持压住插线，插上瞬间松手**。
4. 判定：

```bash
lsusb | grep 3609          # 12d1:3609  USB SER
ls /dev/ttyUSB*            # ttyUSB0 或 ttyUSB1
```

**失败判据**（exploit 输出）：

| 现象 | 含义 | 处理 |
|---|---|---|
| `Error setting upload address and size. rsp=b''` | 设备完全没回应：不在 BootROM，或已挂起 | 断电重来 |
| `... rsp=b'U'` | `0x55` NAK：上一次传输状态没清干净 | 断电重来 |
| 传输到一半 `rsp=b''` | USB 链路问题 | 换数据线、换直连端口、不要经 hub |
| 端口从 `ttyUSB0` 变成 `ttyUSB1` | 重新枚举 | 脚本应自动扫描，不要写死端口 |

另外：**不要同时开着占用这个 USB 设备的虚拟机**。设备被宿主机和虚拟机争抢时，脚本会"写进去但设备没响应"，现象与 BootROM 异常几乎一样。

## 4. 加载 RAM fastboot（黑 boot）

```bash
# 运行上游 exploit（map220v/kirin710_bootrom_exploit）
# 实验环境的封装为 scripts/unlock.sh，内部调用 exploit_fixed.py；
# 用环境变量指定要加载的 fastboot 镜像
KIRIN_BOOTLOADER=fastboot_unlock3.img python3 exploit_fixed.py
```

> 上游脚本在本机做过三处容错修改，否则大概率失败：自动扫描 `ttyUSB0/ttyUSB1`（端口会变）、ACK 重试、最后一包 NAK 容错。改动细节不属于本仓库范围，但缺了它们很难跑通。

预期输出（关键三行）：

```
/dev/ttyUSB0
Downloaded xloader!
Bootloader downloaded! Main CPU boots...
```

已知容错（本机多次出现，不影响结果）：

- 最后一包常被 NAK（`last packet NAKed (seq=144)`），按"设备要 tail"处理即可；
- 首包可能被拒（见第 3 节表格），断电重来即可。

加载成功后：

```bash
fastboot devices            # 应列出一台设备
fastboot oem lock-state info
```

黑 boot 下两项显示 `UNLOCKED`（因为加载的是跳过 FB 检查的镜像，不代表 `oeminfo` 里的 FB 状态真的被改了）。**这个环境只存在于内存，断电即失效**，每次操作都要重新短接。

## 5. 9.1 固件解包

三个包的分工不同，缺一不可：

| 包 | 内容 |
|---|---|
| `update_sd_base.zip` | `UPDATE.APP`（约 3.4 GB），含 44 个条目：分区表、引导链、kernel、recovery、system/vendor/product/odm/cust/... |
| `update_sd_cust_*.zip` | 其中的 `UPDATE.APP` 含 **`version` 分区**（约 3.4 MB） |
| `update_sd_preload_*.zip` | 其中的 `UPDATE.APP` 含 **`preload` 分区**（约 790 MB） |

**关键点：`version` 和 `preload` 不在 base 包里。** 只刷 base 会得到"能引导、但每次都被踢回 eRecovery"的结果，因为 bootloader 会核对 `version` 与 `vbmeta`、`oeminfo` 的版本是否一致。

解包后先核对本机分区尺寸：

```bash
python3 tools/hw_extract.py <path>/UPDATE.APP -p hisiufs_gpt -o private-work
python3 - <<'PY'
import struct
d=open('private-work/hisiufs_gpt.img','rb').read()
h=d[0x200:0x400]
pl,num,esz=struct.unpack_from('<QII',h,0x48)
for i in range(num):
    e=d[pl*512+i*esz:pl*512+(i+1)*esz]
    if len(e)<128 or e[:16]==b'\0'*16: continue
    s,t=struct.unpack_from('<QQ',e,32)
    print(f"{e[56:128].decode('utf-16le').rstrip(chr(0)):22s}{(t-s+1)*512//1024//1024:8d} MiB")
PY
```

本机实测（AL00a，供对照，**不要照抄**）：

| 分区 | 大小 |
|---|---:|
| system_a | 1896 MiB |
| product_a | 1048 MiB |
| vendor_a | 480 MiB |
| odm_a | 96 MiB |
| cust_a | 88 MiB |
| **preas** | **136 MiB** |
| preavs | 32 MiB |
| version_a | 200 MiB |
| preload_a | 928 MiB |
| userdata | 4096 MiB |

> 这个 `preas = 136 MiB` 是后续第二部分遇到"ROM 声明 936 MiB"问题的根源，务必记录自己设备的实际值。

## 6. 刷写分区

分区表的 fastboot 目标名是 **`ptable`**，不是 `gpt`，也不是包内文件名 `hisiufs_gpt`：

```bash
fastboot flash ptable private-work/hisiufs_gpt.img
```

失败对照：

| 目标名 | 结果 |
|---|---|
| `gpt` | `FAILED (remote: 'partition length get error')` |
| `hisiufs_gpt` | 同上 |
| **`ptable`** | `OKAY` ✅ |

镜像来自两个来源：`base` 包解出的分区，以及从 `cust` / `preload` 两个包里单独解出的 `version.img` 与 `preload.img`。

随后按顺序刷写（每条都必须 `OKAY` 再继续；下面用 `private-work/` 代指解包目录）：

```bash
# 引导链
for n in xloader fastboot trustfirmware hhee teeos fw_lpm3 dts dto \
         isp_firmware vector sensorhub fw_hifi; do
  fastboot flash "$n" private-work/$n.img
done

# kernel / recovery
for n in kernel recovery_ramdisk recovery_vendor recovery_vbmeta \
         erecovery_kernel erecovery_ramdisk erecovery_vendor erecovery_vbmeta \
         eng_vendor eng_system; do
  fastboot flash "$n" private-work/$n.img
done

# 校验与基带
for n in vbmeta modemnvm_update modemnvm_cust modem_fw hisee_img hisee_fs; do
  fastboot flash "$n" private-work/$n.img
done

# 系统分区
for n in preas preavs vendor odm cust system product; do
  fastboot flash "$n" private-work/$n.img
done

# 只存在于 cust / preload 包里的两个分区
fastboot flash version private-work/version.img
fastboot flash preload private-work/preload.img

# 其余
for n in patch cache; do fastboot flash "$n" private-work/$n.img; done
```

说明：

- `fastboot flash ptable` 之后 bootloader 是否立即重读新表**不可靠**。稳妥做法是刷完 `ptable` 先重启一次，再重新短接进入黑 boot 刷其余分区。
- 只要 `ptable` 没有真正改动（刷的是同一份原始表），不重启也可以继续。
- 不要刷 `userdata.img`（那只是个 308 KB 的占位），启动后由系统重建或手动 `erase`。

## 7. 首次启动与数据分区

刷完后 `fastboot reboot`。第一次开机会出现两种情况之一：

1. **正常进入 EMUI 9.1 设置向导**：完成；
2. **进入 eRecovery，提示"数据分区损坏严重"**：说明 `userdata` 仍是 EMUI 10 的加密数据。任选一种处理：
   - eRecovery 里选择**低级格式化数据分区**；或
   - 重新短接进黑 boot：

```bash
fastboot erase userdata
fastboot erase cache
fastboot reboot
```

首次开机可能持续 5–10 分钟，期间不要断电。

验证：

- 设置向导可进入；
- 设置 → 关于手机，版本号应为 `9.1.0.226`；
- 能再次短接进入黑 boot，并执行 `fastboot oem lock-state info`。

## 8. 回退到 EMUI 10

- 材料：`10.0.0.168` 完整包（同样含 `ptable` 与全部分区镜像）。
- 流程与第 6 节相同：先 `ptable`，再引导链，再系统分区。
- **本机没有完整执行过回退**，因此不把这部分写成已验证步骤。回退同样会清数据。

## 9. 未验证与风险

- 不同批次的 GPT 尺寸、`preas` 大小可能不同；本页数字只对本机有效。
- 刷写 `xloader` / `fastboot` 期间若 USB 掉线，设备可能无法正常启动；但 **BootROM 入口不受影响**，短接仍可重新加载 RAM fastboot 继续刷。
- 不要刷"单板软件 / board software"一类的包：会重写 `oeminfo`，串号与锁状态都会丢失。
- 不要在未断电的情况下反复短接；容易得到"有时能进、有时 NAK"的不稳定现象。
- 本页没有记录按键组合的稳定秒数；本机电源键与音量键都正常，但不同设备可能不同。

完成本页后，设备应处于：**EMUI 9.1 正常启动 + 原始 GPT + 可再次进入黑 boot**。下一章：[解锁 USER 锁](02-unlock-userlock.md)；再往后是 [第二部分：LeaOS 安装](03-after-downgrade.md)。
