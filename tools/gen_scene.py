#!/usr/bin/env python3
"""Writes scene.rml: the words and the controls around the scripted room.

Generated so the buttons, their listeners, the state machine and the hold
animations stay in step. Run from the project root:

    python3 tools/gen_scene.py && rive . --verify

Draw order in Rive: earlier siblings draw ON TOP, so every group lists its
foreground first and its background last. The script (main.luau) knows the
slider positions too (SL_X0, SL_X1, SL_FLAME_Y, SL_HAZE_Y): keep them in step.
"""

FONT = {
    'display': ('0:31', 'Cormorant Garamond', 'SemiBold Italic'),
    'serif': ('0:32', 'Cormorant Garamond', 'Medium'),
    'mono': ('0:33', 'IBM Plex Mono', 'Medium'),
    'arabic': ('0:35', 'IBM Plex Sans Arabic', 'SemiBold'),
}

CREAM = 'FFF2E6D0'
MUTED = 'FF9C9384'
DIM = 'FF6E675C'
INK = 'FF17120E'
AMBER = 'FFF0A040'
EMBER = 'FFE07A2A'

VM = '0:900'
P = {  # view model properties
    'tool': '0:901', 'lit': '0:902', 'stencil': '0:903', 'fresh': '0:904',
    'flame': '0:905', 'haze': '0:906', 'escape': '0:907', 'escapeText': '0:908',
    'flameText': '0:909', 'hazeText': '0:910', 'caption': '0:911', 'quality': '0:912',
    'haloX': '0:913', 'haloY': '0:914', 'haloW': '0:915', 'haloH': '0:916', 'haloOn': '0:917', 'haloPress': '0:918',
}

# panel geometry (design units); the sliders are mirrored in main.luau
PX0, PW = 976, 272
X0, X1 = 1000, 1216
IW = X1 - X0
SL_FLAME_Y, SL_HAZE_Y = 492, 560

_ids = iter(range(2000, 9000))


def nid():
    return f'0:{next(_ids)}'


def bind(prop, key, conv=None, write=False, extra=''):
    c = f' converterId="{conv}"' if conv else ''
    d = ' direction="true"' if write else ''
    return f'<DataBindContext sourcePathIds="{VM}-{P[prop]}" propertyKey="{key}"{c}{d}{extra}/>'


def text(name, x, y, content, font, size, color, bound=None, spacing=0, align=None, width=None,
         color_id=None, node_id=None, ind=8):
    fid, fam, sty = FONT[font]
    sid = nid()
    pad = ' ' * ind
    ls = f' letterSpacing="{spacing}"' if spacing else ''
    if width:
        sizing = f'width="{width}" height="{int(size * 1.6)}" sizingValue="fixed" overflowValue="fitFontSize"'
    else:
        sizing = 'sizingValue="autoWidth"'
    al = f' alignValue="{align}"' if align else ''
    cid = f' id="{color_id}"' if color_id else ''
    if bound:
        run = (f'<TextValueRun styleId="{sid}" text="{content}" name="Run">\n'
               f'{pad}        {bind(bound, 268)}\n{pad}    </TextValueRun>')
    else:
        run = f'<TextValueRun styleId="{sid}" text="{content}" name="Run"/>'
    return f'''{pad}<Text x="{x}" y="{y}" {sizing}{al} name="{name}" id="{node_id or nid()}">
{pad}    <TextStylePaint fontSize="{size}" fontAssetId="{fid}" familyName="{fam}" styleName="{sty}"{ls} name="{name} Style" id="{sid}">
{pad}        <Fill name="Fill"><SolidColor colorValue="{color}" name="C"{cid}/></Fill>
{pad}    </TextStylePaint>
{pad}    {run}
{pad}</Text>'''


