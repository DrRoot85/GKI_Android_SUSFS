#!/usr/bin/env python3
"""为原生 KernelSU (tiann/KernelSU) 添加 SUSFS 支持。

tiann/KernelSU 结构可能随提交而变化：
- kernel/core/init.c: 包含 kernelsu_init() 函数
- kernel/Kconfig: 菜单定义
- kernel/Kbuild: 编译单元

simonpunk/susfs4ksu 的补丁针对 flat kernel/ksu.c，与 tiann/KernelSU 结构不匹配，
故直接修改源码。如果无法自动集成，则返回非零退出码以便上层回退到手工 sed。
"""

import sys
from pathlib import Path

KSU_KERNEL = Path("KernelSU/kernel")


def modify_kconfig():
    """在 Kconfig 中添加完整的 KSU_SUSFS 菜单"""
    kconfig = KSU_KERNEL / "Kconfig"
    if not kconfig.exists():
        print(f"WARNING: {kconfig} not found, skipping SUSFS menu for KernelSU", file=sys.stderr)
        return False
    s = kconfig.read_text(encoding="utf-8")
    if "config KSU_SUSFS" in s:
        print("Kconfig: SUSFS menu already present")
        return True
    marker = "endmenu\n"
    insertion = (
        'menu "KernelSU - SUSFS"\n'
        'config KSU_SUSFS\n'
        '\tbool "KernelSU addon - SUSFS"\n'
        '\tdepends on KSU\n'
        '\tdefault y\n'
        '\thelp\n'
        '\t  Patch and Enable SUSFS to kernel with KernelSU\n'
        '\n'
        'config KSU_SUSFS_SUS_PATH\n'
        '\tbool "Enable to hide suspicious path"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_SUS_MOUNT\n'
        '\tbool "Enable to hide suspicious mounts"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_SUS_KSTAT\n'
        '\tbool "Enable to spoof suspicious kstat"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_SPOOF_UNAME\n'
        '\tbool "Enable to spoof uname"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_ENABLE_LOG\n'
        '\tbool "Enable logging susfs log to kernel"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS\n'
        '\tbool "Hide KSU SUSFS symbols"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n'
        '\tbool "Spoof cmdline or bootconfig"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_SUS_MAP\n'
        '\tbool "Enable SUS_MAP"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_OPEN_REDIRECT\n'
        '\tbool "Enable open redirect"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        '\n'
        'config KSU_SUSFS_PRIORITY_UID_FILTER\n'
        '\tbool "Enable priority UID filter"\n'
        '\tdepends on KSU_SUSFS\n'
        '\tdefault y\n'
        'endmenu\n'
    )
    idx = s.find(marker)
    if idx < 0:
        # 尝试其他 endmenu 变体
        for m in ("endmenu\r\n", "endmenu"):
            idx = s.find(m)
            if idx >= 0:
                break
        if idx < 0:
            print("WARNING: endmenu not found in Kconfig, skipping SUSFS menu", file=sys.stderr)
            return False
    s = s[:idx] + insertion + s[idx:]
    kconfig.write_text(s, encoding="utf-8")
    print("Kconfig: SUSFS menu added with all config options")
    return True


