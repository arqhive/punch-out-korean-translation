"""Replace the katakana subtitle of the PUNCH-OUT!! logo in the THP videos with Korean.

The videos show the G03275 title logo (anamorphic, ~0.45 x 0.60). Per video:
1. SIFT finds the logo pose in every frame where it is clearly visible.
2. Each run is extended frame by frame (fade-in, zoom, dissolve) with ECC, and with a
   subtitle-only search once the logo is too faint or too large for ECC.
3. Runs where the logo holds still share one median pose, so the subtitle does not jitter.
4. Around the subtitle the frame is f = opacity*JP + (1 - opacity*a_jp)*bg. bg is rebuilt by
   inpainting under the Japanese letters, the opacity is fitted there, and the Korean
   subtitle is laid over that bg the same way.
Frames are re-encoded with the original quantisation/Huffman tables (raised one step at a time
only if a frame outgrows its slot) and written back into their original THP slots, so no THP
header, frame size or audio byte changes.
"""
from pathlib import Path
import io,json,struct
import numpy as np,cv2
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
MOVIES=ROOT/'work/jp/DATA/files/art/movies'
OUT=ROOT/'work/video-build'
TRACK=ROOT/'manifests/logo-video-track.json'
VIDEOS=['attract_tutorial.thp','Tutorial_Detailed.thp','Intro_Movie.thp']
BOX=(361,182,493,206)       # G03275 subtitle box in texture space
BLUR=0.4                    # the videos render the logo slightly soft

def frames(b):
    first,nc=struct.unpack_from('>I',b,0x18)[0],struct.unpack_from('>I',b,struct.unpack_from('>I',b,0x20)[0])[0]
    pos,size,out=struct.unpack_from('>I',b,0x28)[0],first,[]
    for _ in range(struct.unpack_from('>I',b,0x14)[0]):
        nxt=struct.unpack_from('>I',b,pos)[0];sizes=struct.unpack_from('>'+'I'*nc,b,pos+8)
        out.append((pos+8+4*nc,sizes[0]));pos+=size;size=nxt
    return out

def scan_start(j):
    k=2
    while j[k+1]!=0xDA:k+=2+struct.unpack_from('>H',j,k+2)[0]
    return k+2+struct.unpack_from('>H',j,k+2)[0]

def to_std(j):
    # THP scans omit the FF00 byte stuffing of standard JPEG.
    s,e=scan_start(j),j.rindex(b'\xff\xd9');return j[:s]+j[s:e].replace(b'\xff',b'\xff\x00')+b'\xff\xd9'

def encode(rgb,orig,limit):
    # Original quantisation tables first; only if the frame outgrows its slot, raise every
    # table entry by one step at a time. Everything after the DQT segments stays identical.
    q=Image.open(io.BytesIO(to_std(orig))).quantization;o=scan_start(orig)
    for step in range(8):
        buf=io.BytesIO();Image.fromarray(rgb).save(buf,'JPEG',qtables={k:[min(255,v+step) for v in t] for k,t in q.items()},subsampling=2,optimize=False)
        p=buf.getvalue();assert p[2:4]==b'\xff\xe0';p=p[:2]+p[4+struct.unpack_from('>H',p,4)[0]:]   # drop APP0
        s=scan_start(p);assert p[2+2*69:s]==orig[2+2*69:o],'headers differ from the original frame'
        e=p.rindex(b'\xff\xd9');j=p[:s]+p[s:e].replace(b'\xff\x00',b'\xff')+b'\xff\xd9'
        if len(j)<=limit:return j,step
    raise ValueError('frame does not fit its slot')

def premul(path):
    a=np.asarray(Image.open(path).convert('RGBA')).astype(np.float32)/255;a[...,:3]*=a[...,3:];return a

def warp(img,A,ss=4):
    # Supersampled warp then area-average, so the 0.45x downscale does not alias.
    big=cv2.warpAffine(img,(np.asarray(A,np.float32)*ss),(512*ss,384*ss),flags=cv2.INTER_LINEAR)
    return cv2.resize(big,(512,384),interpolation=cv2.INTER_AREA)

