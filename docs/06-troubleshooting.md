# 现象与排查

| 现象 | 本次结论和下一步 |
|---|---|
| 白 boot：USER UNLOCKED，但 FB LOCKED | 两种锁状态不同。黑 boot 的显示不证明白 boot 限制被永久解除 |
| wipe-super 在 odm 报 Command not allowed | 权限问题，之前的载体可能已写入；不是只靠修正 preas 大小就能解决 |
| preas expected 981467136, got 142606336 | 原 LP 声明与本台物理容量不匹配，核对 adapted metadata 和 ROM |
| 原布局、只刷三个引导/Recovery 分区能进入 Recovery | 不代表 system/vendor/product 等 ROM 载荷已安装；这三个分区不是完整系统 |
| kernel partition size: 0 / skip copying AVB footer | 本次相同提示后刷写成功；按实际写入、回读和启动判断，不把提示本身判为损坏 |
| reboot recovery 返回 OKAY，却到白 boot/eRecovery | OKAY 只证明命令接受，确认实际屏幕和 ADB 状态；不认定按键损坏 |
| eRecovery 显示联网修复等五个按钮、ADB 无设备 | 本次不是 LeaOS Recovery；不要在那里执行 sideload 指南或自动联网恢复 |
| 橙色警告页、自动继续后重启 | 本次最后定位到 init 机型解析；警告页本身不足以证明 AVB、GPT 或 kernel 出错 |
| sideload Total xfer: 0.97x | 传输比值不是安装结果；看手机最终状态并保存 recovery.log |
| 签名错误但最后 status 0 | 本次对已核验包允许继续；仍需确认载荷及启动，不推广到未知包 |
| 没有 /dev/block/mapper/system | Recovery 可能尚未创建映射，本次 Advanced → Mount /system 后可读；不要凭空假设 dm 编号 |
| adb exec-out 读取块设备多出尾部字符 | 远端 dd 的 stderr 可能进入原始数据；在远端使用 `2>/dev/null` 并严格检查字节数 |
| pstore 最后是 Recovery 的日志 | 中间进过 eRecovery/Recovery 会影响可见记录；标明日志所属启动，不能拿它直接解释正常启动失败 |
| 中国移动最初显示无 SIM | 后续单卡识别及通话成功；先区分 ABSENT、无服务、旧日志和热插拔状态 |
| 交换两卡后只有一张可用 | 本次只观察到一个逻辑电话可用，未确认是配置、驱动还是其他原因，不声称两卡槽均支持 |

## 只读日志采集示例

先确认是 LeaOS Recovery，退出 sideload 回主菜单。在仅连接目标手机的情况下：

```bash
mkdir -p private-reports
adb devices
adb pull /tmp/recovery.log private-reports/recovery.log
adb pull /sys/fs/pstore private-reports/pstore
adb shell dmesg > private-reports/recovery-dmesg.txt
adb shell 'lpdump /dev/block/by-name/system' > private-reports/lpdump.txt
adb shell 'ls -l /dev/block/by-name; cat /proc/partitions' > private-reports/partitions.txt
```

命令不保证每个环境都提供对应文件或工具；缺少日志不等于没有故障。不要为了日志擅自刷入旧诊断 kernel。以上目录默认不会被本仓库 Git 跟踪，分享前仍需脱敏。

## 旧交接记录中已更正的结论

- 本台电源键、音量键正常。
- 不能将 RAM fastboot 的 FB 解锁状态等同于原厂永久解除 FB 限制，也不把 FB 和 FRP 混称。
- 改 GPT 后启动失败不等于已证明 bootloader 有特殊 GPT 校验。本次成功路径没有改 GPT，因此也没有解决或验证那个假设。
- LP geometry 魔数 `gDla` 是 AOSP 格式，不是华为独有格式。
- “原包可以完成 sideload”不代表“国行 init 可以正常启动”。
- 早期报告中的“未真机测试”是当时状态；最终验证需结合后来的回读与启动结果，不能直接复制旧状态作为最新结论。
