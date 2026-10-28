"""Optional official RPC adapter. NOT a bridge to FL-hosted Pianoteq instances.

Use only with an explicitly started, isolated Pianoteq standalone server.
FL parameter indices must never be inferred from this API's indices.
No activation, deletion, preference editing, or automatic process launching.
"""
import json
import math
import urllib.request

from .workflow import WorkflowError


class PianoteqStandalone:
    scope = 'Pianoteq standalone; NOT FL Studio'

    def __init__(self, port: int, timeout: float = 3):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Explicit loopback port1024..65535 required')
        if not 0 < timeout <= 10:
            raise ValueError('timeout must be 0..10 seconds')
        self.url = f'http://127.0.0.1:{port}/jsonrpc'
        self.timeout = timeout
        self.sequence = 0
        # Do not send local control traffic to an environment HTTP proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _call(self, method, params=None):
        self.sequence += 1
        request = urllib.request.Request(self.url, data=json.dumps(dict(jsonrpc='2.0', id=self.sequence,
            method=method, params=params or {})).encode(), headers={'Content-Type':'application/json'})
        with self.opener.open(request, timeout=self.timeout) as response:
            payload = response.read(4_000_001)
        if len(payload) > 4_000_000:
            raise WorkflowError('RPC_SIZE_LIMIT', 'Official RPC response too large')
        body = json.loads(payload)
        if body.get('id') != self.sequence or body.get('jsonrpc') != '2.0' or 'error' in body or 'result' not in body:
            raise WorkflowError('RPC_FAILED', 'Invalid/error official RPC response', response=body)
        return body['result']

    def info(self):
        result = self._call('getInfo')
        if not isinstance(result, list) or len(result) != 1 or result[0].get('vendor_name') != 'Modartt' or result[0].get('plugin_type') != 'sta':
            raise WorkflowError('RPC_IDENTITY', 'Expected official Modartt standalone instance')
        return dict(host_scope=self.scope, readback=result[0])

    def catalog(self):
        self.info()
        return dict(host_scope=self.scope, presets=self._call('getListOfPresets'),
                    limitation='Availability here does not prove availability/selection in an FL instance')

    def parameters(self):
        self.info()
        return dict(host_scope=self.scope, parameters=self._call('getParameters'))

    def load_preset(self, name: str, bank: str = ''):
        catalog = self.catalog()['presets']
        matches = [p for p in catalog if p.get('name') == name and p.get('bank') == bank]
        if len(matches) != 1:
            raise WorkflowError('PRESET_NOT_UNIQUE', 'Exact catalog name/bank required')
        if matches[0].get('license_status') != 'ok':
            raise WorkflowError('PRESET_UNAVAILABLE', 'Preset not reported as licensed/available')
        before = self.info()['readback']['current_preset']
        self._call('loadPreset', dict(name=name, bank=bank))
        after = self.info()['readback']['current_preset']
        verified = after.get('name') == name and after.get('bank') == bank and after.get('instrument') == matches[0].get('instr')
        return dict(ok=verified, verified=verified, host_scope=self.scope, before=before, after=after,
                    FL_plugin_acceptance=False, persistence_verified=False)

    def set_parameters(self, changes: list[dict]):
        if not isinstance(changes, list) or not 1 <= len(changes) <= 32:
            raise ValueError('1..32 parameter edits required')
        known = {p['id']:p for p in self.parameters()['parameters']}
        seen = set()
        for c in changes:
            if not isinstance(c, dict) or set(c) != {'id','normalized_value','expected_value'} or c['id'] in seen or c['id'] not in known:
                raise ValueError('Exact unique parameter id, expected_value and normalized_value required')
            seen.add(c['id'])
            for key in ('normalized_value','expected_value'):
                v = c[key]
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 1:
                    raise ValueError('Finite normalized value required')
            if abs(known[c['id']]['normalized_value'] - c['expected_value']) > .0001:
                raise WorkflowError('STALE_PARAMETER','Standalone parameter differs',id=c['id'])
        self._call('setParameters', {'list':[dict(id=c['id'], normalized_value=c['normalized_value']) for c in changes]})
        actual = {p['id']:p for p in self.parameters()['parameters']}
        verified = all(c['id'] in actual and abs(actual[c['id']]['normalized_value']-c['normalized_value']) < .0001 for c in changes)
        return dict(ok=verified, verified=verified, host_scope=self.scope,
                    readback=[actual.get(c['id']) for c in changes], FL_plugin_acceptance=False,
                    persistence_verified=False)
