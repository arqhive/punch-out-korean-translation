"""Repack NLG font glyphs: Hangul plus the digits/Latin/symbols the text uses in GmarketSans."""
import json,os,re,struct
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image,ImageDraw,ImageFont
from decode_gx import decode,palette_rgba

ROOT=Path(__file__).resolve().parents[1]
# Bold with a thin but fully opaque outline: real hardware shows the atlas at ~0.6x, where
# Medium strokes and a see-through outline blur into the background (2026-10-30 hardware test,
# user chose this over Medium with a thicker outline).
# GmarketSans is not in the repository: put it in tools/fonts or install it for the current user.
FONT=next((p for p in (ROOT/'tools/fonts/GmarketSansBold.otf',
                       Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft/Windows/Fonts/GmarketSansBold.otf',
                       Path('C:/Windows/Fonts/GmarketSansBold.otf')) if p.exists()),None)
assert FONT,'GmarketSansBold.otf not found (tools/fonts or Windows fonts)'
# Alpha gain after downscaling: the original glyphs have no translucent pixels inside the
# outline, so edge coverage is doubled and only the outermost pixel stays partly transparent.
ALPHA_GAIN=2.0
SS=4
CMAP=TTFont(FONT).getBestCmap()
OUT=ROOT/'work/font-build'

