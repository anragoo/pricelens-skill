from __future__ import annotations
import json
import re
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch
from pathlib import Path
from urllib.parse import urlsplit
from scripts import pricelens

class ClientDetailContractTests(unittest.TestCase):

    def test_multiple_details_run_concurrently_and_preserve_input_order(self) -> None:
        ids = ['pl2_first', 'pl2_second']
        gate = threading.Barrier(len(ids))

        def fake_call(path, payload):
            gate.wait(timeout=2)
            if payload['id'] == ids[0]:
                time.sleep(0.03)
            return {'ok': True, 'goods': {'id': payload['id']}}
        output = StringIO()
        with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', ['pricelens.py', 'detail', '--id', *ids]), redirect_stdout(output):
            self.assertEqual(pricelens.main(), 0)
        response = json.loads(output.getvalue())
        self.assertEqual(response, {'ok': True, 'service': 'PriceLens', 'results': [{'id': ids[0], 'result': {'ok': True, 'goods': {'id': ids[0]}}}, {'id': ids[1], 'result': {'ok': True, 'goods': {'id': ids[1]}}}]})

    def test_multiple_detail_failures_are_isolated_and_generic(self) -> None:
        ids = ['pl2_good', 'pl2_bad']

        def fake_call(path, payload):
            if payload['id'] == ids[1]:
                raise RuntimeError('private diagnostic')
            return {'ok': True, 'goods': {'id': payload['id']}}
        output = StringIO()
        with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', ['pricelens.py', 'detail', '--id', *ids]), redirect_stdout(output):
            self.assertEqual(pricelens.main(), 0)
        response = json.loads(output.getvalue())
        self.assertTrue(response['ok'])
        self.assertEqual([item['id'] for item in response['results']], ids)
        failed = response['results'][1]['result']
        self.assertEqual(failed['error']['message'], 'PriceLens 服务暂时不可用，请稍后重试。')
        self.assertNotIn('private diagnostic', json.dumps(response, ensure_ascii=False))

    def test_multiple_detail_all_failures_return_nonzero(self) -> None:
        ids = ['pl2_first', 'pl2_second']
        output = StringIO()
        with patch.object(pricelens, 'call', side_effect=RuntimeError('private diagnostic')), patch('sys.argv', ['pricelens.py', 'detail', '--id', *ids]), redirect_stdout(output):
            self.assertEqual(pricelens.main(), 2)
        response = json.loads(output.getvalue())
        self.assertFalse(response['ok'])
        self.assertEqual([item['id'] for item in response['results']], ids)
        self.assertTrue(all((not item['result']['ok'] for item in response['results'])))

    def test_detail_batch_keeps_worker_count_bounded(self) -> None:
        ids = [f'pl2_{index}' for index in range(5)]
        active = 0
        peak_active = 0
        lock = threading.Lock()

        def fake_call(path, payload):
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            try:
                time.sleep(0.03)
                return {'ok': True, 'goods': {'id': payload['id']}}
            finally:
                with lock:
                    active -= 1
        output = StringIO()
        with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', ['pricelens.py', 'detail', '--id', *ids]), redirect_stdout(output):
            self.assertEqual(pricelens.main(), 0)
        self.assertEqual(peak_active, 4)
        self.assertTrue(json.loads(output.getvalue())['ok'])

    def test_search_maps_public_marketplace_name_to_service_contract(self) -> None:
        captured = {}

        def fake_call(path, payload):
            captured['path'] = path
            captured['payload'] = payload
            return {'ok': True, 'items': []}
        with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', ['pricelens.py', 'search', '--keyword', '耳机', '--source', 'jd', '--sort', 'price']), redirect_stdout(StringIO()):
            self.assertEqual(pricelens.main(), 0)
        self.assertEqual(captured['payload'], {'keyword': '耳机', 'source': 2, 'sort': 'price'})

    def test_multiple_sources_run_concurrently_and_preserve_input_order(self) -> None:
        sources = ['jd', 'pdd', 'taobao']
        source_ids = [pricelens.PUBLIC_SOURCES[source] for source in sources]
        gate = threading.Barrier(len(sources))

        def fake_call(path, payload):
            gate.wait(timeout=2)
            if payload['source'] == source_ids[0]:
                time.sleep(0.03)
            return {'ok': True, 'echo_source': payload['source']}
        output = StringIO()
        with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', ['pricelens.py', 'search', '--keyword', '耳机', '--source', *sources]), redirect_stdout(output):
            self.assertEqual(pricelens.main(), 0)
        response = json.loads(output.getvalue())
        self.assertEqual(response, {'ok': True, 'service': 'PriceLens', 'results': [{'platform': source, 'result': {'ok': True, 'echo_source': source_id}} for source, source_id in zip(sources, source_ids)]})

    def test_multiple_search_failure_is_isolated_with_public_platform_name(self) -> None:
        sources = ['jd', 'pdd']

        def fake_call(path, payload):
            if payload['source'] == pricelens.PUBLIC_SOURCES['pdd']:
                raise RuntimeError('private diagnostic')
            return {'ok': True, 'items': []}
        output = StringIO()
        with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', ['pricelens.py', 'search', '--keyword', '耳机', '--source', *sources]), redirect_stdout(output):
            self.assertEqual(pricelens.main(), 0)
        response = json.loads(output.getvalue())
        self.assertTrue(response['ok'])
        self.assertEqual([item['platform'] for item in response['results']], sources)
        failed = response['results'][1]['result']
        self.assertEqual(failed['error']['message'], 'PriceLens 服务暂时不可用，请稍后重试。')
        self.assertNotIn('private diagnostic', json.dumps(response, ensure_ascii=False))

    def test_search_forwards_explicit_price_bounds_only_when_set(self) -> None:
        cases = ((['--min-price', '100', '--max-price', '500'], {'min_price': '100', 'max_price': '500'}), (['--max-price', '500'], {'max_price': '500'}), (['--min-price', '100'], {'min_price': '100'}), ([], {}))
        for price_args, expected_bounds in cases:
            with self.subTest(price_args=price_args):
                captured = {}

                def fake_call(path, payload):
                    captured['path'] = path
                    captured['payload'] = payload
                    return {'ok': True, 'items': []}
                argv = ['pricelens.py', 'search', '--keyword', '耳机', '--source', 'jd', *price_args]
                with patch.object(pricelens, 'call', side_effect=fake_call), patch('sys.argv', argv), redirect_stdout(StringIO()):
                    self.assertEqual(pricelens.main(), 0)
                self.assertEqual(captured['path'], '/v1/search')
                self.assertEqual(captured['payload'], {'keyword': '耳机', 'source': 2, 'sort': 'default', **expected_bounds})

    def test_search_rejects_invalid_or_reversed_price_bounds_before_request(self) -> None:
        invalid_args = (['--min-price', '-1'], ['--max-price', 'NaN'], ['--min-price', 'Infinity'], ['--max-price', '1e999999999'], ['--max-price', '1e-999999999'], ['--min-price', '1' * 65], ['--min-price', '501', '--max-price', '500'])
        for price_args in invalid_args:
            with self.subTest(price_args=price_args):
                with patch.object(pricelens, 'call') as call, patch('sys.argv', ['pricelens.py', 'search', '--keyword', '耳机', '--source', 'jd', *price_args]), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        pricelens.main()
                self.assertEqual(raised.exception.code, 2)
                call.assert_not_called()

    def test_network_failure_hides_url_and_exception_details(self) -> None:
        with patch.object(pricelens.urllib.request, 'urlopen', side_effect=pricelens.urllib.error.URLError('secret diagnostic')):
            result = pricelens.call('/v1/search', {'keyword': '耳机'})
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertIn('PriceLens 服务暂时不可用', serialized)
        self.assertNotIn('secret diagnostic', serialized)
        self.assertNotIn('127.0.0.1', serialized)

    def test_api_error_details_are_not_forwarded_to_client(self) -> None:
        with patch.object(pricelens.urllib.request, 'urlopen') as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = json.dumps({'ok': False, 'error': {'code': 'DETAIL_UNAVAILABLE', 'message': 'private diagnostic'}}).encode()
            result = pricelens.call('/v1/detail', {'id': 'pl2_opaque'})
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn('DETAIL_UNAVAILABLE', serialized)
        self.assertNotIn('private diagnostic', serialized)

    def test_client_and_skill_metadata_are_versioned_together(self) -> None:
        root = Path(__file__).resolve().parents[1]
        metadata = json.loads((root / '_meta.json').read_text(encoding='utf-8'))
        skill = (root / 'SKILL.md').read_text(encoding='utf-8')
        self.assertEqual(pricelens.CLIENT_VERSION, '3.4.6')
        self.assertEqual(metadata['version'], '3.4.6')
        self.assertIn('version: 3.4.6', skill)
