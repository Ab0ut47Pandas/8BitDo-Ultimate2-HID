; Controller 1.10 startup selector, TC32 disassembly
; Original
   10044:	0b12      	tloadr	r3, [pc, #72]	; (0x10090) ; literal=0x00845fe8
   10046:	581a      	tloadr	r2, [r3, #0]
   10048:	0b12      	tloadr	r3, [pc, #72]	; (0x10094) ; literal=0x00020020
   1004a:	021a      	tnand	r2, r3
   1004c:	c002      	tjeq.n	0x10054
   1004e:	a102      	tmovs	r1, #2
   10050:	0b11      	tloadr	r3, [pc, #68]	; (0x10098) ; literal=0x0084615d
   10052:	4019      	tstorerb	r1, [r3, #0]
   10054:	a384      	tmovs	r3, #132	; 0x84
   10056:	f29b      	tshftls	r3, r3, #10
   10058:	021a      	tnand	r2, r3
   1005a:	c002      	tjeq.n	0x10062
   1005c:	a201      	tmovs	r2, #1
   1005e:	0b0e      	tloadr	r3, [pc, #56]	; (0x10098) ; literal=0x0084615d
   10060:	401a      	tstorerb	r2, [r3, #0]
   10062:	6d30      	tpop	{r4, r5, pc}

; Replacement
   10044:	0812      	tloadr	r0, [pc, #72]	; (0x10090)
   10046:	5800      	tloadr	r0, [r0, #0]
   10048:	a184      	tmovs	r1, #132	; 0x84
   1004a:	f289      	tshftls	r1, r1, #10
   1004c:	0208      	tnand	r0, r1
   1004e:	c001      	tjeq.n	0x10054
   10050:	a200      	tmovs	r2, #0
   10052:	8004      	tj.n	0x1005e
   10054:	a201      	tmovs	r2, #1
   10056:	090f      	tloadr	r1, [pc, #60]	; (0x10094)
   10058:	0208      	tnand	r0, r1
   1005a:	c000      	tjeq.n	0x1005e
   1005c:	a202      	tmovs	r2, #2
   1005e:	0b0e      	tloadr	r3, [pc, #56]	; (0x10098)
   10060:	401a      	tstorerb	r2, [r3, #0]
   10062:	6d30      	tpop	{r4, r5, pc}
