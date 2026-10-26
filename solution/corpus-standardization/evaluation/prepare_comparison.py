"""Pair independently selected source positions; hide method names for annotation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sqlite3


def connect(directory):
    db = sqlite3.connect((Path(directory).resolve() / 'corpus.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def get_side(db, path, anchor):
    source = db.execute('SELECT * FROM sources WHERE relpath=?', (path,)).fetchone()
    if source is None:
        raise ValueError(f'Missing source: {path}')
    candidates = db.execute('SELECT * FROM chunks WHERE source_id=? AND start_cp<=? AND end_cp>?',
                            (source['source_id'], anchor, anchor)).fetchall()
    if not candidates:
        raise ValueError(f'Uncovered anchor: {path}:{anchor}')
    row = min(candidates, key=lambda c: (abs((c['start_cp'] + c['end_cp']) / 2 - anchor), c['start_cp']))
    raw = source['raw_text']
    structure = json.loads(row['structure_json']) if 'structure_json' in row.keys() else {}
    headings = structure.get('heading_path', [])
    return source, {
        'chunk_id': row['chunk_id'], 'start': row['start_cp'], 'end': row['end_cp'],
        'text': raw[row['start_cp']:row['end_cp']],
        'heading': headings, 'structure': structure,
        'reading_start': row['reading_start_cp'], 'reading_end': row['reading_end_cp'],
        'reading_text': raw[row['reading_start_cp']:row['reading_end_cp']],
    }


def prepare(positions, old_directory, new_directory, output):
    selected = json.loads(Path(positions).read_text(encoding='utf-8-sig'))
    old_db, new_db = connect(old_directory), connect(new_directory)
    randomizer = random.Random(104729)
    pairs, blind, key = [], [], {}
    try:
        for item in selected['items']:
            path, anchor = item['path'], item['anchor']
            source, old = get_side(old_db, path, anchor)
            newer, new = get_side(new_db, path, anchor)
            if source['raw_text'] != newer['raw_text']:
                raise ValueError(f'Source changed between methods: {path}')
            raw = source['raw_text']
            left = max(source['body_start'], min(old['start'], new['start']) - 900)
            right = min(len(raw), max(old['end'], new['end']) + 900)
            common = {'id': item['id'], 'path': path, 'title': source['title'],
                      'collection': item['collection'], 'anchor': anchor,
                      'form': item.get('form', item.get('forms', [])),
                      'context_start': left, 'context_end': right, 'source_context': raw[left:right]}
            pair = {**common, 'old': old, 'new': new,
                    'annotation': {'verdict': 'undetermined', 'reason': '尚未标注'},
                    'review': {'status': 'pending'}}
            pairs.append(pair)
            names = ['old', 'new']
            randomizer.shuffle(names)
            key[item['id']] = dict(zip(['A', 'B'], names))
            sides = {}
            for label, method in key[item['id']].items():
                side = pair[method]
                sides[label] = {k: side[k] for k in ('start', 'end', 'text', 'heading',
                                                    'reading_start', 'reading_end', 'reading_text')}
            blind.append({**common, **sides})
    finally:
        old_db.close()
        new_db.close()
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    def save(name, value):
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    save('comparison.json', {
        'summary': {'total': len(pairs), 'improved': 0, 'regressed': 0, 'tied': 0, 'undetermined': len(pairs)},
        'methodology': {
            'old': '固定600字，重叠100字；阅读上下文最多1200字',
            'new': '按章、条目和注释关系切分；长条再分段，单片段最多1200字',
            'sampling': '固定种子，二王及高/中/低频四组各8个原文位置；不按切分效果挑样本',
            'scoring': '匿名A/B；缺条头、断注、正文注释脱离、无关条混入、正文截断各0/1/2，越低越好。主评片段及提供的条头；阅读上下文单独备注。',
            'limits': 'AI结构标注与主agent复核，不是人工金标准或DeepSeek效果评测；等量来源组样本不代表全库字数加权表现。长度和结构可能使方法被猜出。',
        }, 'items': pairs})
    save('blind_packets.json', {'instructions': '按RUBRIC.md独立评分。不要读取comparison.json或method_key.json；只评材料实际提供的信息，不猜方法。', 'items': blind})
    save('method_key.json', key)
    print(json.dumps({'samples': len(pairs), 'output': str(destination)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--positions', required=True)
    parser.add_argument('--old', required=True)
    parser.add_argument('--new', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    prepare(args.positions, args.old, args.new, args.output)