def pack_ci8(im,palette):
    a=np.asarray(im).astype(np.float32)
    # Compare premultiplied RGBA, so transparent RGB does not create fringes.
    p=np.asarray(palette,dtype=np.float32)
    p[:,:3]*=p[:,3:]/255
    a[...,:3]*=a[...,3:]/255
    colors,inverse=np.unique(a.reshape(-1,4),axis=0,return_inverse=True)
    indices=np.argmin(((colors[:,None]-p[None,:])**2).sum(axis=2),axis=1).astype(np.uint8)
    idx=indices[inverse].reshape(im.height,im.width)
    return idx.reshape(im.height//4,4,im.width//8,8).transpose(0,2,1,3).tobytes()

def build(source,needed):
    b=source.read_bytes();table,n=struct.unpack_from('>II',b)
    entries=[struct.unpack_from('>III',b,table+i*12) for i in range(n)]
    desc=b[entries[-1][1]*32:entries[-1][1]*32+entries[-1][2]].decode('ascii')
    height=int(re.search(r'RenderHeight (\d+)',desc)[1]);baseline=int(re.search(r'RenderAscent (\d+)',desc)[1])
    pages=[];headers=[];palbytes=[]
    for key,units,length in entries[:-1]:
        raw=b[units*32:units*32+length];w,h=struct.unpack_from('>HH',raw,4)
        assert (w,h)==(512,512) and length==96+w*h+512
        pal=raw[96+w*h:];headers.append(raw[:96]);palbytes.append(pal)
        pages.append(decode(raw[96:96+w*h],w,h,9,palette_rgba(pal,2)))
    metrics=re.findall(r'^Glyph (\S+) Width (-?\d+) (-?\d+) (-?\d+)',desc,re.M)
    size=40 if height>40 else 21
    stroke=2 if height>40 else 1
    font=ImageFont.truetype(str(FONT),size);bigfont=ImageFont.truetype(str(FONT),size*SS)
    hangul_advance=round(font.getlength('한'))
    # GmarketSans descenders (g, j, y) with the outline reach past the cell bottom; raise every
    # new glyph so the deepest one keeps a 1px margin (the original glyphs kept ~4px).
    lowest=max(baseline+font.getbbox(chr(cp),anchor='ls',stroke_width=stroke)[3]-1 for cp in needed if cp in CMAP)
    dy=min(0,(height-2)-lowest)
    def render(code,cp):
        # Hangul keeps one fixed advance; digits, Latin and symbols use the font's own advance
        # so they share the Hangul size and baseline instead of the original Japanese font's.
        ch=chr(cp);advance=hangul_advance if 0xac00<=cp<=0xd7a3 else round(font.getlength(ch))
        left,_,right,_=font.getbbox(ch,anchor='ls',stroke_width=stroke)
        # Glyphs reaching left of the origin (e.g. 'j') move right just enough not to clip.
        ox=stroke+1+max(0,-(left+stroke+1))
        width=max(advance+2*stroke+2,right+ox+1)
        # Draw at SS times the size and box-average down: exact edge coverage keeps the outline
        # clean when real hardware shows the atlas at ~0.6x without mipmaps.
        big=Image.new('RGBA',(width*SS,height*SS));draw=ImageDraw.Draw(big)
        draw.text((ox*SS,(baseline+dy)*SS),ch,font=bigfont,anchor='ls',fill='white',stroke_width=stroke*SS,stroke_fill='black')
        im=big.convert('RGBa').resize((width,height),Image.Resampling.BOX).convert('RGBA')
        a=np.asarray(im).copy();a[...,3]=np.clip(a[...,3].astype(np.float32)*ALPHA_GAIN,0,255).astype(np.uint8)
        im=Image.fromarray(a)
        return (code,advance,width,0,im)
    # Redraw every non-Hangul character the game text uses, except the '=' button
    # placeholder, the space, and characters GmarketSans lacks (they keep the original glyph).
    redraw={cp for cp in needed if not 0xac00<=cp<=0xd7a3 and chr(cp) not in '= ' and cp in CMAP}
    glyphs=[];x=y=page=0;retained=set()
    for code,advance,width,left in metrics:
        advance,width,left=map(int,(advance,width,left));cp=ord(code) if len(code)==1 else int(code)
        if x+width>512:x=0;y+=height
        if y+height>512:y=0;page+=1
        assert page<len(pages)
        if cp in redraw:
            glyphs.append(render(code,cp));retained.add(cp)
        # Keep all non-Japanese glyphs and any explicitly needed original characters.
        elif cp in needed or not (0x3000<=cp<=0x9fff or 0xff00<=cp<=0xffef):
            glyphs.append((code,advance,width,left,pages[page].crop((x,y,x+width,y+height))))
            retained.add(cp)
        x+=width
    for cp in sorted(needed-retained):glyphs.append(render(str(cp),cp))
    newpages=[Image.new('RGBA',(512,512))];x=y=0
    positions=[]
    for code,adv,w,left,im in glyphs:
        if x+w>512:x=0;y+=height
        if y+height>512:y=0;newpages.append(Image.new('RGBA',(512,512)))
        newpages[-1].paste(im,(x,y));positions.append((code,len(newpages)-1,x,y,w));x+=w
    # Union of original palettes plus all grayscale/alpha combinations needed by new glyphs.
    # Original glyph colors remain exactly representable in the original palette.
    palette_raw=palbytes[0];palette=palette_rgba(palette_raw,2)
    chunks=[]
    for i,im in enumerate(newpages):
        payload=pack_ci8(im,palette)
        header=bytearray(headers[0]);struct.pack_into('>I',header,20,0)
        chunks.append((entries[0][0]+i,bytes(header)+payload+palette_raw))
        decoded=decode(payload,512,512,9,palette)
        decoded.save(OUT/f'{source.stem}-{i:02}.png')
    prefix=desc[:desc.index('Glyph ')]
    assert len(newpages)<=len(pages),(source.name,len(newpages),len(pages))
    prefix=re.sub(r'PageCount \d+',f'PageCount {len(newpages)}',prefix)
    tail=desc[desc.index('Kern '):] if 'Kern ' in desc else 'END\r\n'
    # Original kerning pairs were tuned for the original glyphs; drop pairs touching redrawn ones.
    tail=''.join(line for line in tail.splitlines(True)
                 if not (line.startswith('Kern ') and any(ord(c) in redraw for c in line.split()[1:3] if len(c)==1)))
    newdesc=prefix+'\r\n\r\n'.join(f'Glyph {c} Width {a} {w} {l}' for c,a,w,l,_ in glyphs)+'\r\n\r\n'+tail
    chunks.append((entries[-1][0],newdesc.encode('ascii')))
    first=(32+12*len(chunks)+31)//32*32
    result=bytearray(first);result[:32]=b[:32];struct.pack_into('>II',result,4,len(chunks),1);struct.pack_into('>I',result,12,first//32)
    for i,(key,raw) in enumerate(chunks):
        pos=len(result);assert pos%32==0
        struct.pack_into('>III',result,32+i*12,key,pos//32,len(raw))
        result.extend(raw);result.extend(bytes((-len(result))%32))
    dest=OUT/source.name;dest.write_bytes(result)
    (OUT/(source.stem+'.txt')).write_text(newdesc,encoding='ascii')
    (OUT/(source.stem+'-positions.json')).write_text(json.dumps(positions),encoding='utf-8')
    return {'source':str(source.relative_to(ROOT)),'output':str(dest.relative_to(ROOT)),'original_pages':len(pages),'pages':len(newpages),'glyphs':len(glyphs),'added':len(needed-retained),'bytes':len(result),'runtime_verified':False}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=json.loads((ROOT/'work/translation/translated-texts.json').read_text(encoding='utf-8'))
    needed={ord(c) for r in rows for c in re.sub(r'\{[^}]+\}','',r['translation']) if c not in '\r\n'}
    # Credits stay in the original English/CP1252 text, so only their source characters are needed.
    credits=json.loads((ROOT/'work/translation/credits-source.json').read_text(encoding='utf-8'))
    needed.update(ord(c) for r in credits for c in r['text'] if c not in '\r\n')
    report=[build(p,needed) for p in (ROOT/'work/jp/DATA/files/art/fe/fonts').glob('*.res')]
    (ROOT/'manifests/korean-font-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
