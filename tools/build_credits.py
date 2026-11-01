"""Translate credit headings; use a bounded UTF-8 decoder at credit-only call sites."""
from pathlib import Path
import hashlib,json,struct
from keystone import Ks,KS_ARCH_PPC,KS_MODE_PPC32,KS_MODE_BIG_ENDIAN
from unicorn import Uc,UC_ARCH_PPC,UC_MODE_PPC32,UC_MODE_BIG_ENDIAN,UC_PROT_ALL
from unicorn.ppc_const import *

ROOT=Path(__file__).resolve().parents[1]
# Zero padding inside the MetroTRK interrupt vector table in text0 (0x80005788-0x80005c54).
# Retail boots never execute or copy it, and loaders/Gecko do not use it (unlike 0x80001800).
ADDRESS=0x800057a0
CAVE=(0x80005788,0x80005c54)
CALLS=[0x80091168,0x80091210,0x80091270,0x800912e4,0x80091344,0x800913ac]
ASM='''
mr 6,4
addi 7,5,-1
loop:
cmpwi 7,0
ble done
lbz 0,0(3)
cmpwi 0,0
beq done
addi 3,3,1
cmplwi 0,0x80
blt store
cmplwi 0,0xe0
bge three
andi. 0,0,0x1f
lbz 8,0(3)
andi. 8,8,0x3f
slwi 0,0,6
or 0,0,8
addi 3,3,1
b store
three:
andi. 0,0,0xf
lbz 8,0(3)
lbz 9,1(3)
andi. 8,8,0x3f
andi. 9,9,0x3f
slwi 0,0,12
slwi 8,8,6
or 0,0,8
or 0,0,9
addi 3,3,2
store:
sth 0,0(6)
addi 6,6,2
addi 7,7,-1
b loop
done:
li 0,0
sth 0,0(6)
blr
'''

def main():
    headings=json.loads((ROOT/'work/translation/credits-headings.json').read_text(encoding='utf-8'))
    rows=json.loads((ROOT/'work/translation/credits-source.json').read_text(encoding='utf-8'))
    out=ROOT/'work/credits-build';out.mkdir(exist_ok=True)
    all_lines=[];translations=[]
    for row in rows:
        lines=row['text'].splitlines();new=[]
        for i,line in enumerate(lines):
            value=headings.get(line,line) if i and lines[i-1] in ('!','$') else line
            if line=='Nintendo of Europe':value=line
            new.append(value)
            if value!=line:translations.append({'file':row['source'],'line':i+1,'source':line,'translation':value})
        assert len(lines)==len(new) and all(len(s)<64 for s in new)
        (out/Path(row['source']).name).write_bytes(('\r\n'.join(new)+'\r\n').encode('utf-8'))
        all_lines.extend(new)
    code=bytes(Ks(KS_ARCH_PPC,KS_MODE_PPC32|KS_MODE_BIG_ENDIAN).asm(ASM,addr=ADDRESS)[0])
    # Execute the actual PPC decoder against every credit line and output guard bytes.
    uc=Uc(UC_ARCH_PPC,UC_MODE_PPC32|UC_MODE_BIG_ENDIAN);uc.mem_map(0x80000000,0x10000,UC_PROT_ALL)
    uc.mem_write(ADDRESS,code)
    for line in set(all_lines):
        for capacity in (1,4,64):
            uc.mem_write(0x80008000,line.encode('utf-8')+b'\0')
            uc.mem_write(0x80009000,b'\xa5'*256)
            uc.reg_write(UC_PPC_REG_3,0x80008000);uc.reg_write(UC_PPC_REG_4,0x80009000);uc.reg_write(UC_PPC_REG_5,capacity)
            uc.reg_write(UC_PPC_REG_LR,0x80002000);uc.emu_start(ADDRESS,0x80002000,count=10000)
            expected=line[:capacity-1].encode('utf-16be')+b'\0\0'
            assert bytes(uc.mem_read(0x80009000,len(expected)))==expected,line
            assert bytes(uc.mem_read(0x80009000+len(expected),8))==b'\xa5'*8
    original=(ROOT/'work/jp/DATA/sys/main.dol').read_bytes();dol=bytearray(original)
    def fileoff(addr,size=4):
        for i in range(7):
            o,a,n=(struct.unpack_from('>I',dol,base+i*4)[0] for base in (0,0x48,0x90))
            if n and a<=addr and addr+size<=a+n:return o+addr-a
        raise AssertionError(hex(addr))
    # The cave must be all zeros in text0 and nothing in the DOL may branch or point into it.
    assert CAVE[0]<=ADDRESS and ADDRESS+len(code)<=CAVE[1]
    cave=fileoff(CAVE[0],CAVE[1]-CAVE[0]);assert dol[cave:cave+CAVE[1]-CAVE[0]]==bytes(CAVE[1]-CAVE[0])
    for i in range(18):
        o,a,n=(struct.unpack_from('>I',dol,base+i*4)[0] for base in (0,0x48,0x90))
        for k in range(0,n,4):
            w=struct.unpack_from('>I',dol,o+k)[0];pc=a+k
            if i<7 and w>>26 in (16,18):
                mask,top=(0xfffc,0x8000) if w>>26==16 else (0x03fffffc,0x02000000)
                d=w&mask;t=(d-2*top if d&top else d)+(0 if w&2 else pc)
                assert not CAVE[0]<=t&0xffffffff<CAVE[1],hex(pc)
            assert not CAVE[0]<=w<CAVE[1],hex(pc)
    for pc in CALLS:
        off=fileoff(pc);old=struct.unpack_from('>I',dol,off)[0]
        assert old==(0x48000001|((0x80123f90-pc)&0x03fffffc)),hex(pc)
        struct.pack_into('>I',dol,off,0x48000001|((ADDRESS-pc)&0x03fffffc))
    off=fileoff(ADDRESS,len(code));dol[off:off+len(code)]=code
    assert len(dol)==len(original)
    (out/'main.dol').write_bytes(dol)
    report={'translated_heading_occurrences':len(translations),'proper_names':'original spelling preserved',
            'encoding':'UTF-8, no BOM','hook_address':hex(ADDRESS),'hook_bytes':len(code),
            'hook_location':'zero padding in MetroTRK vector table (text0), no new DOL section',
            'call_sites':[hex(x) for x in CALLS],'cpu_test_unique_lines':len(set(all_lines)),
            'cpu_test_capacities':[1,4,64],'runtime_verified':False,'changes':translations}
    (ROOT/'manifests/credits-translation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Credits translated:',len(translations),'occurrences. PPC decoder passed',len(set(all_lines))*3,'tests.')

if __name__=='__main__':main()
