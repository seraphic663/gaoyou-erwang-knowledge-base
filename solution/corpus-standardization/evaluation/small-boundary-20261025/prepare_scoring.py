"""Package completed outputs without exposing experimental conditions to raters."""
import json
import random
from pathlib import Path

P = Path(__file__).resolve().parent
RUN = P / 'runs' / '20261025T113349Z'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
refs = {x['id']: x for x in read(P / 'hidden_reference.json')['items']}
texts = {x['id']: x for x in read(P / 'public_inputs.json')['items']}
rng = random.Random(202610254)
keys = {}
for cid in sorted(refs):
    variants = [(c, r) for c in ('tagged', 'untagged') for r in (1, 2)]
    rng.shuffle(variants)
    for label, (condition, repeat) in zip('ABCD', variants):
        keys[f'{cid}-{label}'] = {'id': cid, 'condition': condition, 'repeat': repeat}
inverse = {(v['id'], v['condition'], v['repeat']): k for k, v in keys.items()}
latest = {}
for line in (RUN / 'attempts.jsonl').read_text(encoding='utf-8').splitlines():
    row = json.loads(line)
    if not row['will_retry']:
        latest[(row['id'], row['condition'], row['repeat'])] = row
packets = {'a': [], 'b': []}
group_a = {'luna-01','luna-02','luna-03','luna-04','luna-05','SOL01','SOL02','SOL03','SOL04','SOL05'}
for key, row in latest.items():
    cid = row['id']
    group = 'a' if cid in group_a else 'b'
    packets[group].append({'response_id': inverse[key], 'case_id': cid,
                          'source': texts[cid], 'reference': refs[cid],
                          'answer': row['parsed_output'], 'outcome': row['outcome'],
                          'format_issues': row['format_issues']})
for group, rows in packets.items():
    rows.sort(key=lambda x: x['response_id'])
    (P / f'scoring_packet_{group}.json').write_text(json.dumps({'items': rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(P / 'scoring_key.json').write_text(json.dumps(keys,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print({group: len(rows) for group, rows in packets.items()})
