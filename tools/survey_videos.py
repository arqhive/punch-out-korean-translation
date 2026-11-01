"""Representative THP frames for lettering survey, not an exhaustive video review."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,subprocess,imageio_ffmpeg
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/jp/DATA/files';OUT=ROOT/'work/video-survey';OUT.mkdir(parents=True,exist_ok=True)
def main():
 videos=json.loads((ROOT/'manifests/videos.json').read_text('utf-8'));jobs=[]
 for i,v in enumerate(videos):
  for j,fraction in enumerate([.15,.5,.85]):jobs.append((i,j,v,fraction))
 def extract(job):
  i,j,v,part=job;dest=OUT/f'V{i+1:02}-{j}.png'
  if dest.exists():return dict(file=str(dest),ok=True,error='')
  args=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-ss',str(v['duration_seconds']*part),'-i',str(BASE/v['source']),'-frames:v','1','-vf','scale=320:-1','-y',str(dest)]
  p=subprocess.run(args,capture_output=True)
  if not dest.exists():
   args=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-i',str(BASE/v['source']),'-frames:v','1','-vf',f'select=eq(n\\,{int(v["frames"]*part)}),scale=320:-1','-fps_mode','vfr','-y',str(dest)]
   p=subprocess.run(args,capture_output=True)
  return dict(file=str(dest),ok=dest.exists(),error=p.stderr.decode(errors='replace')[:500])
 with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(extract,jobs))
 (OUT/'sampling.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
 for batch in range(0,len(videos),6):
  sheet=Image.new('RGB',(1000,1200),'#37424b');draw=ImageDraw.Draw(sheet)
  for i,v in enumerate(videos[batch:batch+6]):
   draw.text((5,i*200+2),f'V{batch+i+1:02} '+v['source'].split('/')[-1],fill='white')
   for j in range(3):
    p=OUT/f'V{batch+i+1:02}-{j}.png'
    if p.exists():
     im=Image.open(p).convert('RGB');im.thumbnail((325,177));sheet.paste(im,(j*333,i*200+20))
  sheet.save(OUT/f'contact-{batch//6+1:02}.jpg')
 print('Sampled',sum(x['ok'] for x in result),'/',len(jobs),'frames from',len(videos),'THP files; not exhaustive.',flush=True)
if __name__=='__main__':main()
