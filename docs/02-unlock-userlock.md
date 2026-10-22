# 第一部分 B：解锁 USER 锁

本页记录在这台 **HRY-AL00a** 上解锁 `USER LockState` 的过程：不申请、不购买 16 位解锁码，而是加载一个**打过补丁的 RAM fastboot**，跳过密码校验，直接调用固件自己的写锁函数。

起点见 [降级章节](01-downgrade-to-emui9.md)：EMUI 9.1 已能启动，且能再次短接进入黑 boot。

## 0. 目标、边界与风险

| 项 | 说明 |
|---|---|
| 目标 | `USER LockState: UNLOCKED`，允许后续启动非官方系统（LeaOS） |
| 不涉及 | 白 boot 的 `FB LockState`；它仍显示 `LOCKED`，这是正常现象 |
| 原理 | 复用固件内部的 `oeminfo_lock_stat_write(1)`，只跳过它前面的密码校验 |
| 风险 | 会写入 `oeminfo`；解锁行为本身通常会触发一次数据清除/警告页 |
| 恢复 | `oeminfo` 可被"单板软件"类包重写，但那会同时丢失串号；不要用它来"恢复原状" |

## 1. 两个锁是不同维度

| | USER 锁 | FB 锁 |
|---|---|---|
| 存在位置 | `oeminfo` | 同一 `oeminfo`，但由 fastboot 读取并强制 |
| 作用 | 能否启动非官方系统 | 是否允许 fastboot 刷写（例如 `odm`） |
| 解锁后 | **持久**，重启、重刷固件都不丢 | 白 boot 仍可能显示 `LOCKED`；黑 boot 显示 `UNLOCKED` |
| 判断方式 | `fastboot oem lock-state info` 的 `USER LockState` | 同一条命令的 `FB LockState`，但必须注明当前是白 boot 还是黑 boot |

实测现象：

- 白 boot（原厂 fastboot）：`FB LOCKED` / `USER UNLOCKED`，写 `odm` 返回 `Command not allowed`；
- 黑 boot（RAM fastboot）：两项都可能显示 `UNLOCKED`，因为运行的镜像本身被改过；
- 解锁过 USER 之后，即使白 boot 仍显示 `FB LOCKED`，USER 也不会回退。

## 2. 定位 `oem unlock` 的处理函数

镜像里带符号表，`fastboot` 的命令分派表位于 `0x3C3A2558`：

```
0x3C3A2558  "oem unlock"  →  0x3C027AA0   usr_fastboot_unlock
0x3C3A2568  "oem relock"  →  0x3C027E14
```

`usr_fastboot_unlock` 的关键片段（节选）：

```asm
3c027b34: bl   0x3c029210      ; 密码校验函数
3c027b38: mov  w22, w0
3c027b3c: cbz  w0, 0x3c027b90  ; 返回 0（校验通过）→ 进入解锁流程
3c027b40: ldr  w0, [x19, #4]   ; 否则失败计数 +1
3c027b58: b.le 0x3c027c30      ; → 打印 "check password failed!"
```

真正的写锁动作在成功路径上：

```asm
3c027bd4: mov  w0, w20         ; w20 = 解锁状态值 1
3c027bd8: bl   0x3c028fe8      ; oeminfo_lock_stat_write(int state)
```

相关符号：

| 符号 | 地址 |
|---|---|
| `usr_fastboot_unlock` | `0x3C027AA0` |
| 密码校验函数 | `0x3C029210` |
| `oeminfo_lock_stat_write` | `0x3C028FE8` |
| `hisi_secboot_set_lockstate` | `0x3C0E05CC`（未使用） |

> 该 fastboot 镜像的**文件偏移 = 运行时地址 − `0x3C000000`**（本版本已核对）。

## 3. 补丁

只替换三条指令，让执行流在校验之后**直接跳到写锁**：

| 地址 | 原指令（机器码 / 字节） | 新指令（机器码 / 字节） | 含义 |
|---|---|---|---|
| `0x3C027B38` | `mov w22, w0` — `0x2A0003F6` / `f6 03 00 2a` | `mov w20, #1` — `0x52800034` / `34 00 80 52` | 状态值 = 1 |
| `0x3C027B3C` | `cbz w0, #0x3C027B90` — `0x340002A0` / `a0 02 00 34` | `mov w25, #0` — `0x52800019` / `19 00 80 52` | 清标志 |
| `0x3C027B40` | `ldr w0, [x19, #4]` — `0xB9400660` / `60 06 40 b9` | `b #0x3C027BD4` — `0x14000025` / `25 00 00 14` | 直接跳到写锁 |

补丁后该处反汇编应为：

```asm
3c027b34: bl   0x3c029210
3c027b38: mov  w20, #1
3c027b3c: mov  w25, #0
3c027b40: b    0x3c027bd4        ; → mov w0, w20 ; bl oeminfo_lock_stat_write
```

