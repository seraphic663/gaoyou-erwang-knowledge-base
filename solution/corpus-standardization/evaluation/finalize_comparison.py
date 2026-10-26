"""Join anonymous ratings and explicit review notes into the local comparison."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

DIMENSIONS = ('missing_heading', 'cut_note', 'detached_note', 'unrelated', 'cut_body')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def finalize(directory, annotation_paths, review_path=None):
    directory = Path(directory)
    data, keys = read(directory / 'comparison.json'), read(directory / 'method_key.json')
    annotations = {}
    for path in annotation_paths:
        for item in read(path)['items']:
            if item['id'] in annotations:
                raise ValueError(f'Duplicate annotation: {item["id"]}')
            for side in ('A', 'B'):
                scores = item[side]['scores']
                if set(scores) != set(DIMENSIONS) or any(v not in (0, 1, 2, None) for v in scores.values()):
                    raise ValueError(f'Invalid scores: {item["id"]}')
            annotations[item['id']] = item
    if set(annotations) != {item['id'] for item in data['items']}:
        raise ValueError('Annotations and selected positions differ')
    reviews = {item['id']: item for item in read(review_path)['items']} if review_path else {}
    for item in data['items']:
        rated, key = annotations[item['id']], keys[item['id']]
        preferred = rated['preferred']
        if preferred in ('A', 'B'):
            verdict = 'improved' if key[preferred] == 'new' else 'regressed'
        elif preferred in ('tie', 'undetermined'):
            verdict = 'tied' if preferred == 'tie' else 'undetermined'
        else:
            raise ValueError(f'Invalid preferred: {preferred}')
        annotation = {key[label]: rated[label] for label in ('A', 'B')}
        annotation.update(verdict=verdict, reason=rated['reason'], reading_note=rated.get('reading_note', ''))
        item['initial_annotation'] = annotation
        item['annotation'] = dict(annotation)
        item['review'] = {'status': 'not_reviewed', 'note': 'Luna匿名初评，尚未由主agent复核'}
        if item['id'] in reviews:
            review = reviews[item['id']]
            for field, value in review.get('annotation', {}).items():
                if field in ('old', 'new'):
                    original = item['annotation'][field]
                    item['annotation'][field] = {**original, **value,
                        'scores': {**original['scores'], **value.get('scores', {})}}
                else:
                    item['annotation'][field] = value
            item['review'] = {k: v for k, v in review.items() if k not in ('id', 'annotation')}
        for method in ('old', 'new'):
            item['annotation'][method]['uncertain'] = any(value is None for value in item['annotation'][method]['scores'].values())
    counts = Counter(item['annotation']['verdict'] for item in data['items'])
    initial = Counter(item['initial_annotation']['verdict'] for item in data['items'])
    summary = {'total': len(data['items']), **{k: counts[k] for k in ('improved', 'regressed', 'tied', 'undetermined')},
               'initial_verdicts': dict(initial), 'reviewed': len(reviews),
               'changed_verdict_ids': [i['id'] for i in data['items'] if i['annotation']['verdict'] != i['initial_annotation']['verdict']]}
    summary['lengths'] = {method: {'mean': round(statistics.mean(len(i[method]['text']) for i in data['items']), 1),
                                 'median': statistics.median(len(i[method]['text']) for i in data['items']),
                                 'min': min(len(i[method]['text']) for i in data['items']),
                                 'max': max(len(i[method]['text']) for i in data['items'])}
                          for method in ('old', 'new')}
    summary['dimensions'] = {}
    for dim in DIMENSIONS:
        paired = [i for i in data['items'] if all(i['annotation'][m]['scores'][dim] is not None for m in ('old', 'new'))]
        summary['dimensions'][dim] = {'paired_count': len(paired), **{
            method: {'problem_count': sum(i['annotation'][method]['scores'][dim] > 0 for i in paired),
                     'severe_count': sum(i['annotation'][method]['scores'][dim] == 2 for i in paired)}
            for method in ('old', 'new')}}
    data['summary'] = summary
    (directory / 'comparison.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--annotations', nargs='+', required=True)
    parser.add_argument('--reviews')
    args = parser.parse_args()
    finalize(args.directory, args.annotations, args.reviews)
