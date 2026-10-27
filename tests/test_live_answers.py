"""Opt-in tests with a real installed local model; no downloads or user documents.

STUDY_AGENT_TEST_MODEL=gemma4:e2b pytest -q tests/test_live_answers.py -s
Set STUDY_AGENT_ANSWER_REPORT to a JSON path to save synthetic results, including failures.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from time import perf_counter

import pytest

from study_agent import mac_bridge
from study_agent.embeddings import _request, ensure_local_model
from study_agent.rag import _citation_matches, _numbers, _uncited_paragraph
from study_agent.retrieval import RetrievalResult
from study_agent.search import SearchHit

CASES = json.loads((Path(__file__).parent / 'fixtures/answer_cases.json').read_text())
MODEL = os.environ.get('STUDY_AGENT_TEST_MODEL')
pytestmark = pytest.mark.skipif(not MODEL, reason='requires explicit STUDY_AGENT_TEST_MODEL')


@pytest.fixture(scope='module')
def live_report():
    assert MODEL
    digest = ensure_local_model(MODEL, 'completion')  # Fail, never silently download/skip.
    report = {'model': MODEL, 'digest': digest, 'ollama_version': _request('/api/version'),
              'synthetic_only': True, 'cases': []}
    yield report
    if path := os.environ.get('STUDY_AGENT_ANSWER_REPORT'):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_real_model_answer(case, monkeypatch, live_report) -> None:
    # Isolate answer formation from retrieval quality. The generator, local-model
    # validation, prompt, context budget, repair and bridge serialization are real.
    hits = [SearchHit('Synthetic', item['document_id'], item['text'], 1, Path('/synthetic'),
                      chunk_id=f'synthetic:{index}') for index, item in enumerate(case['sources'])]
    monkeypatch.setattr(mac_bridge, '_retrieve', lambda _: (None, [], RetrievalResult(hits)))
    original = mac_bridge.answer
    attempts = []

    def observed(*args, **kwargs):
        attempt = {'repair': bool(kwargs.get('citation_feedback'))}
        attempts.append(attempt)
        started = perf_counter()
        try:
            content = original(*args, **kwargs)
            if case.get('inject_uncited_paragraph') and len(attempts) == 1:
                # Explicit fault injection to exercise the real repair request;
                # never present this as a naturally occurring model failure.
                attempt['injected_fault'] = 'uncited_paragraph'
                content += '\n\nКонтролируемый тестовый абзац без ссылки на источник материала.'
            attempt['answer'] = content
            attempt['uncited_paragraph'] = _uncited_paragraph(content, _citation_matches(content))
            return content
        finally:
            attempt['seconds'] = round(perf_counter() - started, 3)

    monkeypatch.setattr(mac_bridge, 'answer', observed)
    started = perf_counter()
    response = mac_bridge.dispatch({'command': 'answer', 'query': case['query'],
                                    'model': MODEL, 'language': case['language']})
    row = {'id': case['id'], 'passed': False, 'seconds': round(perf_counter() - started, 3),
           'attempts': attempts, 'response': response}
    live_report['cases'].append(row)
    print(f"{case['id']}: {row['seconds']}s, {len(attempts)} attempt(s), ok={response['ok']}",
          flush=True)
    assert response['ok'], response.get('error')
    result = response['result']
    assert result['grounded'] is case['grounded']
    assert sorted(item['document_id'] for item in result['sources']) == sorted(
        case['expected_documents'])
    normalized = re.sub(r'\s+|\\,|\\!', '', result['answer']).lower()
    for group in case['term_groups']:
        assert any(term.lower() in normalized for term in group), (group, result['answer'])
    for term in case.get('forbidden', []):
        assert term.lower() not in result['answer'].lower()
    if result['grounded']:
        matches = _citation_matches(result['answer'])
        assert matches
        assert _uncited_paragraph(result['answer'], matches) is None
        assert {number for match in matches for number in _numbers(match)} == set(
            range(1, len(result['sources']) + 1))
        assert all(item['excerpt'] in hits[index].excerpt for item in result['sources']
                   for index in range(len(hits)) if item['document_id'] == hits[index].document_id)
    assert 1 <= len(attempts) <= 2
    if case.get('inject_uncited_paragraph'):
        assert len(attempts) == 2 and attempts[1]['repair']
    row['passed'] = True