def rrect(name, x, y, w, h, r, fill=None, stroke=None, sw=1, ind=8, sid=None, fill_id=None,
          stroke_id=None, inner='', ox=0, oy=0):
    pad = ' ' * ind
    rad = (f' cornerRadiusTL="{r}" cornerRadiusTR="{r}" cornerRadiusBL="{r}" cornerRadiusBR="{r}"'
           f' linkCornerRadius="false"') if r else ''
    out = [f'{pad}<Shape x="{x}" y="{y}" name="{name}" id="{sid or nid()}">']
    if inner:
        out.append(f'{pad}    <Rectangle width="{w}" height="{h}" originX="{ox}" originY="{oy}"{rad} name="Path">{inner}</Rectangle>')
    else:
        out.append(f'{pad}    <Rectangle width="{w}" height="{h}" originX="{ox}" originY="{oy}"{rad} name="Path"/>')
    if fill:
        fid = f' id="{fill_id}"' if fill_id else ''
        out.append(f'{pad}    <Fill name="Fill"><SolidColor colorValue="{fill}" name="C"{fid}/></Fill>')
    if stroke:
        kid = f' id="{stroke_id}"' if stroke_id else ''
        out.append(f'{pad}    <Stroke thickness="{sw}" name="Stroke"><SolidColor colorValue="{stroke}" name="C"{kid}/></Stroke>')
    out.append(f'{pad}</Shape>')
    return '\n'.join(out)


def label(name, y, content, right_bound=None):
    parts = [text(name, X0, y, content, 'mono', 11, MUTED, spacing=2.2)]
    if right_bound:
        parts.append(text(name + ' Value', X0, y - 2, '0', 'mono', 12, CREAM, bound=right_bound,
                          align='right', width=IW))
    return parts


# ---------------------------------------------------------------------------
# ids we key or listen to

TOOL_PILL = '0:100'
TITLE, SUBTITLE = '0:103', '0:104'
KNIFE_TXT_C, ETCH_TXT_C = '0:101', '0:102'
HIT_KNIFE, HIT_ETCH = '0:110', '0:111'
HIT_GRIN, HIT_GHOUL, HIT_MASH = '0:112', '0:113', '0:114'
HIT_CANDLE, HIT_NEW = '0:115', '0:116'
CANDLE_FILL, CANDLE_STROKE = '0:120', '0:121'
CANDLE_ON_TXT, CANDLE_OFF_TXT = '0:122', '0:123'
CANDLE_DOT = '0:124'

CONV_W = '0:960'     # 0..100 -> 0..IW
CONV_X = '0:961'     # 0..100 -> X0..X1
CONV_NOT = '0:962'   # boolean negate
CONV_PRESS = '0:963' # press 0..1 -> scale 1..1.04

children = []
add = children.append

# caption and title, on top of everything
add(text('Caption', 56, 732, 'Draw with the knife.', 'display', 30, CREAM, bound='caption', width=880))
add(text('Title', 52, 18, 'Hollow', 'display', 78, CREAM, node_id=TITLE))
add(text('Subtitle', 58, 112, "CARVE IT  ·  LIGHT IT  ·  DON'T TRUST WHAT IT CASTS", 'mono', 11, MUTED, spacing=2.4, node_id=SUBTITLE))

# --- tool
children += label('Label Tool', 60, 'TOOL')
add(rrect('Hit Knife', X0, 80, IW / 2, 44, 0, fill='00000000', sid=HIT_KNIFE))
add(rrect('Hit Etch', X0 + IW / 2, 80, IW / 2, 44, 0, fill='00000000', sid=HIT_ETCH))
add(text('Knife Label', X0, 92, 'KNIFE', 'mono', 13, INK, spacing=2, align='center', width=IW / 2, color_id=KNIFE_TXT_C))
add(text('Etch Label', X0 + IW / 2, 92, 'ETCH', 'mono', 13, CREAM, spacing=2, align='center', width=IW / 2, color_id=ETCH_TXT_C))
add(f'''        <Node x="{X0 + 4}" y="84" name="Tool Pill" id="{TOOL_PILL}">
{rrect('Pill', 0, 0, IW / 2 - 8, 36, 11, fill=CREAM, ind=12)}
        </Node>''')
add(rrect('Tool Track', X0, 80, IW, 44, 14, fill='14FFFFFF', stroke='1FFFFFFF'))

