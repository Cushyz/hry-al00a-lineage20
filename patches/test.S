/* Exercise the exact replacement instructions, short-string layout, and the
 * original libc check's cmp/b.hi decision. No host or phone partitions used. */
.text
.global _start
_start:
 adr x20, cases
 mov x21, #0
next:
 adr x19, buffer
 mov x0, x19
 mov w0, #16
 cmp w0, #16
 b.ne fail
 mov x0, x19
 stp xzr, xzr, [x0]
 ldrb w2, [x20], #1
 mov w3, #16
 cmp x2, x3
 b.hi rejected
 mov x4, #0
copy:
 cmp x4, x2
 b.eq copied
 ldrb w5, [x20, x4]
 strb w5, [x19, x4]
 add x4, x4, #1
 b copy
copied:
 adr x22, sso
 stp xzr, xzr, [x22]
 str xzr, [x22, #16]
 mov w9, #32
 ldr q1, [x19]
 strb w9, [x22]
 stur q1, [x22, #1]
 ldrb w5, [x22]
 cmp w5, #32
 b.ne fail
 ldrb w5, [x22, #17]
 cbnz w5, fail
 mov x4, #0
check:
 cmp x4, x2
 b.eq checked
 add x6, x22, #1
 ldrb w5, [x6, x4]
 ldrb w7, [x20, x4]
 cmp w5, w7
 b.ne fail
 add x4, x4, #1
 b check
checked:
 cmp x2, #16
 b.eq advance
 add x6, x22, #1
 ldrb w5, [x6, x2]
 cbnz w5, fail
 b advance
rejected:
 cmp x2, #17
 b.ne fail
advance:
 add x20, x20, x2
 add x21, x21, #1
 cmp x21, #5
 b.lt next
 mov x0, #0
 b exit
fail:
 mov x0, #1
exit:
 mov x8, #93
 svc #0
.data
cases:
.byte 8
.ascii "HRY-LX1x"
.byte 9
.ascii "HRY-AL00a"
.byte 0
.byte 16
.ascii "1234567890abcdef"
.byte 17
.ascii "1234567890abcdefg"
.balign 16
buffer: .skip 32
sso: .skip 32
