from pathlib import Path
import json,html,collections
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text('utf-8'))
def main():
 main=read('manifests/extracted-images.json')['images'];system=read('manifests/system-assets.json')['images'];allrows=main+system
 selected=[('로고·포스터',i,'펀치아웃!!') for i in ['G03167','G03184','G03229','G03275','G04346','S0418','S0422']]
 selected += [('손목 스트랩 안내',i,'한국어 안전 안내로 교체') for i in ['G03415','G03416']]
 home={'S0042':'닫기','S0043':'Wii 메뉴로','S0044':'다시 시작','S0045':'Wii 리모컨 설정','S0046':'Wii 리모컨 설정 닫기','S0047':'예','S0048':'아니요','S0051':'다시 연결','S0052':'음량','S0053':'진동','S0054':'연결','S0059':'HOME 버튼 메뉴'}
 selected += [('HOME 메뉴',k,v) for k,v in home.items()]
 # User explicitly keeps character decoration, including the 一番 headband
 # both on model textures and within videos, in its original language.
 groups=collections.defaultdict(list);targets=[];seen=set()
 for cat,id,ko in selected:
  r=next(r for r in allrows if r['id']==id)
  if r['pixel_sha256'] in seen:continue
  seen.add(r['pixel_sha256']);r=dict(r);r.update(category=cat,proposed_korean=ko,occurrences=[dict(id=x['id'],source=x['source'],offset=x.get('offset'),index=x.get('index')) for x in allrows if x['pixel_sha256']==r['pixel_sha256']],status='scope_pending' if '방침' in cat else 'translation_target');targets.append(r);groups[cat].append(r)
 (ROOT/'manifests/image-translation-targets.json').write_text(json.dumps(dict(targets=targets,english_only_images_preserved=True,visual_survey='All 1349 main unique images viewed in contact sheets; system Japanese label textures and banner inspected. Videos sampled, not exhaustively viewed.'),ensure_ascii=False,indent=2)+'\n','utf-8')
 style='body{background:#19242c;color:#e2edf2;font:16px system-ui;margin:32px}h1,h2{color:#80d0ff}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:18px}article{background:#2c3943;padding:16px;border-radius:12px}figure{margin:10px 0;padding:12px;background:repeating-conic-gradient(#46515b 0% 25%,#3c4751 0% 50%) 0/20px 20px;overflow:auto}img{max-width:100%;object-fit:contain}small{display:block;color:#a8bac6;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{border:1px solid #455663;padding:10px;text-align:left;white-space:pre-wrap}input{padding:10px;width:90%;margin-bottom:20px}'
 out=ROOT/'work/image-translation';out.mkdir(exist_ok=True);parts=[f'<!doctype html><meta charset="utf-8"><title>펀치아웃 이미지 번역 대상</title><style>{style}</style><h1>펀치아웃 · 일본어가 있는 그림만</h1><p>영문 전용 그림·배경·인물·기호는 제외했습니다. 같은 그림의 사본은 묶었습니다. 아직 번역본이 아닌 원본 대상 목록입니다.</p>']
 for cat,rows in groups.items():
  parts.append(f'<h2>{cat} · {len(rows)}종</h2><section>')
  for r in rows:
   src='../../'+r['image'];parts.append(f'<article><b>{r["id"]} · {html.escape(r["proposed_korean"])}</b><figure><img src="{src}" width="{r["width"]}" height="{r["height"]}" loading="lazy"></figure><small>{r["width"]}×{r["height"]} · 사본 {len(r["occurrences"])}개<br>{html.escape(r["source"])}</small></article>')
  parts.append('</section>')
 (out/'index.html').write_text('\n'.join(parts),'utf-8')
 rows=read('work/translation/source-texts.json');out=ROOT/'work/text-review';out.mkdir(exist_ok=True)
 text=[f'<!doctype html><meta charset="utf-8"><title>펀치아웃 추출 텍스트</title><style>{style}</style><h1>일본판 본문 925항목</h1><p>일본어 원문 · 같은 키의 영어 대조문. 번역 전 추출 검토입니다.</p><input placeholder="검색" oninput="document.querySelectorAll(\'tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><table><thead><tr><th>ID</th><th>일본어</th><th>영어 대조</th></tr></thead><tbody>']
 for r in rows:text.append('<tr><td>'+html.escape(r['id']+'\n'+r['symbol'])+'</td><td>'+html.escape(r['source'])+'</td><td>'+html.escape(r['english'])+'</td></tr>')
 text.append('</tbody></table>');(out/'index.html').write_text('\n'.join(text),'utf-8')
 print('Image target groups',dict((k,len(v)) for k,v in groups.items()),'total',len(targets))
if __name__=='__main__':main()