# --- stencils
children += label('Label Stencils', 148, 'STENCILS  ·  AUTO-CARVE')
for i, (name, hint, hid, arabic) in enumerate([
        ('Grin', 'CLASSIC', HIT_GRIN, False),
        ('Ghoul', 'CUT + ETCH', HIT_GHOUL, False),
        ('Mashrabiya', 'مشربية', HIT_MASH, True)]):
    y = 168 + i * 50
    add(rrect(f'Hit {name}', X0, y, IW, 42, 0, fill='00000000', sid=hid))
    add(text(f'{name} Label', X0 + 16, y + 4, name, 'display', 25, CREAM))
    if arabic:
        add(text(f'{name} Hint', X0, y + 8, hint, 'arabic', 15, AMBER, align='right', width=IW - 16))
    else:
        add(text(f'{name} Hint', X0, y + 14, hint, 'mono', 10, DIM, spacing=1.6, align='right', width=IW - 16))
    add(rrect(f'{name} Button', X0, y, IW, 42, 12, fill='0FFFFFFF', stroke='1FFFFFFF'))

# --- candle
children += label('Label Candle', 330, 'CANDLE')
add(rrect('Hit Candle', X0, 350, IW, 56, 0, fill='00000000', sid=HIT_CANDLE))
add(text('Candle Light', X0, 362, 'Light the candle', 'display', 28, INK, align='center', width=IW, node_id=CANDLE_ON_TXT))
add(text('Candle Snuff', X0, 362, 'Snuff it out', 'display', 28, AMBER, align='center', width=IW, node_id=CANDLE_OFF_TXT))
add(f'''        <Shape x="{X0 + 24}" y="378" name="Candle Dot" id="{CANDLE_DOT}">
            <Ellipse width="8" height="8" name="Path"/>
            <Fill name="Fill"><SolidColor colorValue="FFFFD27A" name="C"/></Fill>
        </Shape>''')
add(rrect('Candle Button', X0, 350, IW, 56, 16, fill=AMBER, stroke='00F0A040', sw=1.5,
          fill_id=CANDLE_FILL, stroke_id=CANDLE_STROKE))

# --- sliders
for nm, y, prop, txt in [('Flame', SL_FLAME_Y, 'flame', 'flameText'), ('Haze', SL_HAZE_Y, 'haze', 'hazeText')]:
    children += label(f'Label {nm}', y - 30, nm.upper(), right_bound=txt)
    add(f'''        <Node x="{X0}" y="{y}" name="{nm} Knob" id="{nid()}">
            {bind(prop, 13, CONV_X)}
            <Shape x="0" y="0" name="Knob" id="{nid()}">
                <Ellipse width="18" height="18" name="Path"/>
                <Fill name="Fill"><SolidColor colorValue="{CREAM}" name="C"/></Fill>
            </Shape>
            <Shape x="0" y="0" name="Knob Halo" id="{nid()}">
                <Ellipse width="30" height="30" name="Path"/>
                <Fill name="Fill"><SolidColor colorValue="33F0A040" name="C"/></Fill>
            </Shape>
        </Node>''')
    add(rrect(f'{nm} Fill', X0, y - 2, IW * 0.8, 4, 2, fill=AMBER, inner=bind(prop, 20, CONV_W)))
    add(rrect(f'{nm} Track', X0, y - 2, IW, 4, 2, fill='26FFFFFF'))

# --- light escaping
children += label('Label Escape', 604, 'LIGHT ESCAPING', right_bound='escapeText')
add(rrect('Escape Fill', X0, 630, 0, 6, 3, fill=EMBER, inner=bind('escape', 20, CONV_W)))
add(rrect('Escape Track', X0, 630, IW, 6, 3, fill='1AFFFFFF'))

# --- new pumpkin
add(rrect('Hit New', X0, 684, IW, 46, 0, fill='00000000', sid=HIT_NEW))
add(text('New Label', X0, 697, 'NEW PUMPKIN', 'mono', 12, CREAM, spacing=2.4, align='center', width=IW))
add(rrect('New Button', X0, 684, IW, 46, 14, stroke='40F2E6D0', sw=1))
add(rrect('Panel Rule', X0, 664, IW, 1, 0, fill='1AFFFFFF'))

# the hover halo: the script glides it to whichever control is under the pointer
add(f'''        <Node x="1108" y="189" name="Hover Halo" id="{nid()}">
            {bind('haloX', 13)}
            {bind('haloY', 14)}
            {bind('haloOn', 18)}
            {bind('haloPress', 16, CONV_PRESS)}
            {bind('haloPress', 17, CONV_PRESS)}
            <Shape x="0" y="0" name="Halo" id="{nid()}">
                <Rectangle width="216" height="42" originX="0.5" originY="0.5" cornerRadiusTL="13" cornerRadiusTR="13" cornerRadiusBL="13" cornerRadiusBR="13" linkCornerRadius="false" name="Path" id="{nid()}">
                    {bind('haloW', 20)}
                    {bind('haloH', 21)}
                </Rectangle>
                <Fill name="Fill"><SolidColor colorValue="24F0A040" name="C"/></Fill>
                <Stroke thickness="1.5" name="Stroke"><SolidColor colorValue="B3F0A040" name="C"/></Stroke>
            </Shape>
        </Node>''')

