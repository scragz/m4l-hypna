"""Build an editable Max patch and an unfrozen M4L instrument from local sources."""
import json
import math
import re
import shutil
import struct
import sys
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# OUT holds editable staging sources (loose deps + the unfrozen dev device);
# DEST holds only the final, self-contained frozen device.
OUT = ROOT / "scripts" / "build"
OUT.mkdir(parents=True, exist_ok=True)
DEST = ROOT / "device"
DEST.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT.parent / "theme"))
import theme as T  # noqa: E402  shared device theme
# HFS+ timestamps, which the collective directory uses, count from 1 Jan 1904.
MAC_EPOCH = 2082844800

# src/hypna-waves.json declares the wavetable layout. It generates the tables
# and supplies the constants the DSP indexes them with, so the two cannot drift.
LAYOUT = json.loads((SRC/'hypna-waves.json').read_text())
BANKS = LAYOUT['banks']
FRAMES = LAYOUT['frames']
CYCLE = LAYOUT['cycle_samples']
HARMONICS = LAYOUT['harmonics']
PARTIALS = HARMONICS[0]


def spectrum(bank, t):
    """Original, phase-aligned spectral journeys, expressed as sine partials."""
    result = []
    for h in range(1, PARTIALS+1):
        if bank == 0:
            classic = [1.0 if h == 1 else 0.0,
                       8 / math.pi**2 * (-1)**((h-1)//2) / h**2 if h % 2 else 0.0,
                       0.5 / h, 0.8 / h if h % 2 else 0.0]
            frame = min(int(t * 3), 2)
            blend = t * 3 - frame
            value = ((1-blend)*classic[frame] + blend*classic[frame+1]) if h <= PARTIALS//2 else 0
        elif bank == 1:  # Open a soft spectrum into a full, bright harmonic stack.
            value = math.exp(-(h/(1.3+40*t*t))**2) / h**0.95
        elif bank == 2:  # Odd harmonics; a resonant band travels up the hollow body.
            value = (0.4/h + math.exp(-((h-(3+22*t))/3)**2)/h**0.3) if h % 2 else 0
        elif bank == 3:  # Two narrow upper bands move at different rates.
            value = (0.3 if h == 1 else 0) + 0.65*math.exp(-((h-(3+24*t))/1.4)**2) + 0.4*math.exp(-((h-(11+38*t))/2)**2)
        elif bank == 4:  # Three broad vocal-like formants; still integer harmonics.
            value = 0.15/h + math.exp(-((h-(3+7*t))/1.5)**2) + 0.7*math.exp(-((h-(13-5*t))/2.2)**2) + 0.4*math.exp(-((h-(19+13*t))/3)**2)
        elif bank == 5:  # Odd/even balance and brightness evolve independently.
            value = (1 if h % 2 else 0.1+0.9*t) * math.exp(-h/(3+45*t)) / h**0.7
        elif bank == 6:  # Signed partials progressively invert, producing folded contours.
            value = math.cos(h*t*math.pi*1.5) * math.exp(-h/32) / h**0.9
            if h == 1: value = 0.8
        else:  # Sweep a spectral comb over a persistent fundamental.
            value = (0.08 + 0.92*(0.5+0.5*math.cos(h*(0.2+1.4*t)))**5) / h**0.8
            if h == 1: value = 0.7
        result.append(value)
    return result


def make_waves():
    # Bank -> mip level -> morph frame -> sample. Compute each partial once,
    # snapshot bandwidth levels, and apply the full frame's gain to every mip.
    sines = [[math.sin(2*math.pi*h*i/CYCLE) for i in range(CYCLE)] for h in range(1, PARTIALS+1)]
    with wave.open(str(OUT / "hypna-waves.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        for bank in range(len(BANKS)):
            levels = {h: [] for h in HARMONICS}
            for frame in range(FRAMES):
                coefficients = spectrum(bank, frame/(FRAMES-1))
                current = [0.0]*CYCLE
                snapshots = {}
                for h, weight in enumerate(coefficients, 1):
                    if weight:
                        current = [v+weight*s for v, s in zip(current, sines[h-1])]
                    if h in levels:
                        snapshots[h] = current[:]
                # Classic preserves the first prototype's exact sound.
                # Bound every mip as well as the full spectrum: removing a
                # cancelling partial can otherwise increase a waveform's peak.
                peak = max(abs(v) for row in snapshots.values() for v in row)
                gain = 1 if bank == 0 else 0.9/max(peak, 0.0001)
                for h in HARMONICS:
                    row = array('h', (round(max(-1, min(1, v*gain))*32767) for v in snapshots[h]))
                    if sys.byteorder != 'little': row.byteswap()
                    levels[h].append(row.tobytes())
            for h in HARMONICS:
                for row in levels[h]: wav.writeframesraw(row)
    shutil.copy2(SRC/'hypna-waves.json', OUT/'hypna-waves.json')


def constants():
    """Layout constants the DSP indexes the wavetable with, all derived from
    src/hypna-waves.json so a layout change reaches the code that reads it."""
    return {
        'BANKS': len(BANKS), 'BANKMAX': len(BANKS)-1,
        'MIPS': len(HARMONICS), 'MIPMAX': len(HARMONICS)-1,
        'PARTIALS': PARTIALS,
        'FRAMES': FRAMES, 'FRAMEMAX': FRAMES-1, 'BLENDMAX': FRAMES-2,
        'CYCLE': CYCLE,
        # Scan centre, the -100..100 offset's scale, and the Classic bank's
        # triangle frame: all positions within a frame set.
        'WAVEMID': (FRAMES-1)/2,
        'WAVESCALE': (FRAMES-1)/200,
        'TRIANGLE': (FRAMES-1)/3,
    }


def number(value):
    """Whole numbers print without a decimal point, as hand-written GenExpr would."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return repr(value)


def substitute(text, tokens):
    """Replace the $NAMEs present in `tokens`; leave any others for a later pass."""
    return re.sub(r'\$([A-Z]+)',
                  lambda m: number(tokens[m.group(1)]) if m.group(1) in tokens else m.group(0),
                  text)


def read_block(lines, start):
    """Return the lines between an opening //@ marker and its matching //@end."""
    depth, body, index = 1, [], start + 1
    while index < len(lines):
        marker = lines[index].strip()
        if marker == '//@end':
            depth -= 1
            if depth == 0:
                return body, index + 1
        elif marker.startswith('//@'):
            depth += 1
        body.append(lines[index])
        index += 1
    raise SystemExit('unterminated //@ block in ' + str(SRC/'hypna-engine.genexpr'))


def emit_voice(body, voice, frequency):
    """One voice's lines. GenExpr has no arrays of History, so the five voices
    are unrolled here; //@fundamental sections belong to voice 0 alone."""
    tokens = {'V': voice, 'F': frequency}
    lines, index = [], 0
    while index < len(body):
        if body[index].strip() == '//@fundamental':
            nested, index = read_block(body, index)
            if voice == 0:
                lines.extend(substitute(line, tokens) for line in nested)
        else:
            lines.append(substitute(body[index], tokens))
            index += 1
    return lines


def expand(template, frequencies):
    """Expand src/hypna-engine.genexpr into the DSP embedded in the patch."""
    lines = template.splitlines(keepends=True)
    output, index = [], 0
    while index < len(lines):
        marker = lines[index].strip()
        if marker == '//@doc':
            _, index = read_block(lines, index)
        elif marker == '//@voices':
            body, index = read_block(lines, index)
            for voice, frequency in enumerate(frequencies):
                output.extend(emit_voice(body, voice, frequency))
        else:
            output.append(lines[index])
            index += 1
    return substitute(''.join(output), constants())


def dsp_code():
    frequencies = [58.27, 58.27*42/32, 58.27*56/32, 58.27*62/32, 58.27*63/32]
    return expand((SRC/'hypna-engine.genexpr').read_text(), frequencies)


def make_patch(code):
    patch = dict(fileversion=1, appversion=dict(major=8, minor=6, revision=5, architecture="x64", modernui=1),
                 classnamespace="box", rect=[80, 100, 1110, 700], openrect=[0, 0, 1036, 169],
                 openinpresentation=1, devicewidth=1036, bglocked=1,
                 boxes=[], lines=[], parameters={}, dependency_cache=[], autosave=0, **T.patcher_attrs())
    patch['project'] = dict(version=1, amxdtype=1768515945, readonly=0, devpathtype=0, devpath=".", autoorganize=1, hideprojectwindow=1, autolocalize=0, contents={}, layout={}, searchpath={})

    def box(id, klass="newobj", text=None, rect=None, **kw):
        b = dict(id=id, maxclass=klass, patching_rect=rect or [20, 220 + len(patch['boxes'])*25, 160, 22])
        if text is not None:
            b['text'] = text
        b.update(kw)
        patch['boxes'].append(dict(box=b))
        return id

    def wire(src, dst, so=0, di=0):
        patch['lines'].append(dict(patchline=dict(source=[src, so], destination=[dst, di])))

    def label(id, text, x, y, w, role='label', justify=0):
        box(id, "comment", text, [x, y, w, 18], presentation=1, presentation_rect=[x, y, w, 18],
            varname=id, numinlets=1, numoutlets=0, **T.label(role, justify=justify))

    def readout(id, x, y, w):
        box(id, "comment", '', [x, y, w, 18], presentation=1, presentation_rect=[x, y+1, w, 17],
            varname=id, numinlets=1, numoutlets=0, **T.label('text', T.SPEC['font']['readout']))

    def param(name, title, default, lo, hi, x, y, w=52, unit=0, enum=None, integer=False, tuning=False, toggle=False):
        attrs = dict(parameter_longname=title, parameter_shortname=title, parameter_type=0,
                     parameter_mmin=lo, parameter_mmax=hi, parameter_initial=[default], parameter_initial_enable=1,
                     parameter_unitstyle=unit, parameter_linknames=0)
        klass, extra = "live.numbox", T.numbox()
        if toggle:
            klass = "live.text"
            attrs.update(parameter_type=2, parameter_enum=enum, parameter_unitstyle=9)
            extra = dict(T.button(), text=enum[0], texton=enum[1], mode=1)
        elif enum:
            klass = "live.menu"
            attrs.update(parameter_type=2, parameter_enum=enum, parameter_unitstyle=9)
            extra = dict(T.menu(), items=enum)
        elif integer and hi <= 255:
            attrs['parameter_type'] = 1
        box(name, klass, rect=[x, y, w, 18], presentation=1, presentation_rect=[x, y, w, 18],
            parameter_enable=1, varname=name, saved_attribute_attributes=dict(valueof=attrs), **extra)
        patch['parameters'][name] = [title, title, 0]
        if integer and not enum:
            integer_id = box(name+'-int', text="round 1")
            wire(name, integer_id)
        else:
            integer_id = name
        prep = box(name+'-message', text='prepend '+name)
        wire(integer_id, prep)
        wire(prep, 'control' if tuning else 'synth')

    # Fieldsets: Tuning and Wavetable stacked at left, then Voices, Motion, Space.
    art = dict(width=1036, height=169, fieldsets=[
        [2, 0, 264, 90, 'Tuning'], [2, 92, 264, 76, 'Wavetable'], [270, 0, 424, 168, 'Voices'],
        [698, 0, 166, 168, 'Motion'], [868, 0, 166, 168, 'Space']])
    label('prime-label', 'Primes', 10, 22, 62)
    for i, value in enumerate([2, 3, 7, 31]):
        param('prime'+str(i), 'Prime '+str(i+1), value, 2 if i==0 else 1, 32767, 74+i*47, 22, 44, integer=True, tuning=True)
    label('base-label', 'Base Hz', 10, 44, 62)
    param('base', 'Base frequency', 29.135, 0.001, 32.767, 74, 44, 62, unit=1, tuning=True)
    label('octave-label', 'Octave', 142, 44, 52)
    param('octave', 'Octave', 1, -8, 8, 196, 44, 62, integer=True, tuning=True)
    label('den-label', 'Denom.', 10, 66, 62)
    param('denominator', 'Denominator', 32, 1, 256, 74, 66, 62, integer=True, tuning=True)
    label('trans-label', 'Transpose', 142, 66, 52)
    param('transpose', 'Transpose', 0, -60, 60, 196, 66, 62, unit=7, integer=True, tuning=True)
    label('shape-label', 'Bass Wave', 10, 114, 62)
    param('shape', 'Fundamental waveform', 0, 0, 3, 74, 114, 184, enum=['Wavetable', 'Sine', 'Triangle', 'Square'])
    label('wavetable-label', 'Table', 10, 140, 62)
    param('wavetable', 'Wavetable', 0, 0, len(BANKS)-1, 74, 140, 184, enum=BANKS)

    for title, x, w in [('Voice', 280, 56), ('Gate', 338, 36), ('Numerator', 380, 66), ('Ratio / Hz', 452, 116), ('Gain', 572, 54), ('Pan', 632, 54)]:
        label('header-'+title, title, x, 20, w)
    for i in range(5):
        y = 40+i*25
        label('voice'+str(i), 'Fund.' if i==0 else 'Tone '+str(i), 280, y, 56)
        param('gate'+str(i), 'Gate '+str(i), 0, 0, 1, 338, y, 36, enum=['Off', 'On'], toggle=True)
        if i:
            param('numerator'+str(i-1), 'Numerator '+str(i), [42,56,62,63][i-1], 1, 1024, 380, y, 66, integer=True, tuning=True)
        else:
            label('fundamental-ratio', '1/1', 380, y, 66, 'dim', justify=1)
        readout('pitch'+str(i), 452, y, 116)
        param('gain'+str(i), 'Gain '+str(i), 0, -40, 6, 572, y, 54, unit=4)
        if i:
            param('pan'+str(i), 'Pan '+str(i), 0, -100, 100, 632, y, 54, unit=0)
        else:
            label('center', 'Center', 632, y, 54, 'dim', justify=1)

    for i, (name, title, default, lo, hi, unit) in enumerate([
        ('wavepos','Wave Offset',0,-100,100,0), ('attack','Attack',10,0,30000,2),
        ('release','Release',1000,0,60000,2), ('slew','Slew',0,0,10000,2), ('crossfade','Crossfade',20,0,10000,2)]):
        label(name+'-label', title, 708, 24+i*27, 72)
        param(name,title,default,lo,hi,780,24+i*27,76,unit=unit)
    for i, (name, title, default, lo, hi, unit) in enumerate([
        ('wet','Reverb Mix',0,0,100,5), ('revtime','Reverb Time',1700,400,30000,2),
        ('size','Size',100,1,100,5), ('damping','High Damp',60,0,100,0), ('master','Output',-12,-60,0,4)]):
        label(name+'-label', title, 878, 24+i*27, 72)
        param(name,title,default,lo,hi,950,24+i*27,76,unit=unit)

    gen = dict(fileversion=1, classnamespace="dsp.gen", rect=[100, 100, 950, 700], boxes=[
        dict(box=dict(id='code', maxclass='codebox', code=code, numinlets=0, numoutlets=4, patching_rect=[40, 40, 850, 570]))], lines=[])
    for i in range(4):
        gen['boxes'].append(dict(box=dict(id='out'+str(i),maxclass='newobj',text='out '+str(i+1),patching_rect=[40+i*130,640,70,22])))
        gen['lines'].append(dict(patchline=dict(source=['code',i],destination=['out'+str(i),0])))
    # Max records a js object's script in saved_object_attributes; freezing
    # resolves the dependency from there, not from the box text.
    box('control', text='js hypna-control.js', rect=[30, 225, 160, 22], numinlets=1, numoutlets=1,
        saved_object_attributes=dict(filename='hypna-control.js', parameter_enable=0))
    box('synth', text='gen~', rect=[400, 290, 100, 22], numinlets=1, numoutlets=4, outlettype=['signal']*4, patcher=gen)
    wire('control','synth')
    box('table',text='buffer~ hypna_factory_v2 hypna-waves.wav',rect=[30,260,345,22])
    box('midi',text='midiin',rect=[30,300,60,22])
    box('live-init',text='live.thisdevice',rect=[30,340,120,22])
    box('init-defer',text='deferlow',rect=[30,375,80,22])
    box('restore',klass='message',text='restore',rect=[30,410,80,22])
    wire('live-init','init-defer'); wire('init-defer','restore'); wire('restore','control')
    box('audio',text='plugout~',rect=[400,370,100,22],numinlets=2,numoutlets=2)
    wire('synth','audio'); wire('synth','audio',1,1)
    label('raw-comment','Gen outputs 3 and 4: raw fundamental and envelope inspection taps.',400,430,550)
    # Inspection guidance belongs in the editor, not the device presentation.
    patch['boxes'][-1]['box']['presentation'] = 0
    # Background art sits last: Max draws later boxes behind earlier ones in this build's ordering.
    box('art', 'jsui', rect=[0, 0, 1036, 169], presentation=1, presentation_rect=[0, 0, 1036, 169], filename='hypna-art.js',
        border=0, ignoreclick=1, background=1, numinlets=1, numoutlets=1, outlettype=[''], parameter_enable=0)
    T.write_jsui(OUT, 'hypna', art)
    patch['dependency_cache'] = [dict(name='hypna-control.js',type='TEXT',implicit=1),dict(name='hypna-waves.wav',type='WAVE',implicit=1),
                                 dict(name='hypna-theme.js',type='TEXT',implicit=1),dict(name='hypna-art.js',type='TEXT',implicit=1)]
    patch['parameters']['parameterbanks'] = {
        '0': dict(index=0,name='Tuning',parameters=['base','octave','transpose','denominator','numerator0','numerator1','numerator2','numerator3']),
        '1': dict(index=1,name='Tone',parameters=['wavepos','shape','attack','release','slew','crossfade','wet','master']),
        '2': dict(index=2,name='Voices',parameters=['gate0','gate1','gate2','gate3','gate4','revtime','size','damping']),
        '3': dict(index=3,name='Wavetable',parameters=['wavetable','wavepos','shape','attack','release','crossfade','wet','master'])}
    return dict(patcher=patch)


def amxd(payload, meta=0):
    """Wrap a ptch payload in the outer chunks. Outer sizes are little-endian.

    Same ampf/iiii/meta/ptch layout as Live's installed Max Instrument template.
    The meta value is a big-endian format revision; frozen devices written by
    Max carry 7, while the unfrozen template leaves it at 0.
    """
    return (b'ampf' + struct.pack('<I', 4) + b'iiii'
            + b'meta' + struct.pack('<I', 4) + struct.pack('>I', meta)
            + b'ptch' + struct.pack('<I', len(payload)) + payload)


def chunk(tag, data):
    """A collective chunk: tag, big-endian size counting this 8-byte header, data."""
    return tag.encode() + struct.pack('>I', len(data) + 8) + data


def padded(name):
    """Collective names are null-terminated and padded to a four-byte boundary."""
    raw = name.encode()
    return raw + b'\0' * (4 - len(raw) % 4)


def mac_time(path):
    return int(path.stat().st_mtime) + MAC_EPOCH


def collective(name, document, dependencies):
    """Bundle the patcher and every dependency into an mx@c collective.

    Layout: a sixteen-byte header, the file payloads back to back, then a 'dlst'
    footer of one 'dire' record per file. Header words two and three are a single
    64-bit big-endian offset to that footer. Each record carries the file's type
    code, name, size, absolute offset, and modification date, so Max can resolve
    `js hypna-control.js` and `buffer~ ... hypna-waves.wav` from inside the
    device instead of from sibling files on disk.
    """
    entries = []
    for dependency in dependencies:
        path = OUT / dependency['name']
        entries.append(dict(name=dependency['name'], type=dependency['type'], flag=0,
                            data=path.read_bytes(), mdat=mac_time(path)))
    # The patcher itself is the first entry, named after the device, and is the
    # only one flagged 17. Max writes patcher text with a trailing newline/null.
    stamps = [entry['mdat'] for entry in entries] + [mac_time(Path(__file__).resolve())]
    entries.insert(0, dict(name=name, type='JSON', flag=17, mdat=max(stamps),
                           data=json.dumps(document, indent=2).encode() + b'\n\0'))

    offset = 16
    directory = b''
    for entry in entries:
        directory += chunk('dire', b''.join([
            chunk('type', entry['type'].encode()),
            chunk('fnam', padded(entry['name'])),
            chunk('sz32', struct.pack('>I', len(entry['data']))),
            chunk('of32', struct.pack('>I', offset)),
            chunk('vers', struct.pack('>I', 0)),
            chunk('flag', struct.pack('>I', entry['flag'])),
            chunk('mdat', struct.pack('>I', entry['mdat'])),
        ]))
        offset += len(entry['data'])
    return (b'mx@c' + struct.pack('>III', 16, 0, offset)
            + b''.join(entry['data'] for entry in entries) + chunk('dlst', directory))


if __name__ == '__main__':
    make_waves()
    code = dsp_code()
    (OUT/'hypna-engine.genexpr').write_text(code)
    # copy2 keeps the source timestamp, which the frozen directory records.
    shutil.copy2(SRC/'hypna-control.js', OUT/'hypna-control.js')
    data = json.dumps(make_patch(code), indent=2).encode()+b'\n'
    (OUT/'Hypna.maxpat').write_bytes(data)
    # Development device: the patch alone, reading its dependencies from device/.
    (OUT/'Hypna.dev.amxd').write_bytes(amxd(data + b'\0'))
    # Distribution device: frozen, so the controller script and factory wavetable
    # travel inside the file. A frozen patcher is read-only in Max.
    document = json.loads(data)
    document['patcher']['project'] = dict(document['patcher']['project'], readonly=1)
    (DEST/'Hypna.amxd').write_bytes(amxd(
        collective('Hypna.amxd', document, document['patcher']['dependency_cache']), meta=7))
    print('Built Hypna.maxpat, frozen Hypna.amxd, Hypna.dev.amxd, and factory wavetable.')
