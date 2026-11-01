"""Pack localized resources into an isolated extracted Wii game tree."""
from pathlib import Path
import collections,csv,hashlib,io,json,shutil,struct
import numpy as np
from PIL import Image
from inspect_editions import parse_loc
from extract_system_assets import u8,lz10
from decode_gx import decode,size
from gxenc import encode

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/jp/DATA'
OUT=ROOT/'work/patched/DATA'

def u32(b,o):return struct.unpack_from('>I',b,o)[0]

def repack_u8(b,replace):
    root=u32(b,4);count=u32(b,root+8);data_start=u32(b,12)
    result=bytearray(b[:data_start]);files=list(u8(b));by_offset={off:(name,raw) for name,off,raw in files}
    for i in range(count):
        n=root+i*12;flags,off,length=struct.unpack_from('>III',b,n)
        if flags>>24:continue
        name,raw=by_offset[off];raw=replace.get(name,raw)
        result.extend(bytes((-len(result))%32));off=len(result)
        result.extend(raw);struct.pack_into('>II',result,n+4,off,len(raw))
    assert {name:raw for name,_,raw in u8(result)}=={name:replace.get(name,raw) for name,_,raw in files}
    return bytes(result)

def wrap(raw):
    return b'IMD5'+struct.pack('>I',len(raw))+bytes(8)+hashlib.md5(raw).digest()+raw

def compress_lz(raw):
    """LZ10 like the original banner: distance >= 2, stream padded to 4 bytes."""
    result=bytearray(b'LZ77\x10'+len(raw).to_bytes(3,'little'));chains={};i=0;n=len(raw)
    while i<n:
        flagpos=len(result);result.append(0)
        for bit in range(8):
            if i>=n:break
            best=dist=0
            for j in reversed(chains.get(raw[i:i+3],())):
                d=i-j
                if d>4096:break
                if d<2:continue
                l=3
                while l<18 and i+l<n and raw[j+l]==raw[i+l]:l+=1
                if l>best:best,dist=l,d
                if l==18:break
            if best>=3:
                result[flagpos]|=0x80>>bit;result.extend((((best-3)<<4)|((dist-1)>>8),(dist-1)&0xff));step=best
            else:result.append(raw[i]);step=1
            for k in range(i,min(i+step,n-2)):chains.setdefault(raw[k:k+3],[]).append(k)
            i+=step
    result.extend(bytes((-len(result))%4))
    assert lz10(result[4:])==raw
    return bytes(result)

