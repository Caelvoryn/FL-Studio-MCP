"""Offline read-failure tests. These never count as real FL acceptance."""
from types import SimpleNamespace

import pytest

from fl_studio_mcp.tools import plugin
from fl_studio_mcp.connection import FLBridgeError


def reader(monkeypatch, call):
    functions={}
    class Registry:
        def tool(self, **kwargs):
            def record(fn):
                functions[fn.__name__]=fn
                return fn
            return record
    monkeypatch.setattr(plugin,'get_bridge',lambda:SimpleNamespace(call=call))
    plugin.register(Registry())
    return functions['fl_plugin_state']


def test_complete_snapshot_falls_back_to_real_single_replies(monkeypatch):
    calls=[]
    def call(command,args=None):
        calls.append((command,args))
        if command=='get_play_state':return {'playing':False}
        if command==plugin.protocol.CMD_PLUGIN_GET_PARAMS:
            if args['start']:raise FLBridgeError('timeout')
            return dict(plugin='Sytrus',total=3,params=[dict(i=0,v=.2)],next_start=1)
        return dict(param=args['param'],v=args['param']/10,name='observed',s='actual')
    result=reader(monkeypatch,call)(0,-1,complete=True)
    assert result['ok'] and result['readback']['snapshot_atomic'] is False
    assert [p['v'] for p in result['readback']['params']]==[.2,.1,.2]
    assert [args['param'] for cmd,args in calls if cmd==plugin.protocol.CMD_PLUGIN_GET_PARAM]==[1,2]


def test_snapshot_rejects_wrong_single_index(monkeypatch):
    def call(command,args=None):
        if command=='get_play_state':return {'playing':False}
        if command==plugin.protocol.CMD_PLUGIN_GET_PARAMS:
            if args['start']:raise FLBridgeError('timeout')
            return dict(plugin='Sytrus',total=2,params=[dict(i=0,v=.2)],next_start=1)
        return dict(param=0,v=.9)
    result=reader(monkeypatch,call)(0,-1,complete=True)
    assert not result['ok'] and result['error']['code']=='PLUGIN_RESPONSE_MISMATCH'


def test_snapshot_refuses_playing_transport(monkeypatch):
    result=reader(monkeypatch,lambda *args:dict(playing=True))(0,-1,complete=True)
    assert not result['ok'] and result['error']['code']=='INVALID_READ_STATE'


def test_snapshot_does_not_fill_missing_indices(monkeypatch):
    def call(command,args=None):
        if command=='get_play_state':return {'playing':False}
        return dict(plugin='Sytrus',total=2,params=[dict(i=0,v=.2),dict(i=0,v=.3)],next_start=None)
    result=reader(monkeypatch,call)(0,-1,complete=True)
    assert not result['ok'] and result['error']['code']=='PARAMETER_SNAPSHOT_INCOMPLETE'


def test_filter_mismatch_refuses_before_plugin_read(monkeypatch):
    def call(command,args=None):
        assert command==plugin.protocol.CMD_CHANNEL_LIST
        return dict(total=1,channels=[dict(i=0,name='Automation')],next_start=None)
    result=reader(monkeypatch,call)(0,-1,expected_channel='Classic')
    assert not result['ok'] and result['error']['code']=='CHANNEL_FILTER_MISMATCH'


def test_filter_changed_during_read_is_not_verified(monkeypatch):
    count=0
    def call(command,args=None):
        nonlocal count
        if command==plugin.protocol.CMD_CHANNEL_LIST:
            count+=1
            return dict(total=1,channels=[dict(i=0,name='Classic' if count==1 else 'Other')],next_start=None)
        return dict(plugin='Sytrus',total=1,params=[dict(i=0,v=.2)],next_start=None)
    result=reader(monkeypatch,call)(0,-1,expected_channel='Classic')
    assert not result['ok'] and result['error']['code']=='CHANNEL_FILTER_MISMATCH'