# panel glass
add(rrect('Panel', PX0, 36, PW, 728, 24, fill='D90C0A0E', stroke='1AFFFFFF'))

# the scripted room, under everything
add('''        <LayoutComponent width="1280" height="800" styleId="0:11" name="Stage" id="0:10">
            <LayoutComponentStyle layoutWidthScaleType="1" layoutHeightScaleType="1" widthUnitsValue="3" heightUnitsValue="3" name="Stage Style" id="0:11"/>
            <ScriptedLayout scriptAssetId="0:80" name="Room" id="0:12"/>
        </LayoutComponent>''')


# ---------------------------------------------------------------------------
# state machine

def cond_num(prop, value):
    return f'''<TransitionViewModelCondition opValue="equal">
                            <TransitionPropertyViewModelComparator>
                                <BindablePropertyNumber>
                                    {bind(prop, 636)}
                                </BindablePropertyNumber>
                            </TransitionPropertyViewModelComparator>
                            <TransitionValueNumberComparator value="{value}"/>
                        </TransitionViewModelCondition>'''


def cond_bool(prop, value):
    return f'''<TransitionViewModelCondition>
                            <TransitionPropertyViewModelComparator>
                                <BindablePropertyBoolean>
                                    {bind(prop, 634)}
                                </BindablePropertyBoolean>
                            </TransitionPropertyViewModelComparator>
                            <TransitionValueBooleanComparator value="{value}"/>
                        </TransitionViewModelCondition>'''


# hand-tuned: the pill overshoots a touch and settles (easeOutBack-ish)
PILL_EASE = '<CubicEaseInterpolator x1="0.3" y1="1.45" x2="0.55" y2="1"/>'
# the candle button breathes in slowly, like a flame catching
CANDLE_EASE = '<CubicEaseInterpolator x1="0.16" y1="1" x2="0.3" y2="1"/>'


def transition(to, cond, duration, ease):
    return f'''<StateTransition stateToId="{to}" duration="{duration}" interpolationType="cubic">
                        {ease}
                        {cond}
                    </StateTransition>'''


def listener(target, name, change):
    return f'''        <StateMachineListenerSingle targetId="{target}" listenerTypeValue="click" name="{name}" id="{nid()}">
            <ListenerViewModelChange>
                {change}
            </ListenerViewModelChange>
        </StateMachineListenerSingle>'''


def set_num(prop, v):
    return f'''<BindablePropertyNumber propertyValue="{v}">
                    {bind(prop, 636, write=True)}
                </BindablePropertyNumber>'''


S_KNIFE, S_ETCH, S_UNLIT, S_LIT = '0:511', '0:512', '0:521', '0:522'
A_KNIFE, A_ETCH, A_UNLIT, A_LIT = '0:601', '0:602', '0:603', '0:604'
not_id = nid()

