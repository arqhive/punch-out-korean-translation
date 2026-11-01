"""Size/localize approved raster assets and decode reusable Korean Wii HOME assets."""
from pathlib import Path
import json,struct,shutil
import numpy as np
from PIL import Image
from decode_gx import decode,size

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/image-edits'
OLD=Path('G:/KoreanTranslation/GPT초벌작/[Wii] 치비로보')

def main():
    OUT.mkdir(exist_ok=True)
    generated=Image.open(OUT/'logo-imagegen.png').convert('RGBA')
    # Use only ImageGen's localized subtitle. English logo pixels remain original.
    # Crop is measured from the inspected 1774x888 generated logo.
    W,H=generated.size
    subtitle=generated.crop((round(W*.709),round(H*.716),W,round(H*.857)))
    subtitle=subtitle.crop(subtitle.getbbox())
    targets=json.loads((ROOT/'manifests/image-translation-targets.json').read_text(encoding='utf-8'))['targets']
    boxes={'G03229':(338,187,505,217),'G03275':(361,182,493,206),
           'G04346':(116,45,162,55),'S0418':(181,90,247,103),'S0422':(90,44,124,51)}
    # S0422: '!!' shadow row below; G03275: パ handakuten outline above 펀; G03229: パ outline left of 펀.
    leftovers={'S0422':[(90,51,124,52)],'G03275':[(378,181,382,182)],'G03229':[(336,208,338,213)]}
    report=[]
    for row in targets:
        key=row['id'];im=Image.open(ROOT/row['image']).convert('RGBA')
        method=''
        if key in boxes:
            x0,y0,x1,y1=boxes[key]
            # These rectangles contain only subtitle glyphs on transparent background;
            # no painted background is copied or synthesized.
            region=im.crop((x0,y0,x1,y1));assert region.size[0]>0
            im.paste(im.getpixel((0,0)),(x0,y0,x1,y1))
            # Japanese glyph outlines that reach just outside a box; erase them without moving
            # the box, so the subtitle keeps its size and position. Logo frame/burst untouched.
            for extra in leftovers.get(key,()):im.paste(im.getpixel((0,0)),extra)
            sub=subtitle.copy();sub.thumbnail((x1-x0,y1-y0),Image.Resampling.LANCZOS)
            im.alpha_composite(sub,(x0+(x1-x0-sub.width)//2,y0+(y1-y0-sub.height)//2))
            method='imagegen subtitle; original English logo retained'
        elif key in ('G03167','G03184'):
            name='opening' if key=='G03167' else 'retired'
            clean=Image.open(ROOT/f'work/us-logo-reference/{name}.png').convert('RGBA')
            box=(148,119,205,135) if key=='G03167' else (147,70,201,85)
            a=np.array(im);b=np.array(clean);x0,y0,x1,y1=box
            # Pixel difference mask against the matching original non-Japanese edition.
            # Restores real background under glyphs, never paints a solid rectangle.
            mask=np.zeros(a.shape[:2],bool)
            mask[y0:y1,x0:x1]=np.any(a[y0:y1,x0:x1]!=b[y0:y1,x0:x1],axis=2)
            a[mask]=b[mask];im=Image.fromarray(a)
            sub=subtitle.copy();sub.thumbnail((x1-x0-3,11),Image.Resampling.LANCZOS)
            im.alpha_composite(sub,(x0+1,y0+1))
            method='imagegen subtitle; original US background via difference mask'
        elif key in ('G03415','G03416'):
            n=0 if key=='G03415' else 1
            src=OLD/f'work/remaining-images/encoded/strap-{n}.png'
            im=Image.open(src).convert('RGBA').resize((row['width'],row['height']),Image.Resampling.LANCZOS)
            method='reuse previously reviewed Korean Wii safety notice; texture aspect conversion'
        elif row['category']=='HOME 메뉴':
            filename=row['source'].split('/')[-1]
            p=ROOT/'work/reused-home/arc/timg'/filename
            raw=p.read_bytes();hd=struct.unpack_from('>I',raw,12)[0];h,w,fmt,off=struct.unpack_from('>HHII',raw,hd)
            im=decode(raw[off:off+size(w,h,fmt)],w,h,fmt)
            assert (w,h)==(row['width'],row['height']),(key,(w,h),(row['width'],row['height']))
            method='reuse original Korean Wii HOME texture from owned Chibi-Robo disc'
        else:raise ValueError(key)
        im.save(OUT/(key+'.png'))
        report.append({'id':key,'method':method,'path':f'work/image-edits/{key}.png','size':im.size})
    (ROOT/'manifests/image-edit-provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared',len(report),'images')

if __name__=='__main__':main()
