"""Read NLG texture records and GX data; never edit source assets."""
from pathlib import Path
from collections import Counter
import struct,json,hashlib,html
from decode_gx import decode,size,palette_rgba
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/jp/DATA/files'
OUT=ROOT/'work/extracted-images';OUT.mkdir(parents=True,exist_ok=True)
FORMATS={0:4,1:5,2:14,3:6,5:1,8:9}
def u32(b,p):return struct.unpack_from('>I',b,p)[0]
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def hashes():
 b=(BASE/'art/hashid.bin').read_bytes();n=u32(b,0);start=4+n*8;out={}
 for i in range(n):
  k,o=struct.unpack_from('>II',b,4+i*8);q=start+o;end=b.index(0,q);out[k]=b[q:end].decode('utf-8')
 return out
def main():
 names=hashes();rows=[];seen={};errors=[];inventory=[]
 def emit(b,w,h,fmt,source,offset,texture_hash=None,pal=None,**extra):
  im=decode(b,w,h,fmt,pal);key=hashlib.sha256(struct.pack('>II',w,h)+im.tobytes()).hexdigest();id=f'G{len(rows)+1:05}'
  if key not in seen:
   dest=OUT/(id+'.png');im.save(dest);seen[key]=dest.relative_to(ROOT).as_posix()
  rows.append(dict(id=id,source=source,width=w,height=h,gx_format=fmt,offset=offset,bytes=len(b),texture_hash=None if texture_hash is None else f'{texture_hash:08x}',name=names.get(texture_hash,''),pixel_sha256=key,image=seen[key],**extra))
 for p in sorted(BASE.rglob('*.dict')):
  d=p.read_bytes();whole=p.with_suffix('.data').read_bytes();assert d[:4]==bytes.fromhex('a9f32458')
  groups=u32(d,8);assert len(d)==12+76*groups
  for group in range(groups):
   desc=12+group*76;groupoff=u32(d,desc);meta=u32(d,desc+8);segments=[struct.unpack_from('>II',d,desc+12+i*8) for i in range(8)]
   groupend=groupoff+sum(v[0] for v in segments)+meta;assert groupend<=len(whole)
   b=whole[groupoff:groupend];cpu=segments[0][0];gpu=cpu+segments[1][0];source=p.with_suffix('.data').relative_to(BASE).as_posix();count=0
   if not meta:continue
   assert meta%12==0
   for i in range(len(b)-meta,len(b)-12,12):
    tag,length,off=struct.unpack_from('>III',b,i)
    if tag!=0x1201b601 or u32(b,i+12)!=0x2501b603:continue
    _,glen,goff=struct.unpack_from('>III',b,i+12);assert length%96==0
    for q in range(cpu+off,cpu+off+length,96):
     k=u32(b,q);w,h=struct.unpack_from('>HH',b,q+4);fmt=u32(b,q+16);pix=gpu+goff+u32(b,q+20);levels=b[q+10]
     try:
      assert 0<w<=4096 and 0<h<=4096;gx=FORMATS[fmt];n=size(w,h,gx);assert gpu+goff<=pix and pix+n<=gpu+goff+glen
      mipbytes=sum(size(max(1,w>>lv),max(1,h>>lv),gx) for lv in range(levels));assert pix+mipbytes<=gpu+goff+glen
      pal=None;po=None
      if gx==9:
       po=gpu+goff+u32(b,q+28);pal=palette_rgba(b[po:po+512],2);assert po+512<=gpu+goff+glen
      emit(b[pix:pix+n],w,h,gx,source,groupoff+pix,k,pal,header_offset=groupoff+q,nlg_format=fmt,mip_levels=levels,mip_bytes=mipbytes,palette_offset=None if po is None else groupoff+po,kind='NLG texture')
      count+=1
     except (AssertionError,ValueError,KeyError) as e:errors.append(dict(source=source,header=groupoff+q,error=str(e),width=w,height=h,nlg_format=fmt))
   inventory.append(dict(source=source,group=group,group_offset=groupoff,texture_count=count,segments=segments,metadata_bytes=meta,first_magic=b[:4].hex()))
 for p in sorted((BASE/'art/fe/fonts').glob('*.res')):
  b=p.read_bytes();n=u32(b,4)
  for i in range(n-1):
   k,units,length=struct.unpack_from('>III',b,32+i*12);off=units*32;v=b[off:off+length];w,h=struct.unpack_from('>HH',v,4)
   assert u32(v,16)==8 and length==96+w*h+512
   emit(v[96:96+w*h],w,h,9,p.relative_to(BASE).as_posix(),off+96,k,palette_rgba(v[-512:],2),kind='font atlas',palette_offset=off+96+w*h)
 for p in sorted(BASE.rglob('*.tpl')):
  b=p.read_bytes();magic,n,table=struct.unpack_from('>III',b);assert magic==0x20af30
  for i in range(n):
   hd,ph=struct.unpack_from('>II',b,table+i*8);h,w,fmt,off=struct.unpack_from('>HHII',b,hd);pal=None
   if ph:
    ncolors=struct.unpack_from('>H',b,ph)[0];pf,po=struct.unpack_from('>II',b,ph+4);pal=palette_rgba(b[po:po+ncolors*2],pf)
   emit(b[off:off+size(w,h,fmt)],w,h,fmt,p.relative_to(BASE).as_posix(),off,pal=pal,kind='TPL',index=i)
 write(ROOT/'manifests/extracted-images.json',dict(images=rows,unique=len(seen),occurrences=len(rows),errors=errors,coverage='NLG texture record pairs, standalone font atlases and loose TPL. FENL, ARC/banner embedded assets and THP video still require separate survey.'))
 write(ROOT/'manifests/nlg-data-inventory.json',inventory)
 write(ROOT/'manifests/hashid-names.json',{f'{k:08x}':v for k,v in names.items()})
 print('Images',len(rows),'unique',len(seen),'errors',len(errors),flush=True)
 print('Errors',errors[:5],flush=True)
 # Internal contact sheets only: do not show all game art as translation targets.
 from PIL import Image,ImageDraw,ImageFont
 candidates=[r for r in rows if r['source'].startswith('art/fe/') and r['kind']!='font atlas']
 unique=list({r['pixel_sha256']:r for r in candidates}.values());sheetroot=ROOT/'work/image-survey';sheetroot.mkdir(exist_ok=True)
 for batch in range(0,len(unique),40):
  sheet=Image.new('RGB',(1200,1000),'#37424b');draw=ImageDraw.Draw(sheet)
  for idx,r in enumerate(unique[batch:batch+40]):
   x=idx%5*240;y=idx//5*125;im=Image.open(ROOT/r['image']).convert('RGBA');im.thumbnail((230,98));sheet.paste(im,(x+(230-im.width)//2,y+18),im)
   draw.text((x+3,y+2),r['id']+' '+r['name'][:29],fill='white')
  sheet.save(sheetroot/f'fe-{batch//40+1:02}.jpg')
 print('Internal FE sheets',len(unique),flush=True)
if __name__=='__main__':main()