sm = f'''        <StateMachine name="Hollow" id="0:500">
            <StateMachineLayer name="Tool" id="0:501">
                <AnyState x="760" y="-120"/>
                <ExitState x="960" y="-120"/>
                <EntryState><StateTransition stateToId="{S_KNIFE}"/></EntryState>
                <AnimationState x="160" y="140" animationId="{A_KNIFE}" id="{S_KNIFE}">
                    {transition(S_ETCH, cond_num('tool', 1), 260, PILL_EASE)}
                </AnimationState>
                <AnimationState x="380" y="140" animationId="{A_ETCH}" id="{S_ETCH}">
                    {transition(S_KNIFE, cond_num('tool', 0), 260, PILL_EASE)}
                </AnimationState>
            </StateMachineLayer>
            <StateMachineLayer name="Candle" id="0:502">
                <AnyState x="760" y="-120"/>
                <ExitState x="960" y="-120"/>
                <EntryState><StateTransition stateToId="{S_UNLIT}"/></EntryState>
                <AnimationState x="160" y="140" animationId="{A_UNLIT}" id="{S_UNLIT}">
                    {transition(S_LIT, cond_bool("lit", "true"), 300, CANDLE_EASE)}
                </AnimationState>
                <AnimationState x="380" y="140" animationId="{A_LIT}" id="{S_LIT}">
                    {transition(S_UNLIT, cond_bool('lit', 'false'), 300, CANDLE_EASE)}
                </AnimationState>
            </StateMachineLayer>
            <StateMachineLayer name="Intro" id="0:503">
                <AnyState x="760" y="-120"/>
                <ExitState x="960" y="-120"/>
                <EntryState><StateTransition stateToId="0:531"/></EntryState>
                <AnimationState x="160" y="140" animationId="0:605" id="0:531"/>
            </StateMachineLayer>
{listener(HIT_KNIFE, 'Pick Knife', set_num('tool', 0))}
{listener(HIT_ETCH, 'Pick Etch', set_num('tool', 1))}
{listener(HIT_GRIN, 'Stencil Grin', set_num('stencil', 1))}
{listener(HIT_GHOUL, 'Stencil Ghoul', set_num('stencil', 2))}
{listener(HIT_MASH, 'Stencil Mashrabiya', set_num('stencil', 3))}
{listener(HIT_NEW, 'New Pumpkin', set_num('fresh', 1))}
        <StateMachineListenerSingle targetId="{HIT_CANDLE}" listenerTypeValue="click" name="Toggle Candle" id="{nid()}">
            <ListenerViewModelChange fromViewModelProperty="true" fromDataBindId="{not_id}">
                <BindablePropertyBoolean>
                    <DataBindContext sourcePathIds="{VM}-{P['lit']}" propertyKey="634" id="{not_id}" converterId="{CONV_NOT}"/>
                    {bind('lit', 634, write=True)}
                </BindablePropertyBoolean>
            </ListenerViewModelChange>
        </StateMachineListenerSingle>
        </StateMachine>'''


def key_double(obj, prop, v):
    return f'<KeyedObject objectId="{obj}"><KeyedProperty propertyKey="{prop}"><KeyFrameDouble value="{v}" frame="0"/></KeyedProperty></KeyedObject>'


def key_color(obj, v):
    return f'<KeyedObject objectId="{obj}"><KeyedProperty propertyKey="37"><KeyFrameColor value="{v}" frame="0"/></KeyedProperty></KeyedObject>'


def anim(aid, name, keys):
    body = '\n            '.join(keys)
    return f'''        <LinearAnimation duration="1" name="{name}" id="{aid}">
            {body}
        </LinearAnimation>'''



def eased(obj, prop, keys):
    """keys: (frame, value, (x1, y1, x2, y2) or None for the last)"""
    out = []
    for f, v, e in keys:
        if e:
            out.append(f'<KeyFrameDouble value="{v}" frame="{f}" interpolationType="cubic"><CubicEaseInterpolator x1="{e[0]}" y1="{e[1]}" x2="{e[2]}" y2="{e[3]}"/></KeyFrameDouble>')
        else:
            out.append(f'<KeyFrameDouble value="{v}" frame="{f}"/>')
    return f'<KeyedObject objectId="{obj}"><KeyedProperty propertyKey="{prop}">{"".join(out)}</KeyedProperty></KeyedObject>'


# the title rises out of the dark; the subtitle follows a beat later (eased by eye)
OUT = (0.16, 1, 0.3, 1)
INTRO = f'''        <LinearAnimation duration="84" name="Intro" id="0:605">
            {eased(TITLE, 18, [(0, 0, OUT), (40, 1, None)])}
            {eased(TITLE, 14, [(0, 40, OUT), (48, 18, None)])}
            {eased(SUBTITLE, 18, [(0, 0, None), (22, 0, OUT), (64, 1, None)])}
            {eased(SUBTITLE, 13, [(0, 58, None), (22, 58, OUT), (84, 58, None)])}
        </LinearAnimation>'''