def subtitle_search(f,jp,init):
    # Too faint or too large for ECC: match only the subtitle, keeping the anamorphic ratio.
    M=np.zeros(jp.shape[:2],np.float32);x0,y0,x1,y1=BOX;M[y0:y1,x0:x1]=1;sub=jp[...,:3].mean(2)*M
    ratio=init[1][1]/init[0][0];best=(-2,None)
    for k in np.linspace(0.7,1.4,71):
        A=np.array(init,np.float64);A[0,0]*=k;A[1,1]=A[0,0]*ratio
        c=np.array([(x0+x1)/2,(y0+y1)/2,1]);A[:,2]+=(np.array(init)@c)-(A@c)    # scale about the subtitle centre
        w=warp(sub,A);ys,xs=np.where(w>0.02)
        if not len(xs):continue
        tpl=w[ys.min():ys.max()+1,xs.min():xs.max()+1];pad=40
        area=f[max(0,ys.min()-pad):ys.max()+1+pad,max(0,xs.min()-pad):xs.max()+1+pad]
        if area.shape[0]<tpl.shape[0] or area.shape[1]<tpl.shape[1] or area.std()<1e-3:continue
        r=cv2.matchTemplate(area,tpl,cv2.TM_CCOEFF_NORMED);_,v,_,loc=cv2.minMaxLoc(r)
        if v>best[0]:
            A[0,2]+=loc[0]-(xs.min()-max(0,xs.min()-pad));A[1,2]+=loc[1]-(ys.min()-max(0,ys.min()-pad));best=(v,A)
    return best

def corners(A):
    x0,y0,x1,y1=BOX;return np.array(A)@np.array([[x0,y0,1],[x1,y0,1],[x0,y1,1],[x1,y1,1]],float).T

def sane(A):
    # The logo is never mirrored and keeps the anamorphic ratio (~1.335) in every video.
    A=np.asarray(A);return A[0,0]>0.05 and A[1,1]>0.05 and abs(A[1,1]/A[0,0]-1.335)<0.15

def track(b,slots,jp):
    gray=lambda i:cv2.cvtColor(decode(b[slots[i][0]:slots[i][0]+slots[i][1]]),cv2.COLOR_RGB2GRAY).astype(np.float32)/255
    sift=cv2.SIFT_create();kt,dt=sift.detectAndCompute((jp[...,:3].mean(2)*255).astype(np.uint8),None)
    tex=np.zeros((384,512),np.float32);tex[:256]=jp[...,:3].mean(2)
    crit=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,300,1e-7);pose={}
    for i in range(len(slots)):
        kf,df=sift.detectAndCompute((gray(i)*255).astype(np.uint8),None)
        if df is None or len(kf)<20:continue
        good=[a for a,c in cv2.BFMatcher().knnMatch(dt,df,k=2) if a.distance<0.75*c.distance]
        if len(good)<20:continue
        A,inl=cv2.estimateAffine2D(np.float32([kt[m.queryIdx].pt for m in good]),np.float32([kf[m.trainIdx].pt for m in good]),ransacReprojThreshold=2.0)
        if A is not None and inl.sum()>=60:pose[i]={'A':A,'method':'sift'}
    # Extend every run outwards until neither ECC nor the subtitle search finds the logo.
    for e in sorted(pose):
        for d in (-1,1):
            if e+d in pose or e-d not in pose:continue
            cur,prev=e,e-d
            for _ in range(12):
                n=cur+d
                if not 0<=n<len(slots) or n in pose:break
                a1,a2=pose[cur]['A'],pose[prev]['A'];vel=a1-a2
                init=a1+vel*(1.35 if np.abs(corners(vel)).max()>1 else 1)   # zooms accelerate
                if not sane(init):break
                g=gray(n);mask=(cv2.warpAffine(jp[...,3],init.astype(np.float32),(512,384))>0.5).astype(np.uint8)
                try:cc,W=cv2.findTransformECC(g,tex,cv2.invertAffineTransform(init).astype(np.float32),cv2.MOTION_AFFINE,crit,mask,1)
                except cv2.error:cc=-1
                if cc>=0.55 and sane(cv2.invertAffineTransform(W)):pose[n]={'A':cv2.invertAffineTransform(W),'method':'ecc'}
                else:
                    v,A=subtitle_search(g,jp,init)
                    # A faint dissolving subtitle still scores ~0.4, but so do ring ropes: accept
                    # only near the predicted spot (4px for a still logo, more when it moves fast).
                    tol=4+1.35*np.abs(corners(vel)).max()
                    if v<0.35 or not sane(A) or np.abs(corners(A).mean(1)-corners(init).mean(1)).max()>tol:break
                    pose[n]={'A':A,'method':'subtitle'}
                prev,cur=cur,n
    # Hold still runs on one median pose.
    order=sorted(pose);group=[]
    for i in order+[None]:
        if i is not None and group and i==group[-1]+1 and np.abs(corners(pose[i]['A'])-corners(pose[group[0]]['A'])).max()<0.8:group.append(i);continue
        if len(group)>=6:
            med=np.median([pose[k]['A'] for k in group],axis=0)
            for k in group:pose[k]={'A':med,'method':pose[k]['method']+'+still'}
        group=[i] if i is not None else []
    return {i:{'A':np.asarray(v['A']).tolist(),'method':v['method']} for i,v in sorted(pose.items())}

