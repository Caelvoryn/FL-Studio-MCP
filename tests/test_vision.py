"""Offline localization/safety tests, never presented as real FL evidence."""
import json
import subprocess
from types import SimpleNamespace

from PIL import Image
import pytest

from fl_studio_mcp import vision, ui_first
from fl_studio_mcp.workflow import WorkflowError, atomic_json


def test_ruler_consensus_ignores_conflicting_ocr_word():
    scale,origin,anchors=vision.fit_axis([(1,78),(2,270),(3,462),(99,300),(2,270)])
    assert scale==pytest.approx(192,abs=1e-10) and origin==pytest.approx(-114,abs=1e-10)
    assert anchors==[(1,78),(2,270),(3,462)]


@pytest.mark.parametrize('points',[[],[(1,78)],[(1,78),(2,270)],[(1,100),(2,90),(3,80)],[(1,10),(2,30),(3,70)]])
def test_ambiguous_or_insufficient_ruler_stops(points):
    with pytest.raises(WorkflowError) as exc:
        vision.fit_axis(points)
    assert exc.value.code=='RULER_UNRECOGNIZED'


def test_ocr_timeout_retains_worker_diagnostic(tmp_path,monkeypatch):
    def timeout(*a,**kw):
        assert kw['stdin']==subprocess.DEVNULL
        assert kw['timeout']==20
        raise subprocess.TimeoutExpired('worker',20,stderr=b'worker traceback')
    monkeypatch.setattr(vision.subprocess,'run',timeout)
    with pytest.raises(WorkflowError) as exc:
        vision.ocr(Image.new('RGB',(10,10)),tmp_path/'labels.png')
    assert exc.value.code=='OCR_TIMEOUT'
    assert (tmp_path/'labels.timeout.txt').read_text()=='worker traceback'


def test_popup_refuses_editor_keys_before_input(tmp_path,monkeypatch):
    monkeypatch.setattr(ui_first,'state_dir',lambda:tmp_path)
    atomic_json(tmp_path/'observations'/'token'/'observation.json',dict(time=__import__('time').time(),process_id=42,title='owned',windows=[dict(handle='123',rect=[1,2,101,202])]))
    rect=SimpleNamespace(left=1,top=2,right=101,bottom=202)
    window=SimpleNamespace(rectangle=lambda:rect,handle=123)
    popup=SimpleNamespace(class_name=lambda:'TQuickPopupMenuWindow',handle=456)
    window.class_name=lambda:'TEventEditForm'
    desktop=SimpleNamespace(pid=42,session=lambda **kw:None,main=SimpleNamespace(window_text=lambda:'owned'))
    monkeypatch.setattr(ui_first,'FLDesktop',lambda:desktop)
    monkeypatch.setattr(ui_first,'visible_windows',lambda d:{'123':window,'456':popup})
    with pytest.raises(WorkflowError) as exc:
        ui_first.act('token','once','123','keys',keys=['f7'])
    assert exc.value.code=='GUI_POPUP_BLOCKED'
    assert not (tmp_path/'ui-operations'/'once.json').exists()


def test_unrecognized_native_anchors_refuse():
    window=SimpleNamespace(rectangle=lambda:SimpleNamespace(left=0,top=0,width=lambda:900,height=lambda:700),children=lambda:[])
    with pytest.raises(WorkflowError) as exc:
        vision.native_piano_anchors(window)
    assert exc.value.code=='ANCHOR_UNRECOGNIZED'


def test_empty_label_pixels_fail_before_ocr(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'ocr',lambda *a:pytest.fail('No pixels must not call OCR'))
    with pytest.raises(WorkflowError) as exc:
        vision.compact_labels(Image.new('RGB',(50,50)),[],tmp_path/'empty.png')
    assert exc.value.code=='LABELS_UNRECOGNIZED'


def test_automation_refuses_flat_curve_instead_of_guessing_scale():
    from PIL import ImageDraw
    image=Image.new('RGB',(500,450),(50,45,65))
    ImageDraw.Draw(image).line((100,125,300,125),fill=(205,190,225))
    layout=dict(first_track_top=0,track_height=300,grid_left=100,pixels_per_bar=100)
    clip=dict(track=1,position_ticks=0)
    points=[dict(position_beats=0,value=.5),dict(position_beats=8,value=.5)]
    with pytest.raises(WorkflowError) as exc:
        vision.automation_value_target(image,layout,clip,points,0,.7,96)
    assert exc.value.code=='AUTOMATION_SCALE_UNRECOGNIZED'


def test_automation_vertical_target_uses_observed_curve_values():
    from PIL import ImageDraw
    image=Image.new('RGB',(500,450),(50,45,65))
    ImageDraw.Draw(image).line((100,200,300,80),fill=(205,190,225))
    layout=dict(first_track_top=0,track_height=300,grid_left=100,pixels_per_bar=100)
    clip=dict(track=1,position_ticks=0)
    points=[dict(position_beats=0,value=.3),dict(position_beats=8,value=.8)]
    target=vision.automation_value_target(image,layout,clip,points,0,.5,96)
    assert target['point'][0]==target['target'][0]
    assert target['target'][1]==pytest.approx(152/449,abs=.003)


def test_automation_occluded_curve_refuses():
    image=Image.new('RGB',(500,450),'black')
    with pytest.raises(WorkflowError) as exc:
        vision.automation_value_target(image,dict(first_track_top=0,track_height=300,grid_left=100,pixels_per_bar=100),
            dict(track=1,position_ticks=0),[dict(position_beats=0,value=.3),dict(position_beats=8,value=.8)],0,.5,96)
    assert exc.value.code=='AUTOMATION_CURVE_UNRECOGNIZED'
