"""Assemble explicit translations; never use untranslated fallback silently."""
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/translation'
ROWS = json.loads((WORK / 'source-texts.json').read_text(encoding='utf-8'))

def main():
    translated = {}
    for path in sorted(WORK.glob('ko-*.tsv')):
        for line in path.read_text(encoding='utf-8').splitlines():
            key, value = line.split('\t', 1)
            if key in translated:
                raise ValueError(f'duplicate translation {key}')
            translated[key] = value
    assert set(translated) <= {r['id'] for r in ROWS}
    source_map = {}
    for row in ROWS:
        if row['id'] in translated:
            source_map.setdefault(row['source'], translated[row['id']])
    preserve = {'', '?', '??', '???', 'GOOD！', 'GREAT！', 'OK！', '1P', '2P',
                'ON', 'OFF', 'KO', 'TKO', 'KO！', 'TKO！', 'VS', 'kg', 'lbs.',
                '.', ':', 'X2', 'X4', 'X6', 'X8', 'X10', '{p}', '{0}',
                '{2}/{1}/{0}', '{0}/{1}', '{0} /{1}'}
    preserve_symbols = {'LOC_CREDITS_COPYRIGHT', 'LOC_CREDITS_FLIP_CHARACTERS'}
    replacements = {
        '年齢：': '나이: ', '出身：': '출신: ', '戦績：': '전적: ',
        'アイルランド・ダブリン': '아일랜드·더블린',
        'トルコ・イスタンブール': '튀르키예·이스탄불',
        'カナダ・サーモンアーム': '캐나다·새먼암', 'スペイン・マドリード': '스페인·마드리드',
        'フランス・パリ': '프랑스·파리', 'インド・ムンバイ': '인도·뭄바이',
        'アメリカ合衆国・ブルックリン': '미국·브루클린',
        '南太平洋・ヒッポーアイランド': '남태평양·히포 아일랜드',
        '日本・東京': '일본·도쿄', 'アメリカ合衆国・フィラデルフィア': '미국·필라델피아',
        'ロシア・モスクワ': '러시아·모스크바', 'アメリカ合衆国・ハリウッド': '미국·할리우드',
        'ドイツ・ベルリン': '독일·베를린',
    }
    missing, errors, output = [], [], []
    for row in ROWS:
        src = row['source']
        value = translated.get(row['id'])
        status = 'translated'
        if value is None and src in source_map:
            value, status = source_map[src], 'shared_translation'
        if value is None and (src in preserve or row['symbol'] in preserve_symbols or re.fullmatch('[0-9]+', src)):
            value, status = src, 'preserved_nontranslation'
        # Text that is already English in the Japanese edition stays English.
        if value is None and re.fullmatch(r'[\x20-\x7e]*[A-Za-z][\x20-\x7e]*', re.sub(r'\{[^}]+\}', '', src)):
            value, status = src, 'preserved_english_original'
        if value is None and row['symbol'].startswith('LOC_OPPONENT_SELECT_') and row['symbol'].endswith('_DESCRIPTION'):
            value, status = src, 'translated_profile_template'
            for jp, ko in replacements.items():
                value = value.replace(jp, ko)
        if value is None:
            missing.append(row['id'])
        else:
            if collections.Counter(re.findall(r'\{[^}]+\}', src)) != collections.Counter(re.findall(r'\{[^}]+\}', value)):
                errors.append({'id': row['id'], 'error': 'control token mismatch'})
            if '=' in src and value.count('=') != src.count('='):
                errors.append({'id': row['id'], 'error': 'button glyph mismatch'})
            if re.search(r'[\u3040-\u30ff\u3400-\u9fff]', value):
                errors.append({'id': row['id'], 'error': 'Japanese residue'})
        output.append({**row, 'translation': value, 'status': status})
    report = {'total': len(ROWS), 'status_counts': dict(collections.Counter(r['status'] for r in output)),
              'missing': missing, 'errors': errors,
              'hangul_syllables': len({c for r in output for c in (r['translation'] or '') if '\uac00' <= c <= '\ud7a3'}),
              'in_game_layout_verified': False}
    (WORK / 'translated-texts.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'manifests/translation-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert not missing and not errors

if __name__ == '__main__':
    main()