def patch_tpl(raw,image):
    hd=u32(raw,12);h,w,fmt,off=struct.unpack_from('>HHII',raw,hd)
    assert image.size==(w,h)
    payload=encode(image,{0:'I4',5:'RGB5A3',14:'CMPR'}[fmt]);assert len(payload)==size(w,h,fmt)
    result=bytearray(raw);result[off:off+len(payload)]=payload
    return bytes(result)

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if not OUT.exists():
        print('Copying original DATA tree into isolated build workspace',flush=True)
        shutil.copytree(BASE,OUT)
    changes=[]
    def save(name,raw):
        dest=OUT/'files'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        changes.append({'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    rows=json.loads((ROOT/'work/translation/translated-texts.json').read_text(encoding='utf-8'))
    raw=(BASE/'files/art/fe/japanese.loc').read_bytes();n=len(rows);pool=bytearray();table=bytearray()
    for r in sorted(rows,key=lambda r:r['hash']):
        assert r['translation'] is not None
        table.extend(struct.pack('>II',int(r['hash'],16),len(pool)//2));pool.extend(r['translation'].encode('utf-16be')+b'\0\0')
    patched=raw[:20]+table+pool
    back=parse_loc(patched);assert [e['text'] for e in back['entries']]==[r['translation'] for r in sorted(rows,key=lambda r:r['hash'])]
    save('art/fe/japanese.loc',patched)
    for p in (ROOT/'work/font-build').glob('*.res'):save('art/fe/fonts/'+p.name,p.read_bytes())
    # Credits stay English as in the Japanese edition, so main.dol needs no decoder hook.
    # Restore originals in case an older build left translated credits or a hooked DOL here.
    for rel in ('files/art/fe/credits/credits.txt','files/art/fe/credits/credits_full.txt','sys/main.dol'):
        shutil.copy2(BASE/rel,OUT/rel)
    # Videos with the Korean logo subtitle (tools/build_logo_videos.py).
    for p in sorted((ROOT/'work/video-build').glob('*.thp')):save('art/movies/'+p.name,p.read_bytes())
    # Preserve the original UTF-16BE TSV byte layout, replacing only the first cell.
    for p in (BASE/'files/HomeButton2').glob('*.csv'):
        text=p.read_bytes().decode('utf-16');table=list(csv.reader(io.StringIO(text),delimiter='\t',skipinitialspace=True))
        for row in table:
            assert len(row)==10
            original='"'+row[0]+'"';replacement='"'+row[9]+'"';assert text.count(original)==1
            text=text.replace(original,replacement,1)
        new=b'\xfe\xff'+text.encode('utf-16be');back=list(csv.reader(io.StringIO(new.decode('utf-16')),delimiter='\t',skipinitialspace=True))
        assert all(b[0]==a[9] and b[1:]==a[1:] for a,b in zip(table,back))
        save('HomeButton2/'+p.name,new)
    targets=json.loads((ROOT/'manifests/image-translation-targets.json').read_text(encoding='utf-8'))['targets']
    mainimages=json.loads((ROOT/'manifests/extracted-images.json').read_text(encoding='utf-8'))['images'];byid={r['id']:r for r in mainimages}
    modified={};home={};banner={};verification=[]
    for row in targets:
        image=Image.open(ROOT/f"work/image-edits/{row['id']}.png").convert('RGBA')
        if row['category']=='HOME 메뉴':
            rel=row['source'].split('::')[1];home[rel]=(ROOT/'work/reused-home'/rel).read_bytes()
        elif row['id'].startswith('S'):
            _,binpath,tplpath=row['source'].split('::');banner.setdefault(binpath,{})[tplpath]=image
        else:
            for occ in row['occurrences']:
                r=byid[occ['id']];name=r['source'];raw=modified.setdefault(name,bytearray((BASE/'files'/name).read_bytes()))
                pos=r['offset'];fmt=r['gx_format'];levels=r.get('mip_levels',1)
                for lv in range(levels):
                    w,h=max(1,r['width']>>lv),max(1,r['height']>>lv)
                    im=image.resize((w,h),Image.Resampling.LANCZOS) if lv else image
                    payload=encode(im,{0:'I4',5:'RGB5A3',14:'CMPR'}[fmt]);assert len(payload)==size(w,h,fmt)
                    if not lv and fmt==14 and row['id'] in ('G03167','G03184'):
                        old=decode(bytes(raw[pos:pos+len(payload)]),w,h,fmt)
                        changed=np.any(np.asarray(old)!=np.asarray(im),axis=2).reshape(h//8,8,w//8,8).any(axis=(1,3)).reshape(-1)
                        packed=np.frombuffer(payload,np.uint8).reshape(-1,32).copy();original=np.frombuffer(bytes(raw[pos:pos+len(payload)]),np.uint8).reshape(-1,32)
                        packed[~changed]=original[~changed];payload=packed.tobytes()
                    raw[pos:pos+len(payload)]=payload
                    if lv==0:
                        decoded=decode(payload,w,h,fmt);p=ROOT/'work/encoded-images'/f"{occ['id']}.png";p.parent.mkdir(exist_ok=True);decoded.save(p)
                    pos+=len(payload)
                assert pos-r['offset']==r.get('mip_bytes',r['bytes'])
                verification.append({'id':occ['id'],'file':name,'offset':r['offset'],'mips':levels,'size_unchanged':len(raw)==(BASE/'files'/name).stat().st_size})
    for name,raw in modified.items():save(name,raw)
    fontrel='arc/font/RevoIpl_UtrilloProGrecoStd_M_32_I4.brfnt';home[fontrel]=(ROOT/'work/reused-home'/fontrel).read_bytes()
    original=(BASE/'files/HomeButton2/homeBtn.arc').read_bytes();save('HomeButton2/homeBtn.arc',repack_u8(original,home))
    original=(BASE/'files/opening.bnr').read_bytes();start=original.index(b'U\xaa8-');outer=dict((p,b) for p,_,b in u8(original[start:]));newbins={}
    for name,images in banner.items():
        b=outer[name];assert b[:4]==b'IMD5' and b[16:32]==hashlib.md5(b[32:]).digest();content=b[32:]
        compressed=content[:4]==b'LZ77';arc=lz10(content[4:]) if compressed else content
        members=dict((p,b) for p,_,b in u8(arc));replaced={p:patch_tpl(members[p],im) for p,im in images.items()}
        arc=repack_u8(arc,replaced);newbins[name]=wrap(compress_lz(arc) if compressed else arc)
    prefix=bytearray(original[:start]);imet=prefix.find(b'IMET')
    # IMET stores uncompressed archive sizes (without IMD5/LZ wrapper).
    if imet>=0:
        for i,name in enumerate(('meta/icon.bin','meta/banner.bin','meta/sound.bin')):
            b=newbins.get(name,outer[name])[32:]
            unpacked=lz10(b[4:]) if b[:4]==b'LZ77' else b
            struct.pack_into('>I',prefix,imet+12+i*4,len(unpacked))
        # Wii menu channel name: ten language slots of 0x54 bytes (UTF-16BE) right after the sizes.
        for i in range(10):
            prefix[imet+0x1c+i*0x54:imet+0x1c+(i+1)*0x54]='펀치아웃!!'.encode('utf-16-be').ljust(0x54,b'\0')
        prefix[imet+0x5b0:imet+0x5c0]=bytes(16)
        # Wii IMET checksum covers the 0x600-byte block starting 0x40 before magic.
        region=imet-0x40
        prefix[region+0x5f0:region+0x600]=hashlib.md5(prefix[region:region+0x600]).digest()
    save('opening.bnr',bytes(prefix)+repack_u8(original[start:],newbins))
    report={'changes':changes,'image_writes':verification,'nloc_roundtrip':True,'originals_modified':False,'runtime_verified':False}
    (ROOT/'manifests/patch-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Packed',len(changes),'files;',len(verification),'main texture occurrences',flush=True)

if __name__=='__main__':main()