anims = [INTRO,
    anim(A_KNIFE, 'Tool Knife', [key_double(TOOL_PILL, 13, X0 + 4), key_color(KNIFE_TXT_C, INK), key_color(ETCH_TXT_C, CREAM)]),
    anim(A_ETCH, 'Tool Etch', [key_double(TOOL_PILL, 13, X0 + IW / 2 + 4), key_color(KNIFE_TXT_C, CREAM), key_color(ETCH_TXT_C, INK)]),
    anim(A_UNLIT, 'Candle Unlit', [key_color(CANDLE_FILL, AMBER), key_color(CANDLE_STROKE, '00F0A040'),
                                   key_double(CANDLE_ON_TXT, 18, 1), key_double(CANDLE_OFF_TXT, 18, 0),
                                   key_double(CANDLE_DOT, 18, 0)]),
    anim(A_LIT, 'Candle Lit', [key_color(CANDLE_FILL, '00F0A040'), key_color(CANDLE_STROKE, AMBER),
                               key_double(CANDLE_ON_TXT, 18, 0), key_double(CANDLE_OFF_TXT, 18, 1),
                               key_double(CANDLE_DOT, 18, 1)]),
]

vm_props = [
    ('Number', 'tool', '0'), ('Boolean', 'lit', 'false'), ('Number', 'stencil', '0'), ('Number', 'fresh', '0'),
    ('Number', 'flame', '80'), ('Number', 'haze', '60'), ('Number', 'escape', '0'), ('String', 'escapeText', '0%'),
    ('String', 'flameText', '80'), ('String', 'hazeText', '60'),
    ('String', 'caption', 'Draw with the knife. Close a shape and the piece falls out.'), ('Number', 'quality', '1'),
    ('Number', 'haloX', '1108'), ('Number', 'haloY', '189'), ('Number', 'haloW', '216'), ('Number', 'haloH', '42'),
    ('Number', 'haloOn', '0'), ('Number', 'haloPress', '0'),
]
vm_decl = '\n'.join(f'        <ViewModelProperty{t} name="{n}" id="{P[n]}"/>' for t, n, _ in vm_props)
vm_inst = '\n'.join(f'            <ViewModelInstance{t} propertyValue="{v}" viewModelPropertyId="{P[n]}"/>' for t, n, v in vm_props)

doc = f'''<Rive version="1" kind="fragment">
    <Artboard defaultStateMachineId="0:500" viewModelId="{VM}" viewModelInstanceId="0:920" clip="true" width="1280" height="800" styleId="0:3" name="Hollow" id="0:2">
        <Fill name="Background"><SolidColor colorValue="FF060508" name="C"/></Fill>
        <LayoutComponentStyle name="Artboard Style" id="0:3"/>
{chr(10).join(children)}
{sm}
{chr(10).join(anims)}
    </Artboard>
    <DataConverterRangeMapper minInput="0" maxInput="100" minOutput="0" maxOutput="{IW}" clampLower="true" clampUpper="true" name="Percent to Width" id="{CONV_W}"/>
    <DataConverterRangeMapper minInput="0" maxInput="100" minOutput="{X0}" maxOutput="{X1}" clampLower="true" clampUpper="true" name="Percent to Knob X" id="{CONV_X}"/>
    <DataConverterBooleanNegate name="Not" id="{CONV_NOT}"/>
    <DataConverterRangeMapper minInput="0" maxInput="1" minOutput="1" maxOutput="1.04" clampLower="true" clampUpper="true" name="Press to Scale" id="{CONV_PRESS}"/>
    <ViewModel defaultInstanceId="0:920" name="Hollow" id="{VM}">
{vm_decl}
        <ViewModelInstance exports="true" name="Default" id="0:920">
{vm_inst}
        </ViewModelInstance>
    </ViewModel>
    <FontAsset file="fonts/CormorantGaramond-SemiBoldItalic.ttf" name="Cormorant Garamond SemiBold Italic" id="0:31"/>
    <FontAsset file="fonts/CormorantGaramond-Medium.ttf" name="Cormorant Garamond Medium" id="0:32"/>
    <FontAsset file="fonts/IBMPlexMono-Medium.ttf" name="IBM Plex Mono Medium" id="0:33"/>
    <FontAsset file="fonts/IBMPlexSansArabic-SemiBold.ttf" name="IBM Plex Sans Arabic SemiBold" id="0:35"/>
    <ScriptAsset file="main.luau" name="main" id="0:80"/>
    <ShaderAsset file="light.wgsl" name="light" id="0:81"/>
</Rive>
'''

open('scene.rml', 'w').write(doc)
print('wrote scene.rml')
