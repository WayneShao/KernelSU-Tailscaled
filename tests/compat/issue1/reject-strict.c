// Test-only launcher: reject only NETLINK_GET_STRICT_CHK, not all netlink.
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/audit.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    const char *value = getenv("KST_NETLINK_ERRNO");
    unsigned int fault = value ? (unsigned int)atoi(value) : ENOPROTOOPT;
    if (fault != ENOPROTOOPT && fault != EOPNOTSUPP && fault != EPERM) return 2;
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD+BPF_W+BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP+BPF_JEQ+BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET+BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD+BPF_W+BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP+BPF_JEQ+BPF_K, __NR_setsockopt, 0, 5),
        BPF_STMT(BPF_LD+BPF_W+BPF_ABS, offsetof(struct seccomp_data, args[1])),
        BPF_JUMP(BPF_JMP+BPF_JEQ+BPF_K, 270 /* SOL_NETLINK */, 0, 3),
        BPF_STMT(BPF_LD+BPF_W+BPF_ABS, offsetof(struct seccomp_data, args[2])),
        BPF_JUMP(BPF_JMP+BPF_JEQ+BPF_K, 12 /* GET_STRICT_CHK */, 0, 1),
        BPF_STMT(BPF_RET+BPF_K, SECCOMP_RET_ERRNO | fault),
        BPF_STMT(BPF_RET+BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {sizeof(filter)/sizeof(filter[0]), filter};
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program)) {
        perror("seccomp"); return 2;
    }
    execvp(argv[1], argv+1); perror("exec"); return 2;
}