def decode(j):return np.asarray(Image.open(io.BytesIO(to_std(bytes(j)))).convert('RGB'))

def swap(f,jw,kw,reg):
    # Around the subtitle f = opacity*JP + (1 - opacity*a_jp)*bg: rebuild bg by inpainting
    # under the Japanese letters, fit the opacity there, lay the Korean subtitle the same way.
    ys,xs=np.where(reg);y0,y1,x0,x1=max(0,ys.min()-8),min(384,ys.max()+9),max(0,xs.min()-8),min(512,xs.max()+9)
    c=f[y0:y1,x0:x1];j=jw[y0:y1,x0:x1];k=kw[y0:y1,x0:x1]
    hole=cv2.dilate((j[...,3]>0.02).astype(np.uint8),np.ones((3,3)))
    bg=cv2.inpaint((c*255).astype(np.uint8),hole,5,cv2.INPAINT_TELEA).astype(np.float32)/255
    u=hole>0;x=(j[...,:3]-j[...,3:]*bg)[u];y=(c-bg)[u];beta=float(np.clip((x*y).sum()/max((x*x).sum(),1e-9),0,1.05))
    out=f.copy();r=reg[y0:y1,x0:x1]
    out[y0:y1,x0:x1][r]=(beta*k[...,:3]+(1-beta*k[...,3:])*bg)[r]
    return out,beta

def build(name,jp,ko,cached):
    src=MOVIES/name;b=bytearray(src.read_bytes());slots=frames(b)
    tr={int(k):v for k,v in cached.items()} if cached else track(b,slots,jp)
    M=np.zeros(jp.shape[:2],np.float32);x0,y0,x1,y1=BOX;M[y0-4:y1+4,x0-4:x1+4]=1;report={}
    for i,p in sorted(tr.items()):
        off,size=slots[i];orig=bytes(b[off:off+size].rstrip(b'\0'));f=decode(orig).astype(np.float32)/255
        jw=cv2.GaussianBlur(warp(jp*M[...,None],p['A']),(0,0),BLUR);kw=cv2.GaussianBlur(warp(ko*M[...,None],p['A']),(0,0),BLUR)
        reg=cv2.dilate(((jw[...,3]>0.004)|(kw[...,3]>0.004)).astype(np.uint8),np.ones((7,7)))>0
        if reg.sum()<20 or np.ptp(corners(p['A'])[1])<5:continue   # off screen, or too small to read
        new,beta=swap(f,jw,kw,reg)
        if beta<0.02:continue
        j,step=encode((np.clip(new,0,1)*255+0.5).astype(np.uint8),orig,size)
        b[off:off+size]=j+bytes(size-len(j))
        report[i]={**p,'opacity':round(beta,3),'jpeg':len(j),'slot':size,'q_step':step}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/name).write_bytes(b)
    assert len(b)==src.stat().st_size
    return report

def main():
    targets={r['id']:r for r in json.loads((ROOT/'manifests/image-translation-targets.json').read_text(encoding='utf-8'))['targets']}
    jp=premul(ROOT/targets['G03275']['image']);ko=premul(ROOT/'work/image-edits/G03275.png')
    cache=json.loads(TRACK.read_text(encoding='utf-8')) if TRACK.exists() else {};report={}
    for name in VIDEOS:
        report[name]=build(name,jp,ko,{k:{'A':v['A'],'method':v['method']} for k,v in cache.get(name,{}).items()})
        f=sorted(report[name]);print(name,'frames',len(f),'ranges',f[:1],'...',f[-1:])
    TRACK.write_text(json.dumps({n:{str(k):v for k,v in r.items()} for n,r in report.items()},indent=1),encoding='utf-8')

if __name__=='__main__':main()
