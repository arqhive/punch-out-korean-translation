"""Bounded linear scan for Japanese UTF-16BE runs outside NLOC/CSV."""
from pathlib import Path
import numpy as np,json,re
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'work/jp/DATA'
def main():
 rows=[];paths=sorted((BASE/'files').rglob('*.data'))+[BASE/'sys/main.dol']
 for p in paths:
  b=p.read_bytes()
  for parity in [0,1]:
   a=np.frombuffer(b[parity:len(b)-(len(b)-parity)%2],dtype='>u2');kana=((a>=0x3041)&(a<=0x3096))|((a>=0x30a1)&(a<=0x30fa))
   if len(a)<4:continue
   candidates=np.flatnonzero(kana[:-2]&kana[1:-1]&kana[2:])
   if not len(candidates):continue
   valid=((a>=32)&(a<=126))|((a>=0x3000)&(a<=0x9fff))|((a>=0xff01)&(a<=0xff60))|(a==9)|(a==10)|(a==13)
   borders=np.flatnonzero(~valid);seen=set()
   for pos in candidates:
    j=np.searchsorted(borders,pos);start=0 if j==0 else int(borders[j-1])+1;end=len(a) if j==len(borders) else int(borders[j])
    if start in seen or end==len(a) or a[end]!=0 or end-start>4096:continue
    seen.add(start)
    if np.count_nonzero(kana[start:end])<4:continue
    text=b[parity+start*2:parity+end*2].decode('utf-16be');rows.append(dict(source=p.relative_to(BASE).as_posix(),offset=parity+start*2,text=text,status='candidate_not_confirmed'))
 (ROOT/'manifests/additional-string-candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n','utf-8')
 print('Scanned',len(paths),'files; additional candidate runs',len(rows),flush=True)
 print(str(rows)[:1200],flush=True)
if __name__=='__main__':main()