为避免手抄出错，直接用脚本生成。**先校验原始镜像的 SHA256**，不匹配就停止：

```python
#!/usr/bin/env python3
# 仅修改本地文件；不访问手机
import hashlib, struct, sys
from pathlib import Path

SOURCE_SHA256 = "4246ae1e37d8ec8e1ac6044ec5c28efab2915244c88c3465485984a7bddb704e"
BASE = 0x3C000000
PATCHES = [
    (0x3C027B38, 0x2A0003F6, 0x52800034),  # mov w22,w0      -> mov w20,#1
    (0x3C027B3C, 0x340002A0, 0x52800019),  # cbz w0,...      -> mov w25,#0
    (0x3C027B40, 0xB9400660, 0x14000025),  # ldr w0,[x19,#4] -> b 0x3C027BD4
]

src, dst = map(Path, sys.argv[1:3])
data = bytearray(src.read_bytes())
if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
    sys.exit("unknown fastboot image; refusing")
for addr, before, after in PATCHES:
    off = addr - BASE
    if struct.unpack_from("<I", data, off)[0] != before:
        sys.exit(f"unexpected bytes at {addr:#x}")
    struct.pack_into("<I", data, off, after)
dst.write_bytes(data)
print("patched:", dst, hashlib.sha256(data).hexdigest())
```

产出镜像的 SHA256（本次实测）应为：

```text
5ed2dcf4f040533436003253d1a33a6457cd49f2ab7f1b77ee2cc6feddd441d7
```

> 表里的 `before` 值请以自己镜像反汇编为准；这里列出的是本机所用镜像的原始机器码。偏移与字节都**绑定该镜像版本**，不能套用到其他 fastboot。

**已排除的两种改法**（本机试过，均无效，留作避免重复尝试）：

- 改 `0x3C027BA0` / `0x3C027BAC` 两处为 `nop`：那是校验**通过之后**的分支，改它不影响密码错误路径；
- 从 `0x3C027B40` 跳到 `0x3C027B90`：会进入等待确认的回调，表现为命令"卡住"。

## 4. 操作步骤

1. 断电（断电池）→ 短接 → 进 VCOM，确认 `12d1:3609`。
2. 用打过补丁的镜像加载 RAM fastboot：

```bash
# 实验环境封装；核心是让 exploit 加载打过补丁的 fastboot 镜像
KIRIN_BOOTLOADER=fastboot_unlock3.img python3 exploit_fixed.py
```

3. 输出里必须出现：

```text
bootloader: fastboot_unlock3.img
Bootloader downloaded! Main CPU boots...
```

4. 执行解锁（密码参数随便填，补丁后不再校验）：

```bash
fastboot oem unlock 0000000000000000
```

5. **按一次电源键。**

   这台设备在 dts 不匹配时屏幕是黑的，看不到"是否解锁"的确认提示，但固件确实在等这个按键。**按下去之后等待几秒**。

6. 验证：

```bash
fastboot oem lock-state info
```

期望：

```text
FB LockState:   UNLOCKED
USER LockState: UNLOCKED
```

7. 再执行一次 `fastboot oem unlock ...`，返回 `FAILED (remote: 'already fastboot unlocked')` 也说明已经解锁。

## 5. 现象与排查

| 现象 | 含义 | 处理 |
|---|---|---|
| 仍报 `check password failed!` | 加载的不是打过补丁的镜像，或补丁偏移不对 | 看 exploit 输出的 `bootloader:` 行 |
| 命令长时间无返回 | 在处理函数里等待按键确认 | 按一次电源键 |
| 第一条返回 `No such device` | 写入后设备立即复位（正常） | 重新 `fastboot devices`，再查锁状态 |
| 第二条返回 `already fastboot unlocked` | 已解锁 | 正常 |
| 命令后信号完全消失 | fastboot 被写坏/挂起 | 断电，短接重新加载；不应影响 `oeminfo` |

## 6. 持久性与风险

- 解锁结果写在 `oeminfo`，**重启、重刷 9.1 都不会丢**（本机实测多次重启与整包重刷后仍为 `UNLOCKED`）；刷回 EMUI 10 后的状态未实测。
- 执行 `fastboot oem relock` 会重新上锁；不要在拿到可用系统前尝试。
- "单板软件 / board software"类包会重写 `oeminfo`，串号与锁状态一起丢失；不要用。
- 解锁后首次启动可能出现华为"设备已解锁，无法信任"警告页，这是正常现象。

## 7. 未验证

- 该补丁是否在 EMUI 10 上同样有效：本机只在 9.1 上成功；EMUI 10 阶段的尝试都在更早的错误改法上失败，没有用最终补丁在 10 上重试。
- 其他 fastboot 镜像版本：偏移和机器码都不同，必须重新反汇编定位。
- 其他批次设备：`oeminfo` 结构一致的可能性高，但没有实测。

完成后进入 [第二部分：LeaOS 安装](03-after-downgrade.md)。