def modify_init_c():
    """在 init.c 中添加 SUSFS 支持"""
    init_c = KSU_KERNEL / "core" / "init.c"
    if not init_c.exists():
        print(f"ERROR: {init_c} not found, cannot integrate SUSFS for KernelSU", file=sys.stderr)
        return False
    s = init_c.read_text(encoding="utf-8")
    changed = False

    # 步骤1：添加 #include <linux/susfs.h>
    # 尝试多个可能的调度头文件锚点
    include_added = False
    for marker in ("#include <linux/sched.h>", "#include <linux/sched/task.h>",
                   "#include <linux/sched/signal.h>", "#include <linux/sched/wake_q.h>"):
        if "#include <linux/susfs.h>" in s:
            include_added = True
            break
        if marker in s:
            s = s.replace(marker, marker + "\n#include <linux/susfs.h>", 1)
            include_added = True
            print(f"init.c: 添加 #include <linux/susfs.h> 在 {marker} 之后")
            changed = True
            break
    if not include_added and "#include <linux/susfs.h>" not in s:
        print("WARNING: 未找到适合的调度头文件锚点，跳过 #include <linux/susfs.h> 插入", file=sys.stderr)

    # 步骤2：移除 ksu_syscall_hook_manager_init() / ksu_syscall_hook_init()
    for hook_call in ("ksu_syscall_hook_manager_init();", "ksu_syscall_hook_init();",
                      "ksu_syscall_hook_manager_init ();", "ksu_syscall_hook_init ();"):
        count_before = s.count(hook_call)
        if count_before > 0:
            replacement = (
                "#if defined(CONFIG_KSU_SUSFS)\n"
                "    susfs_init();\n"
                "    #endif"
            )
            s = s.replace(hook_call, replacement)
            print(f"init.c: 替换 {count_before} 处 {hook_call}", file=sys.stderr)
            changed = True

    # 步骤3：如果仍未找到 susfs_init()，在 kernelsu_init() 函数体内插入
    if "susfs_init()" not in s:
        # 尝试多个函数名模式
        func_found = False
        for func_pattern in ("kernelsu_init(", "ksu_init(", "init_kernelsu("):
            idx = s.find(func_pattern)
            if idx >= 0:
                func_found = True
                ret_idx = s.find("return 0;", idx)
                if ret_idx >= 0:
                    insertion = (
                        "\n    #ifdef CONFIG_KSU_SUSFS\n"
                        "    susfs_init();\n"
                        "    #endif\n"
                    )
                    s = s[:ret_idx] + insertion + s[ret_idx:]
                    changed = True
                    print("init.c: 在 kernelsu_init() 中插入 susfs_init()", file=sys.stderr)
                else:
                    print("WARNING: 未找到 kernelsu_init() 中的 return 0;，跳过 susfs_init() 插入", file=sys.stderr)
                break
        if not func_found:
            print("WARNING: 未找到 kernelsu_init() 函数，跳过 susfs_init() 插入", file=sys.stderr)

    if changed:
        init_c.write_text(s, encoding="utf-8")
        print("init.c: SUSFS support added")
        return True
    elif "susfs_init()" in s and "#include <linux/susfs.h>" in s:
        print("init.c: SUSFS support already present")
        return True
    else:
        print("init.c: SUSFS support could not be added", file=sys.stderr)
        return False


def modify_kbuild():
    """在 Kbuild 中移除旧 hook 编译单元"""
    kbuild = KSU_KERNEL / "Kbuild"
    if not kbuild.exists():
        print(f"WARNING: {kbuild} not found, skipping Kbuild cleanup", file=sys.stderr)
        return True
    s = kbuild.read_text(encoding="utf-8")
    changed = False
    # 与 upstream 10_enable_susfs_for_ksu.patch 保持一致：移除所有
    # 与 SUSFS 冲突的 hook 编译单元，包括顶层和 ifeq 块内的 arch-specific 行
    for obj in (
        "kernelsu-objs += hook/lsm_hook.o",
        "kernelsu-objs += hook/syscall_event_bridge.o",
        "kernelsu-objs += hook/syscall_hook_manager.o",
        "kernelsu-objs += hook/tp_marker.o",
        "kernelsu-objs += hook/arm64/patch_memory.o",
        "kernelsu-objs += hook/arm64/syscall_hook.o",
        "kernelsu-objs += hook/x86_64/patch_memory.o",
        "kernelsu-objs += hook/x86_64/syscall_hook.o",
        "kernelsu-objs += hook/riscv64/patch_memory.o",
        "kernelsu-objs += hook/riscv64/syscall_hook.o",
    ):
        count = s.count(obj)
        if count > 0:
            s = s.replace(obj + "\n", "", count)
            changed = True
    if changed:
        kbuild.write_text(s, encoding="utf-8")
        print("Kbuild: old hook objects removed")
    else:
        print("Kbuild: no old hook objects found")
    return True


def main():
    kconfig_ok = modify_kconfig()
    init_ok = modify_init_c()
    kbuild_ok = modify_kbuild()

    # init.c 是关键：没有 susfs_init() 就没有 SUSFS
    if not init_ok:
        print("ERROR: 无法在 KernelSU init.c 中集成 SUSFS，构建将中断", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
