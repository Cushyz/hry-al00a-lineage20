.text
.global changes
changes:
mov w0, #16
stp xzr, xzr, [x0]
mov w3, #16
mov w9, #32
ldr q1, [x19]
stur q1, [x22, #1]
