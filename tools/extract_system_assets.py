"""Unpack U8/banner assets, system CSV text and THP inventory."""
from pathlib import Path
import struct,json,csv,io,hashlib,re
from decode_gx import decode,size,palette_rgba
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'work/jp/DATA/files';OUT=ROOT/'work/system-assets'
def u32(b,p):return struct.unpack_from('>I',b,p)[0]
def write(p,j):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n','utf-8')
def u8(b):
 assert b[:4]==b'U\xaa8-';root=u32(b,4);count=u32(b,root+8);names=root+count*12;stack=[]
 for i in range(count):
  flags,off,length=struct.unpack_from('>III',b,root+i*12);n=names+(flags&0xffffff);name=b[n:b.index(0,n)].decode('utf-8')
  while stack and i>=stack[-1][0]:stack.pop()
  path='/'.join([s[1] for s in stack if s[1]]+[name])
  if flags>>24:stack.append((length,name))
  else:
   assert off+length<=len(b);yield path,off,b[off:off+length]
def lz10(b):
 assert b[0]==0x10;length=int.from_bytes(b[1:4],'little');p=4;out=bytearray()
 while len(out)<length:
  flags=b[p];p+=1
  for i in range(8):
   if len(out)>=length:break
   if flags&(128>>i):
    v=int.from_bytes(b[p:p+2],'big');p+=2;num=(v>>12)+3;dist=(v&4095)+1
    for _ in range(num):out.append(out[-dist])
   else:out.append(b[p]);p+=1
 return bytes(out[:length])
def main():
 files=[];images=[];errors=[];seen={};fonts=[]
 def handle(b,source,depth=0):
  if b[:4]==b'IMD5':b=b[32:]
  if b[:4]==b'LZ77':b=lz10(b[4:])
  start=b.find(b'U\xaa8-')
  if 0<=start<=0x640:
   for name,off,data in u8(b[start:]):handle(data,source+'::'+name,depth+1)
   return
  dest=OUT/'unpacked'/Path(source.replace('::','/'));dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
  files.append(dict(source=source,bytes=len(b),file=dest.relative_to(ROOT).as_posix(),magic=b[:4].hex()))
  if b[:4]==b'RFNT':fonts.append(source)
  if b[:4]!=bytes.fromhex('0020af30'):return
  n=u32(b,4);table=u32(b,8)
  for i in range(n):
   header,palheader=struct.unpack_from('>II',b,table+i*8);h,w,fmt,off=struct.unpack_from('>HHII',b,header);pal=None
   if palheader:
    nc=struct.unpack_from('>H',b,palheader)[0];pf,po=struct.unpack_from('>II',b,palheader+4);pal=palette_rgba(b[po:po+nc*2],pf)
   im=decode(b[off:off+size(w,h,fmt)],w,h,fmt,pal);key=hashlib.sha256(struct.pack('>II',w,h)+im.tobytes()).hexdigest();id=f'S{len(images)+1:04}'
   if key not in seen:
    p=OUT/'images'/(id+'.png');p.parent.mkdir(exist_ok=True);im.save(p);seen[key]=p.relative_to(ROOT).as_posix()
   images.append(dict(id=id,source=source,index=i,width=w,height=h,format=fmt,image=seen[key],pixel_sha256=key))
 for p in sorted(BASE.rglob('*.arc')):
  b=p.read_bytes()
  if b[:4]!=b'U\xaa8-':
   errors.append(dict(file=p.relative_to(BASE).as_posix(),reason='Not U8; requires separate format inspection'));continue
  handle(b,p.relative_to(BASE).as_posix())
 handle((BASE/'opening.bnr').read_bytes(),'opening.bnr')
 texts=[]
 for p in (BASE/'HomeButton2').glob('*.csv'):
  table=list(csv.reader(io.StringIO(p.read_bytes().decode('utf-16')),delimiter='\t',skipinitialspace=True))
  assert len(table)==4 and all(len(row)==10 for row in table)
  write(OUT/(p.stem+'-table.json'),table)
  for i,row in enumerate(table):
   value=row[0]
   texts.append(dict(id=f'H_{p.stem}_{i}_0',source=p.relative_to(BASE).as_posix(),row=i,column=0,text=value,existing_korean=row[9]))
 credits=[]
 for p in (BASE/'art/fe/credits').glob('*.txt'):
  raw=p.read_bytes();text=raw.decode('cp1252');assert text.encode('cp1252')==raw
  credits.append(dict(source=p.relative_to(BASE).as_posix(),encoding='cp1252',text=text))
 videos=[]
 for p in sorted(BASE.rglob('*.thp')):
  b=p.read_bytes()[:128];assert b[:4]==b'THP\0';fps=struct.unpack_from('>f',b,16)[0];frames=u32(b,20)
  videos.append(dict(source=p.relative_to(BASE).as_posix(),bytes=p.stat().st_size,fps=fps,frames=frames,duration_seconds=frames/fps))
 write(ROOT/'manifests/system-assets.json',dict(files=files,images=images,unique_images=len(seen),fonts=fonts,errors=errors))
 write(ROOT/'work/translation/system-source-texts.json',texts);write(ROOT/'work/translation/credits-source.json',credits);write(ROOT/'manifests/videos.json',videos)
 from PIL import Image,ImageDraw
 selected=list({r['pixel_sha256']:r for r in images if '/tx_' in r['source'] or r['source'].startswith('opening.bnr')}.values())
 for batch in range(0,len(selected),40):
  sheet=Image.new('RGB',(1200,1000),'#37424b');draw=ImageDraw.Draw(sheet)
  for i,r in enumerate(selected[batch:batch+40]):
   x=i%5*240;y=i//5*125;im=Image.open(ROOT/r['image']).convert('RGBA');im.thumbnail((230,96));sheet.paste(im,(x+(230-im.width)//2,y+20),im);draw.text((x+3,y+3),r['id']+' '+r['source'].split('/')[-1][:25],fill='white')
  sheet.save(OUT/f'contact-{batch//40+1:02}.jpg')
 print('System images',len(images),'unique',len(seen),'Japanese CSV fields',len(texts),'THP',len(videos),'errors',errors,flush=True)
if __name__=='__main__':main()
