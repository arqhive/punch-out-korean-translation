"""Inventory original DATA partitions and losslessly read NLG localization."""
from pathlib import Path
from collections import Counter
import json,struct,hashlib,csv,re
ROOT=Path(__file__).resolve().parents[1]
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def write(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf-8')
def parse_loc(b):
 assert b[:4]==b'NLOC';version,language,n,unit=struct.unpack_from('>4I',b,4)
 assert version==unit==1;start=20+n*8;entries=[];keys=[]
 for i in range(n):
  key,offset=struct.unpack_from('>II',b,20+i*8);pos=start+2*offset;end=pos
  assert pos>=start and pos<len(b)
  while b[end:end+2]!=b'\0\0':end+=2;assert end+2<=len(b)
  text=b[pos:end].decode('utf-16be');entries.append(dict(hash=f'{key:08x}',offset=pos,unit_offset=offset,text=text));keys.append(key)
 assert keys==sorted(set(keys))
 # Recreate original exact layout, including aliases, from every referenced string.
 rebuilt=bytearray(b[:start]);rebuilt.extend(bytes(len(b)-start));covered=bytearray(len(b)-start)
 for e in entries:
  raw=e['text'].encode('utf-16be')+b'\0\0';off=e['offset'];rebuilt[off:off+len(raw)]=raw;covered[off-start:off-start+len(raw)]=b'\1'*len(raw)
 assert bytes(rebuilt)==b
 assert all(covered),('unreferenced string data',covered.count(0))
 return dict(language_hash=f'{language:08x}',count=n,string_base=start,entries=entries,lossless_roundtrip=True)
def main():
 inventories={};localizations={};fonts={}
 for ed in ['jp','us']:
  base=ROOT/'work'/ed/'DATA';files=[];inventory=ROOT/'manifests'/f'{ed}-original-files.json'
  if inventory.exists():files=json.loads(inventory.read_text('utf-8'))
  else:
   for p in sorted(base.rglob('*')):
    if not p.is_file():continue
    files.append(dict(path=p.relative_to(base).as_posix(),bytes=p.stat().st_size,sha256=sha_file(p)))
  write(ROOT/'manifests'/f'{ed}-original-files.json',files);inventories[ed]={x['path']:x for x in files}
  locs={}
  for p in sorted((base/'files/art/fe').glob('*.loc')):
   loc=parse_loc(p.read_bytes());locs[p.stem]=loc;write(ROOT/'work/extracted-text'/ed/(p.stem+'.json'),loc)
  localizations[ed]=locs;fonts[ed]=[]
  for p in sorted((base/'files/art/fe/fonts').glob('*.res')):
   b=p.read_bytes();table,count=struct.unpack_from('>II',b);assert table==32
   key,units,size=struct.unpack_from('>III',b,table+(count-1)*12);desc=b[units*32:units*32+size].decode('ascii')
   assert desc.startswith('NLG Font Description file');glyphs=re.findall(r'^Glyph (\S+) [Ww]idth (-?\d+) (-?\d+) (-?\d+)',desc,re.M)
   codes=[ord(c) if len(c)==1 else int(c) for c,*_ in glyphs]
   dest=ROOT/'work/extracted-fonts'/ed/(p.stem+'.txt');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(desc,'utf-8')
   fonts[ed].append(dict(file=p.relative_to(base).as_posix(),bytes=len(b),pages=count-1,glyphs=len(codes),hangul=sum(0xac00<=c<=0xd7a3 for c in codes),cjk=sum(0x4e00<=c<=0x9fff for c in codes),kana=sum(0x3040<=c<=0x30ff for c in codes),description=dest.relative_to(ROOT).as_posix()))
  print(ed,'files',len(files),'localizations',{k:v['count'] for k,v in locs.items()},flush=True)
 jp,us=inventories['jp'],inventories['us'];common=sorted(jp.keys()&us.keys());same=[p for p in common if jp[p]['sha256']==us[p]['sha256']]
 byhash={lang:{e['hash']:e for e in loc['entries']} for lang,loc in localizations['jp'].items()}
 assert byhash['japanese'].keys()==byhash['english'].keys()==byhash['id'].keys()
 rows=[]
 for key,e in byhash['japanese'].items():
  text=e['text'];rows.append(dict(id='L'+key.upper(),hash=key,symbol=byhash['id'][key]['text'],source=text,english=byhash['english'][key]['text'],translation=None,offset=e['offset'],source_file='art/fe/japanese.loc',tokens=re.findall(r'\{[^}]*\}',text)))
 write(ROOT/'work/translation/source-texts.json',rows)
 with (ROOT/'work/translation/source-texts.tsv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f,delimiter='\t');w.writerow(['id','symbol','Japanese','English','Korean']);w.writerows((r['id'],r['symbol'],r['source'],r['english'],'') for r in rows)
 usja={e['hash']:e['text'] for e in localizations['us']['longest']['entries']};jpja=byhash['japanese']
 diff=[dict(id='L'+k.upper(),japanese_jp=jpja[k]['text'],mixed_language_longest_us=usja[k]) for k in sorted(jpja.keys()&usja.keys()) if re.search('[\u3040-\u30ff]',usja[k]) and jpja[k]['text']!=usja[k]]
 write(ROOT/'manifests/japanese-edition-text-differences.json',diff)
 report=dict(editions={ed:dict(files=len(inv),payload_files=sum(k.startswith('files/') for k in inv),payload_bytes=sum(v['bytes'] for k,v in inv.items() if k.startswith('files/')),extensions=dict(Counter(Path(k).suffix for k in inv if k.startswith('files/'))),languages={k:v['count'] for k,v in localizations[ed].items()},fonts=fonts[ed]) for ed,inv in inventories.items()},same_paths=len(common),identical_files=len(same),changed_common_files=[k for k in common if k not in same],jp_only=sorted(jp.keys()-us.keys()),us_only=sorted(us.keys()-jp.keys()),japanese_vs_us_mixed_longest_difference_count=len(diff),jp_extra_texts=sorted(jpja.keys()-usja.keys()),text_fields=len(rows),japanese_characters=sum(len(r['source']) for r in rows),selected='jp',reason='Japan has a dedicated Japanese localization, 28 additional keys, and embedded Japanese glyph coverage. US longest.loc contains mixed-language test strings, not a complete Japanese localization.',runtime_tested=False)
 write(ROOT/'manifests/edition-analysis.json',report)
 print('Selected JP. Fields:',len(rows),'changed Japanese compared to US:',len(diff),flush=True)
if __name__=='__main__':main()
