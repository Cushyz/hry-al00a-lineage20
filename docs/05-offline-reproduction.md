# 离线复现：容量改包与 init 文件补丁

所有公开脚本仅操作电脑上的文件，不调用 adb/fastboot，不写手机。执行位置均为本仓库根目录。容量适配 ZIP 与 init 文件补丁是**两个独立产物**，本页不提供完整通用刷机链。

## 1. 输入与依赖

自行从原作者渠道获得 `LeaOS-OSS-20.0-20260815-harry.zip`，放在仓库根目录；该文件被 Git 忽略。

测试输入 SHA256：

```text
9958ee9b21517538cbb42d7f1c79e96fb4449173945594d574516175ec17a81a
```

这里是本地测试文件的固定标识，不是独立验证的发行者签名。脚本拒绝不同文件，不按“相近版本”继续处理。

依赖：Python 3.11+、brotli、e2fsck、resize2fs、dumpe2fs、debugfs、lpmake、lpdump。后两项来自 AOSP liblp 工具，需使用兼容本例 LP 10.0 的构建；不要把名称相同但来源不明的可执行文件混入 PATH。没有在新机器上验证自动安装依赖的流程。

构建使用 Python assert 做大量格式校验，**不要使用 `python -O` 或设置 PYTHONOPTIMIZE**；发布版入口也会拒绝优化模式。普通用户即可运行，无需 sudo 或挂载文件系统。

## 2. 构建容量适配包

```bash
python3 al00-leaos-lab/scripts/build.py
python3 al00-leaos-lab/scripts/verify_product.py
```

第二步比较缩容前后文件与 inode 属性，必须成功。脚本来自现场离线构建版本，发布时增加了输入哈希和禁用优化模式的限制；没有改变缩容、LP 生成或 OTA 载荷算法。

主要输出：

```text
al00-leaos-lab/output/LeaOS-OSS-20.0-20260815-harry-AL00-EXPERIMENTAL-UNSIGNED.zip
al00-leaos-lab/output/unsparse_super_empty-al00.img
al00-leaos-lab/output/SHA256SUMS
al00-leaos-lab/reports/build-report.json
al00-leaos-lab/reports/product-integrity.json
```

`work/`、`inputs/`、`output/`、`reports/` 都被忽略，重跑会覆盖相应实验产物，请在独立工作副本中执行。报告的 OFFLINE 状态描述该次构建本身；历史真机结果见验证章节，不应靠改报告状态伪造当前真机测试。

脚本将 product.new.dat.br 解压并按 transfer list 恢复，e2fsck 检查，resize2fs 缩容，重新生成全量 new 块指令及 Brotli，再还原比较；没有依赖原分区的旧块内容。其余 ZIP 条目逐项比对，检查 LP geometry/header/tables 的哈希以及 extent 边界。

不同 e2fsprogs 等工具版本可能使输出字节变化；历史输出哈希见证据清单，用于比对，不能替代重新验证。原现场还单独比较了原厂 GPT、设备布局和 GApps 安装器；这些设备相关校验没有被离线构建脚本自动代办。

## 3. 生成 init 补丁文件

容量构建已还原出原 system 镜像后：

```bash
mkdir -p private-work
debugfs -R 'dump /system/bin/init private-work/init.original' \
  al00-leaos-lab/work/system-original.img
python3 scripts/patch-init.py private-work/init.original private-work/init.patched
```

必须得到文档中的修复后 SHA256。生成器只允许完全匹配的原始文件，不覆盖已有输出，不自动寻找设备，不改 system 镜像或 ZIP。

若仅分析 init，无需先完整重建容量包，只要自行从相同 ROM 得到匹配的原文件即可。

可选复核六条指令及局部测试（需要 clang、LLD、llvm-objcopy、qemu-aarch64）：

```bash
clang --target=aarch64-linux-gnu -c patches/changes.S -o private-work/changes.o
llvm-objcopy -O binary --only-section=.text private-work/changes.o private-work/changes.bin
clang --target=aarch64-linux-gnu -nostdlib -static -fuse-ld=lld \
  -Wl,-e,_start patches/test.S -o private-work/model-test
qemu-aarch64 private-work/model-test
```

本仓库不分发 init、补丁块或系统镜像的二进制。以上普通文件产物不能直接用 fastboot flash，更不能替换 kernel。

## 4. 手机侧仍需完成的工作

离线重建、已验证的容量适配安装、设备特定的 init 应用、GApps 安装和真机验收不是同一件事。第 3 项目前仍需具备 LP/ext4 分析能力的人逐台验证。没有这个步骤的可审查方案时，应停在离线复现，不把本文当成新手可全程复制的教程。
