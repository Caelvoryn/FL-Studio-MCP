"""Measured native UI anchors + image grid lines + native OCR. Fail closed."""
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import os

import numpy as np
from PIL import Image, ImageOps

from .workflow import WorkflowError, atomic_json, state_dir


def runs(values, gap=1):
    values = np.asarray(values)
    return [g for g in np.split(values, np.where(np.diff(values) > gap)[0] + 1) if len(g)]


def ocr(image, path):
    image.save(path)
    atomic_json(path.with_suffix('.launch.json'),dict(executable=sys.executable,base_executable=sys._base_executable,
                 python_environment={k:v for k,v in os.environ.items() if k.startswith('PYTHON') or k.startswith('VIRTUAL')}))
    try:
        environment=dict(os.environ, PYTHONPATH=str(Path(sys.prefix)/'Lib'/'site-packages'), PYTHONNOUSERSITE='1')
        process = subprocess.run([sys._base_executable, str(Path(__file__).with_name('ocr_worker.py')), str(path.resolve())],
                                 capture_output=True, text=True, encoding='utf8', timeout=20,
                                 stdin=subprocess.DEVNULL,env=environment,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        detail=exc.stderr.decode('utf8',errors='replace') if isinstance(exc.stderr,bytes) else exc.stderr
        path.with_suffix('.timeout.txt').write_text(detail or 'No worker traceback',encoding='utf8')
        raise WorkflowError('OCR_TIMEOUT', 'Native OCR exceeded 20 seconds',diagnostic=str(path.with_suffix('.timeout.txt'))) from exc
    if process.returncode:
        raise WorkflowError('OCR_UNAVAILABLE', 'Native OCR dependency/language failed', detail=process.stderr[-1200:])
    return json.loads(process.stdout)


def compact_labels(image, boxes, path):
    """Tile only observed pixels with whitespace; never invent recognition text."""
    if not boxes:
        raise WorkflowError('LABELS_UNRECOGNIZED','No visible label pixels; reobserve and restore viewport before retrying')
    numeric=bool(boxes) and all(inverse for _,inverse in boxes)
    tile_width=max(round((box[2]-box[0])*min(5.,80/max(1,box[3]-box[1]))) for box,_ in boxes)+(6 if numeric else 30)
    canvas = Image.new('RGB', (max(300, len(boxes)*tile_width+40), 160), 'white')
    tiles = []
    for index, (box, inverse) in enumerate(boxes):
        crop = ImageOps.autocontrast(image.crop(box).convert('L'))
        if inverse:
            crop = ImageOps.invert(crop)
        scale = min(5., 80/max(1, crop.height))
        crop = crop.resize((max(1, round(crop.width*scale)), max(1, round(crop.height*scale))))
        x = 20 + index*tile_width
        canvas.paste(crop, (x, 30))
        tiles.append((x, x+crop.width, box))
    if not numeric and max(box[2]-box[0] for box,_ in boxes)<40 and canvas.width*2<=2400:
        # Sparse two-word octave labels are rejected by native OCR in some
        # views. Repeat the same observed pixels, never synthesized labels.
        width=canvas.width
        repeated=Image.new('RGB',(width*2,canvas.height),'white')
        repeated.paste(canvas,(0,0));repeated.paste(canvas,(width,0));canvas=repeated
        tiles += [(left+width,right+width,box) for left,right,box in list(tiles)]
    results = ocr(canvas, path)
    matched = []
    for result in results:
        for word in result['words']:
            covered = [i for i,(left,right,_) in enumerate(tiles)
                       if min(right,word['x']+word['width']) > max(left,word['x'])]
            text = word['text'].strip()
            if len(covered) == 1:
                matched.append((covered[0]%len(boxes), text, result['language']))
            elif text.isdecimal() and len(text) == len(covered):
                matched.extend((i,char,result['language']) for i,char in zip(covered,text))
    return matched, results


def fit_axis(points, minimum=3):
    """Consensus, not an assumed ruler origin. Reject inconsistent OCR labels."""
    best = None
    for a,b in itertools.combinations(points,2):
        if a[0] == b[0] or a[1] == b[1]:
            continue
        slope = (b[1]-a[1])/(b[0]-a[0])
        if slope <= 0:
            continue
        intercept = a[1]-a[0]*slope
        accepted = {(value,pixel) for value,pixel in points if abs(pixel-(intercept+value*slope)) <= 1.1}
        count = len({value for value,_ in accepted})
        if best is None or count > best[0]:
            best = (count,slope,intercept,sorted(accepted))
    if best is None or best[0] < minimum:
        raise WorkflowError('RULER_UNRECOGNIZED', 'Insufficient consistent OCR ruler anchors', observed=points)
    _,slope,intercept,accepted = best
    values=np.array([p[0] for p in accepted],dtype=float)
    pixels=np.array([p[1] for p in accepted],dtype=float)
    slope=float(np.sum((values-values.mean())*(pixels-pixels.mean()))/np.sum((values-values.mean())**2))
    intercept=float(pixels.mean()-slope*values.mean())
    return slope,intercept,accepted


def locate_text(image, phrase, folder):
    """Exact observed word/span matching. Ambiguous text never selects a guess."""
    folder.mkdir(parents=True,exist_ok=True)
    def norm(text):
        return ''.join(c.casefold() for c in text if not c.isspace() and not 0xE000<=ord(c)<=0xF8FF)
    wanted=norm(phrase)
    if not wanted:
        raise WorkflowError('INVALID_ARGUMENT','Nonempty visible text required')
    scale=min(4.,2400/max(image.size))
    resized=image.resize((round(image.width*scale),round(image.height*scale)))
    candidates=[]
    records=[]
    for variant,prepared in [('normal',resized),('contrast',ImageOps.invert(ImageOps.autocontrast(resized.convert('L'))).convert('RGB'))]:
        result=ocr(prepared,folder/('text-'+variant+'.png'));records.append(result)
        for language in result:
            lines={}
            for word in language['words']:
                lines.setdefault(word.get('line',0),[]).append(word)
            for words in lines.values():
                words.sort(key=lambda w:w['x'])
                for start in range(len(words)):
                    for end in range(start+1,min(len(words),start+8)+1):
                        span=words[start:end]
                        if norm(''.join(w['text'] for w in span))==wanted:
                            x0=min(w['x'] for w in span);x1=max(w['x']+w['width'] for w in span)
                            y0=min(w['y'] for w in span);y1=max(w['y']+w['height'] for w in span)
                            point=((x0+x1)/2/scale,(y0+y1)/2/scale)
                            if not any(abs(point[0]-p[0])<8 and abs(point[1]-p[1])<8 for p in candidates):candidates.append(point)
    atomic_json(folder/'text-location.json',dict(phrase=phrase,candidates=candidates,ocr=records))
    if len(candidates)!=1:
        raise WorkflowError('TEXT_UNRECOGNIZED' if not candidates else 'AMBIGUOUS_TEXT','Need one actual visible text target',phrase=phrase,candidates=candidates)
    x,y=candidates[0]
    return [x/(image.width-1),y/(image.height-1)]


def native_piano_anchors(window):
    rect = window.rectangle()
    children = window.children()
    horizontal = [c.rectangle() for c in children if c.class_name()=='TQuickScroller' and c.rectangle().width()>4*c.rectangle().height()]
    vertical = [c.rectangle() for c in children if c.class_name()=='TNumBar' and c.rectangle().height()>4*c.rectangle().width()]
    keyboard = [c.rectangle() for c in children if c.class_name()=='TWPControl'
                and c.rectangle().left<rect.left+rect.width()/3 and c.rectangle().top<rect.top+rect.height()/3]
    if len(horizontal)!=1 or not vertical or len(keyboard)!=1:
        raise WorkflowError('ANCHOR_UNRECOGNIZED', 'Piano native scrollbar/keyboard anchors unavailable')
    h, v, k = horizontal[0], max(vertical,key=lambda r:r.height()), keyboard[0]
    return dict(left=h.left-rect.left+1,right=h.right-rect.left-1,top=k.bottom-rect.top-1,
                bottom=v.bottom-rect.top-1,ruler_top=h.bottom-rect.top,scale=h.height()/21,
                keyboard_left=k.left-rect.left)


def infer_piano(image, anchors, ppq, folder):
    image=image.convert('RGB');gray=np.asarray(image.convert('L'))
    left,right,top,bottom=(anchors[k] for k in ('left','right','top','bottom'))
    scale=anchors['scale']
    if not (0<left<right<image.width and 0<top<bottom<image.height):
        raise WorkflowError('ANCHOR_UNRECOGNIZED','Grid bounds do not fit screenshot')
    row=np.median(gray[top:bottom,left+3:right-3],axis=1)
    lines=np.flatnonzero((row[1:-1]<row[:-2]-1)&(row[1:-1]<row[2:]-1))+top+1
    if len(lines)<6:
        raise WorkflowError('GRID_UNRECOGNIZED','Insufficient pitch grid lines')
    step=float(np.median(np.diff(lines)))
    if step<4 or np.mean(np.abs(np.diff(lines)-step)<1)<.85:
        raise WorkflowError('GRID_UNRECOGNIZED','Pitch grid spacing inconsistent')
    key_left=max(anchors['keyboard_left'],left-round(24*scale))
    key_right=left-max(2,round(2*scale))
    dark=(gray[top+2:bottom,key_left:key_right]<100).any(axis=1)
    label_runs=[g+top+2 for g in runs(np.flatnonzero(dark),gap=2) if 4*scale<=len(g)<=18*scale]
    boxes=[((key_left,int(g[0])-1,key_right,int(g[-1])+2),False) for g in label_runs]
    if not boxes:
        raise WorkflowError('PITCH_UNRECOGNIZED','No visible octave labels')
    pitch_labels,pitch_ocr=compact_labels(image,boxes,folder/'pitch-labels.png')
    pitch=[]
    for index,text,language in pitch_labels:
        match=re.fullmatch(r'[Cc]([0-9])',text)
        if match:
            near=[int(y) for y in lines if abs(y-label_runs[index][0])<=step/2]
            if near:
                boundary=min(near,key=lambda y:abs(y-label_runs[index][0]))
                pitch.append((int(match[1])*12,boundary+step/2))
    pitch=list(set(pitch))
    if not pitch:
        raise WorkflowError('PITCH_UNRECOGNIZED','Native OCR could not identify octave',ocr=pitch_ocr)
    if any(abs((a[0]-b[0])*step+(a[1]-b[1]))>1 for a,b in itertools.combinations(pitch,2)):
        raise WorkflowError('PITCH_UNRECOGNIZED','Octave labels disagree with measured semitone grid')
    y0=anchors['ruler_top']+round(3*scale); y1=y0+round(16*scale)
    mask=gray[y0:y1,left:right]>80
    groups=runs(np.flatnonzero(mask.any(axis=0)),gap=max(3,round(8*scale)))
    groups=[g for g in groups if 1<=len(g)<35*scale]
    ruler_boxes=[((left+int(g[0]),y0,left+int(g[-1])+1,y1),True) for g in groups]
    ruler_labels,ruler_ocr=compact_labels(image,ruler_boxes,folder/'time-labels.png')
    column=np.median(gray[top+2:bottom-2,left:right],axis=0)
    points=[]
    for index,text,language in ruler_labels:
        if re.fullmatch(r'[0-9]{1,4}',text) and int(text)>0:
            start=left+int(groups[index][0]); lo=max(left,start-round(5*scale)); hi=min(right,start+1)
            x=lo+int(np.argmin(column[lo-left:hi-left]))
            points.append((int(text),x))
    pixels_per_bar,intercept,accepted=fit_axis(points)
    if pixels_per_bar<8*scale:
        raise WorkflowError('INSUFFICIENT_ZOOM','Time ruler too dense for precise GUI editing')
    # Actual 4/4 acceptance profile; never claim arbitrary time-signature support.
    bar,pixel=accepted[0]
    grid=dict(tick_zero_x=pixel,tick_zero=(bar-1)*4*ppq,pixels_per_tick=pixels_per_bar/(4*ppq),
              pitch_zero_y=pitch[0][1],pitch_zero=pitch[0][0],pixels_per_semitone=step,
              grid_top=top,grid_bottom=bottom,grid_right=right)
    return dict(grid=grid,anchors=anchors,octave_anchors=pitch,time_anchors=accepted,
                pixels_per_bar=pixels_per_bar,ticks_per_bar=4*ppq,ocr=dict(pitch=pitch_ocr,ruler=ruler_ocr),
                limitation='4/4, current visible grid and recognized octave/ruler; unsupported images fail closed')


def locate_piano(desktop, observation, handle):
    from .native import inspect
    from .ui_first import visible_windows
    row=next((r for r in observation['windows'] if r['handle']==str(handle)),None)
    if any(r['class'].startswith('TQuickPopup') for r in observation['windows']):
        raise WorkflowError('GUI_POPUP_BLOCKED','Close/resolve observed popup before automatic grid recognition')
    if not row or not row['title'].startswith(('钢琴卷帘','Piano roll')) or not row.get('image'):
        raise WorkflowError('EDITOR_UNRECOGNIZED','Observed Piano Roll required')
    window=visible_windows(desktop).get(str(handle))
    if window is None:
        raise WorkflowError('WINDOW_CHANGED','Observed editor disappeared')
    session=desktop.session(focus=False)
    folder=Path(row['image']).parent
    try:
        result=infer_piano(Image.open(row['image']),native_piano_anchors(window),inspect(session['path'])['ppq'],folder)
    except WorkflowError as exc:
        atomic_json(folder/'piano-locate-failure.json',exc.result())
        raise
    atomic_json(folder/'piano-location.json',result)
    return result


def locate_playlist(desktop, observation=None, window=None):
    """Automatic origin/scale/uniform-lane measurement; no guessed scroll offset."""
    from .ui_first import observe
    desktop.session()
    if observation is None:
        window=desktop.show_playlist()
        observation=observe(desktop)
    if window is None:
        raise WorkflowError('EDITOR_UNRECOGNIZED','Observed Playlist window required')
    if any(r['class'].startswith('TQuickPopup') for r in observation['windows']):
        raise WorkflowError('GUI_POPUP_BLOCKED','Resolve popup before Playlist measurement')
    row=next(r for r in observation['windows'] if r['handle']==str(window.handle))
    image=Image.open(row['image']).convert('RGB');gray=np.asarray(image.convert('L'))
    folder=Path(row['image']).parent;rect=window.rectangle()
    h=next((c.rectangle() for c in window.children() if c.class_name()=='TQuickScroller'),None)
    headers=[c.rectangle() for c in window.children() if c.class_name()=='TWPControl' and c.rectangle().right<=h.left+5] if h else []
    if h is None or len(headers)!=1:
        raise WorkflowError('ANCHOR_UNRECOGNIZED','Playlist native timeline/track-header anchors unavailable')
    header=headers[0];scale=h.height()/21
    left=h.left-rect.left+1;right=h.right-rect.left-1;top=header.bottom-rect.top
    header_left=header.left-rect.left;header_right=header.right-rect.left
    trace=np.median(gray[top:image.height-24,header_left+round(3*scale):header_right-round(20*scale)],axis=1)
    borders=np.flatnonzero(abs(np.diff(trace))>2)+top+1
    groups=runs(borders,gap=max(1,round(3*scale)))
    boundaries=np.array([int(g[0]) for g in groups])
    if len(boundaries)<3:
        raise WorkflowError('TRACKS_UNRECOGNIZED','Need three consistent visible lane boundaries')
    height=float(np.median(np.diff(boundaries)))
    if np.mean(abs(np.diff(boundaries)-height)<2)<.9 or abs(boundaries[0]-top-height)>2:
        raise WorkflowError('TRACKS_UNRECOGNIZED','Nonuniform or vertically scrolled tracks require recovery')
    tops=[top,*boundaries.tolist()][:4]
    boxes=[((header_left,int(y),header_right,int(y+22*scale)),False) for y in tops]
    labels,track_ocr=compact_labels(image,boxes,folder/'track-labels.png')
    track_points=[]
    for index in range(len(boxes)):
        text=' '.join(text for i,text,_ in labels if i==index)
        found=re.search(r'Track\s*([0-9]+)',text,re.IGNORECASE)
        if found:track_points.append((int(found[1]),tops[index]))
    if len(track_points)<2 or any(abs(y-(top+(number-1)*height))>2 for number,y in track_points):
        raise WorkflowError('TRACKS_UNRECOGNIZED','Cannot verify track1 origin from actual labels',observed=track_points)
    y0=h.bottom-rect.top+round(3*scale);y1=y0+round(16*scale)
    groups=runs(np.flatnonzero((gray[y0:y1,left:right]>80).any(axis=0)),gap=max(3,round(7*scale)))
    groups=[g for g in groups if len(g)<40*scale]
    labels,ruler_ocr=compact_labels(image,[((left+int(g[0]),y0,left+int(g[-1])+1,y1),True) for g in groups],folder/'playlist-time-labels.png')
    column=np.median(gray[top+2:image.height-24,left:right],axis=0)
    points=[]
    for index,text,_ in labels:
        if re.fullmatch(r'[0-9]{1,4}',text) and int(text)>0:
            start=left+int(groups[index][0]);lo=max(left,start-round(6*scale));hi=min(right,start+1)
            x=lo+int(np.argmin(column[lo-left:hi-left]));points.append((int(text),x))
    perbar,intercept,accepted=fit_axis(points)
    if abs(intercept+perbar-left)>2:
        raise WorkflowError('VIEWPORT_ORIGIN_UNSUPPORTED','Playlist is not at bar1; return timeline to start before editing',anchors=accepted)
    result=dict(grid_left=float(intercept+perbar),first_track_top=float(top),pixels_per_bar=perbar,track_height=height,
                track_anchors=track_points,time_anchors=accepted,observation_token=observation['token'],
                limitation='Recognized Track labels, uniform visible lanes, bar1 origin, current 4/4 profile only')
    atomic_json(folder/'playlist-location.json',result)
    return result


def automation_value_target(image, layout, clip, points, point_index, value, ppq):
    """Locate an existing purple FL automation curve, fitting observed pixels
    against saved points. Only vertical edits: do not guess timing or flat-curve
    value scale. Unknown colors/occlusion/multiple curves fail closed.
    """
    if not isinstance(point_index,int) or not 0<=point_index<len(points) or not np.isfinite(value) or not 0<=value<=1:
        raise WorkflowError('INVALID_ARGUMENT','Existing point index and finite 0..1 value required')
    top=layout['first_track_top']+(clip['track']-1)*layout['track_height']
    bottom=top+layout['track_height']
    if top<0 or bottom>image.height-22:
        raise WorkflowError('GUI_OUT_OF_VIEW','Complete automation lane must be visible')
    rgb=np.asarray(image.convert('RGB')).astype(float)
    observed=[]
    for point in points:
        x=layout['grid_left']+(clip['position_ticks']+point['position_beats']*ppq)*layout['pixels_per_bar']/(4*ppq)
        if not 2<x<image.width-3:
            raise WorkflowError('GUI_OUT_OF_VIEW','All saved automation points must be visible for curve verification')
        # FL26 purple automation: light curve over dark purple fill.
        strip=rgb[round(top+25):round(bottom-3),round(x)-2:round(x)+3]
        mask=(strip[:,:,0]>125)&(strip[:,:,2]>strip[:,:,0]+2)&(strip[:,:,0]>strip[:,:,1]+2)
        ys=np.flatnonzero(mask.any(axis=1))
        if not len(ys) or ys.max()-ys.min()>10:
            raise WorkflowError('AUTOMATION_CURVE_UNRECOGNIZED','Need one visible light-purple curve at every saved control point')
        observed.append((point['value'],float(np.median(ys)+round(top+25)),x))
    values=np.array([p[0] for p in observed]);pixels=np.array([p[1] for p in observed])
    if np.ptp(values)<.1:
        raise WorkflowError('AUTOMATION_SCALE_UNRECOGNIZED','Flat/near-flat curve needs explicit visual calibration; no assumed vertical range')
    slope=float(np.sum((values-values.mean())*(pixels-pixels.mean()))/np.sum((values-values.mean())**2))
    intercept=float(pixels.mean()-slope*values.mean())
    if not -layout['track_height']<slope<-.5*layout['track_height'] or np.max(abs(pixels-(intercept+slope*values)))>2:
        raise WorkflowError('AUTOMATION_SCALE_UNRECOGNIZED','Observed control points disagree with saved values')
    x=observed[point_index][2];old_y=observed[point_index][1];new_y=intercept+slope*value
    if not top+25<new_y<bottom-3:
        raise WorkflowError('GUI_OUT_OF_VIEW','Requested value outside verified curve canvas')
    return dict(point=[x/(image.width-1),old_y/(image.height-1)],target=[x/(image.width-1),new_y/(image.height-1)],
                fit=dict(slope=slope,intercept=intercept,observed=observed),
                expected_value=value,value_tolerance=2/abs(slope),
                limitation='Existing visible non-flat purple curve only; vertical move, saved readback required')
