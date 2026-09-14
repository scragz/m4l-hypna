"""Build an editable Max patch and an unfrozen M4L instrument from local sources."""
import json
import math
import struct
import sys
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "device"
OUT.mkdir(exist_ok=True)
BANKS = ['Classic', 'Bloom', 'Hollow', 'Glass', 'Formant', 'Reed', 'Fold', 'Comb']
FRAMES = 16
CYCLE = 2048
HARMONICS = [64, 32, 16, 8, 4, 2, 1]


def spectrum(bank, t):
    """Original, phase-aligned spectral journeys, expressed as sine partials."""
    result = []
    for h in range(1, 65):
        if bank == 0:
            classic = [1.0 if h == 1 else 0.0,
                       8 / math.pi**2 * (-1)**((h-1)//2) / h**2 if h % 2 else 0.0,
                       0.5 / h, 0.8 / h if h % 2 else 0.0]
            frame = min(int(t * 3), 2)
            blend = t * 3 - frame
            value = ((1-blend)*classic[frame] + blend*classic[frame+1]) if h <= 32 else 0
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
    sines = [[math.sin(2*math.pi*h*i/CYCLE) for i in range(CYCLE)] for h in range(1, 65)]
    with wave.open(str(OUT / "dream-waves.wav"), "wb") as wav:
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
    (OUT/'dream-waves.json').write_text(json.dumps(dict(banks=BANKS, frames=FRAMES,
        cycle_samples=CYCLE, harmonics=HARMONICS, layout='bank, mip, frame, sample'), indent=2)+'\n')


def dsp_code():
    code = '''// Factory table: eight banks, seven bandwidth levels, sixteen frames.
tableosc(ph, hz, position, sr, table, bank) {
    level = clamp(ceil(log2(max(1, hz * 64 / (sr * 0.45)))), 0, 6);
    frame = clamp(position, 0, 15);
    first = min(floor(frame), 14);
    blend = frame - first;
    ix = wrap(ph, 0, 1) * 2048;
    a = floor(ix);
    b = wrap(a + 1, 0, 2048);
    frac = ix - a;
    offset = ((clamp(floor(bank), 0, 7) * 7 + level) * 16 + first) * 2048;
    w0 = mix(peek(table, offset + a, 0), peek(table, offset + b, 0), frac);
    w1 = mix(peek(table, offset + 2048 + a, 0), peek(table, offset + 2048 + b, 0), frac);
    return mix(w0, w1, blend);
}
Buffer waves("dream_machine_factory_v2");
Param wavetable(0);
Param wavepos(0);
Param shape(0);
Param attack(10);
Param release(1000);
Param slew(0);
Param crossfade(20);
Param master(-12);
Param wet(0);
Param revtime(1700);
Param size(100);
Param damping(60);
History smoothwave(7.5);
History bankfrom(0);
History bankto(0);
History bankfade(1);
History smoothmaster(0);
History smoothwet(0);
'''
    freqs = [58.27, 58.27*42/32, 58.27*56/32, 58.27*62/32, 58.27*63/32]
    for i, f in enumerate(freqs):
        code += f'''Param freq{i}({f});
Param gate{i}(0);
Param gain{i}(0);
Param pan{i}(0);
History env{i}(0);
History amp{i}(1);
History panning{i}(0.5);
History phaseA{i}(0);
History phaseB{i}(0);
History targetA{i}({f});
History targetB{i}({f});
History actualA{i}({f});
History actualB{i}({f});
History side{i}(0);
History progress{i}(1);
History accepted{i}({f});
'''
    code += '''Delay d0(192000);
Delay d1(192000);
Delay d2(192000);
Delay d3(192000);
History low0(0);
History low1(0);
History low2(0);
History low3(0);
smooth = exp(-1 / (0.01 * samplerate));
smoothwave = mix((clamp(wavepos, -100, 100) + 100) * 0.075, smoothwave, smooth);
// Finish each 50 ms bank fade, then accept the latest selection. All voices
// share its timing; rapid automation never cuts off an unfinished transition.
requestedbank = clamp(floor(wavetable + 0.5), 0, 7);
if ((requestedbank != bankto) && (bankfade >= 1)) {
    bankfrom = bankto;
    bankto = requestedbank;
    bankfade = 0;
}
bankfade = min(1, bankfade + 1 / (0.05 * samplerate));
bankblend = 0.5 - 0.5 * cos(bankfade * pi);
smoothmaster = mix(pow(10, master / 20), smoothmaster, smooth);
smoothwet = mix(clamp(wet * 0.01, 0, 1), smoothwet, smooth);
slewcoeff = slew <= 0 ? 0 : exp(-1 / (max(slew, 0.01) * 0.001 * samplerate));
left = 0;
right = 0;
'''
    for i in range(5):
        code += f'''
// Voice {i}: finish the current crossfade before accepting the latest retune.
// The outgoing oscillator is held; the incoming oscillator starts phase-aligned.
if ((freq{i} != accepted{i}) && (progress{i} >= 1)) {{
    if (side{i} < 0.5) {{ targetB{i} = freq{i}; phaseB{i} = phaseA{i}; actualB{i} = actualA{i}; }}
    else {{ targetA{i} = freq{i}; phaseA{i} = phaseB{i}; actualA{i} = actualB{i}; }}
    side{i} = 1 - side{i};
    progress{i} = 0;
    accepted{i} = freq{i};
}}
progress{i} = min(1, progress{i} + 1 / max(1, crossfade * 0.001 * samplerate));
actualA{i} = mix(targetA{i}, actualA{i}, slewcoeff);
actualB{i} = mix(targetB{i}, actualB{i}, slewcoeff);
fa{i} = clamp(actualA{i}, 0.000001, samplerate * 0.45);
fb{i} = clamp(actualB{i}, 0.000001, samplerate * 0.45);
phaseA{i} = wrap(phaseA{i} + fa{i} / samplerate, 0, 1);
phaseB{i} = wrap(phaseB{i} + fb{i} / samplerate, 0, 1);
pos{i} = smoothwave;
'''
        if i == 0:
            code += 'pos0 = shape == 2 ? 5 : (shape == 3 ? 15 : smoothwave);\n'
        code += f'''voicebank{i} = bankto;
oldbank{i} = bankfrom;
'''
        if i == 0:
            code += 'voicebank0 = shape > 0 ? 0 : bankto;\noldbank0 = shape > 0 ? 0 : bankfrom;\n'
        code += f'''a{i} = tableosc(phaseA{i}, fa{i}, pos{i}, samplerate, waves, voicebank{i});
b{i} = tableosc(phaseB{i}, fb{i}, pos{i}, samplerate, waves, voicebank{i});
if (bankfade < 1) {{
    olda{i} = tableosc(phaseA{i}, fa{i}, pos{i}, samplerate, waves, oldbank{i});
    oldb{i} = tableosc(phaseB{i}, fb{i}, pos{i}, samplerate, waves, oldbank{i});
    a{i} = mix(olda{i}, a{i}, bankblend);
    b{i} = mix(oldb{i}, b{i}, bankblend);
}}
'''
        if i == 0:
            code += 'a0 = shape == 1 ? sin(phaseA0 * twopi) : a0;\nb0 = shape == 1 ? sin(phaseB0 * twopi) : b0;\n'
        code += f'''// Do not fold an out-of-band ratio down to an unrelated audible pitch.
a{i} = actualA{i} < samplerate * 0.45 ? a{i} : 0;
b{i} = actualB{i} < samplerate * 0.45 ? b{i} : 0;
blend{i} = 0.5 - 0.5 * cos(progress{i} * pi);
weight{i} = side{i} < 0.5 ? 1 - blend{i} : blend{i};
osc{i} = mix(a{i}, b{i}, weight{i});
duration{i} = gate{i} > 0.5 ? attack : release;
env{i} = clamp(env{i} + (gate{i} > 0.5 ? 1 : -1) / max(1, duration{i} * 0.001 * samplerate), 0, 1);
amp{i} = mix(gain{i} <= -40 ? 0 : pow(10, gain{i} / 20), amp{i}, smooth);
panning{i} = mix(clamp((pan{i} + 100) / 200, 0, 1), panning{i}, smooth);
voice{i} = osc{i} * env{i} * amp{i} * 0.2;
left = left + voice{i} * cos(panning{i} * pi * 0.5);
right = right + voice{i} * sin(panning{i} * pi * 0.5);
'''
    code += '''// Four-line orthogonal feedback delay network. RT60 is in milliseconds.
roomscale = 0.25 + 0.75 * clamp(size / 100, 0.01, 1);
t0 = min(191998, samplerate * 0.0297 * roomscale);
t1 = min(191998, samplerate * 0.0371 * roomscale);
t2 = min(191998, samplerate * 0.0411 * roomscale);
t3 = min(191998, samplerate * 0.0437 * roomscale);
r0 = d0.read(t0);
r1 = d1.read(t1);
r2 = d2.read(t2);
r3 = d3.read(t3);
cutoff = 18000 * pow(0.025, clamp(damping / 100, 0, 1));
lp = exp(-twopi * min(cutoff, samplerate * 0.45) / samplerate);
low0 = mix(r0, low0, lp);
low1 = mix(r1, low1, lp);
low2 = mix(r2, low2, lp);
low3 = mix(r3, low3, lp);
decay = max(0.4, revtime * 0.001) * samplerate;
d0.write(left + 0.5 * (low0 + low1 + low2 + low3) * pow(0.001, t0 / decay));
d1.write(right + 0.5 * (low0 - low1 + low2 - low3) * pow(0.001, t1 / decay));
d2.write(left + 0.5 * (low0 + low1 - low2 - low3) * pow(0.001, t2 / decay));
d3.write(right + 0.5 * (low0 - low1 - low2 + low3) * pow(0.001, t3 / decay));
wetleft = (r0 + r2) * 0.25;
wetright = (r1 + r3) * 0.25;
out1 = tanh(mix(left, wetleft, smoothwet) * smoothmaster);
out2 = tanh(mix(right, wetright, smoothwet) * smoothmaster);
// Inspection taps, not routed to Live's main outputs.
out3 = osc0;
out4 = env0;
'''
    return code


def make_patch(code):
    patch = dict(fileversion=1, appversion=dict(major=8, minor=6, revision=5, architecture="x64", modernui=1),
                 classnamespace="box", rect=[80, 100, 1110, 700], openrect=[0, 0, 1110, 169],
                 openinpresentation=1, devicewidth=1110, default_fontname="Arial", default_fontsize=11,
                 bglocked=1, bgcolor=[0.09, 0.10, 0.13, 1], editing_bgcolor=[0.15, 0.16, 0.19, 1],
                 boxes=[], lines=[], parameters={}, dependency_cache=[], autosave=0)
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

    def label(id, text, x, y, w, color=None, size=10):
        box(id, "comment", text, [x, y, w, 18], presentation=1, presentation_rect=[x, y, w, 18],
            textcolor=color or [0.73, 0.76, 0.81, 1], fontsize=size, varname=id)

    def param(name, title, default, lo, hi, x, y, w=52, unit=0, enum=None, integer=False, tuning=False):
        attrs = dict(parameter_longname=title, parameter_shortname=title, parameter_type=0,
                     parameter_mmin=lo, parameter_mmax=hi, parameter_initial=[default], parameter_initial_enable=1,
                     parameter_unitstyle=unit, parameter_linknames=0)
        klass = "live.numbox"
        if enum:
            klass = "live.menu"
            attrs.update(parameter_type=2, parameter_enum=enum, parameter_unitstyle=9)
        elif integer and hi <= 255:
            attrs['parameter_type'] = 1
        extra = dict(items=enum) if enum else {}
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

    label('title', 'DREAM MACHINE', 12, 5, 200, [0.62, 0.83, 0.75, 1], 15)
    label('subtitle', 'PRIME-RATIO DRONE INSTRUMENT', 208, 7, 260, size=10)
    label('prime-label', 'Primes', 12, 34, 55)
    for i, value in enumerate([2, 3, 7, 31]):
        param('prime'+str(i), 'Prime '+str(i+1), value, 2 if i==0 else 1, 32767, 63+i*49, 34, 44, integer=True, tuning=True)
    label('base-label', 'Base Hz', 12, 62, 55)
    param('base', 'Base frequency', 29.135, 0.001, 32.767, 63, 62, 77, unit=1, tuning=True)
    label('octave-label', 'Octave', 151, 62, 45)
    param('octave', 'Octave', 1, -8, 8, 200, 62, 58, integer=True, tuning=True)
    label('den-label', 'Denom.', 12, 90, 50)
    param('denominator', 'Denominator', 32, 1, 256, 63, 90, 77, integer=True, tuning=True)
    label('trans-label', 'Transpose', 146, 90, 58)
    param('transpose', 'Transpose', 0, -60, 60, 207, 90, 51, unit=7, integer=True, tuning=True)
    label('shape-label', 'Bass wave', 12, 118, 60)
    param('shape', 'Fundamental waveform', 0, 0, 3, 77, 118, 181, enum=['Wavetable', 'Sine', 'Triangle', 'Square'])
    label('wavetable-label', 'Wavetable', 12, 144, 60)
    param('wavetable', 'Wavetable', 0, 0, len(BANKS)-1, 77, 144, 181, enum=BANKS)

    for title, x, w in [('Voice', 281, 65), ('Gate', 349, 32), ('Numerator', 390, 68), ('Ratio / Hz', 469, 155), ('dB', 627, 47), ('Pan', 686, 47)]:
        label('header-'+title, title, x, 29, w)
    for i in range(5):
        y = 50+i*22
        label('voice'+str(i), 'Fund.' if i==0 else 'Tone '+str(i), 281, y, 65)
        param('gate'+str(i), 'Gate '+str(i), 0, 0, 1, 349, y, 31, enum=['Off', 'On'])
        if i:
            param('numerator'+str(i-1), 'Numerator '+str(i), [42,56,62,63][i-1], 1, 1024, 390, y, 66, integer=True, tuning=True)
        else:
            label('fundamental-ratio', '—', 390, y, 66)
        label('pitch'+str(i), '', 469, y, 155)
        param('gain'+str(i), 'Gain '+str(i), 0, -40, 6, 627, y, 47, unit=4)
        if i:
            param('pan'+str(i), 'Pan '+str(i), 0, -100, 100, 686, y, 47, unit=0)
        else:
            label('center', 'Center', 686, y, 47)

    label('motion-title', 'TONE / MOTION', 750, 29, 163, [0.62, 0.83, 0.75, 1])
    label('space-title', 'SPACE / OUTPUT', 933, 29, 160, [0.62, 0.83, 0.75, 1])
    for name, title, default, lo, hi, y, unit in [
        ('wavepos','Wave offset',0,-100,100,50,0), ('attack','Attack',10,0,30000,72,2),
        ('release','Release',1000,0,60000,94,2), ('slew','Slew',0,0,10000,116,2), ('crossfade','Crossfade',20,0,10000,138,2)]:
        label(name+'-label', title, 750, y, 87)
        param(name,title,default,lo,hi,840,y,76,unit=unit)
    for name, title, default, lo, hi, y, unit in [
        ('wet','Reverb mix',0,0,100,50,5), ('revtime','Reverb time',1700,400,30000,72,2),
        ('size','Size',100,1,100,94,5), ('damping','High damp',60,0,100,116,0), ('master','Output',-12,-60,0,138,4)]:
        label(name+'-label', title, 933, y, 87)
        param(name,title,default,lo,hi,1023,y,75,unit=unit)

    gen = dict(fileversion=1, classnamespace="dsp.gen", rect=[100, 100, 950, 700], boxes=[
        dict(box=dict(id='code', maxclass='codebox', code=code, numinlets=0, numoutlets=4, patching_rect=[40, 40, 850, 570]))], lines=[])
    for i in range(4):
        gen['boxes'].append(dict(box=dict(id='out'+str(i),maxclass='newobj',text='out '+str(i+1),patching_rect=[40+i*130,640,70,22])))
        gen['lines'].append(dict(patchline=dict(source=['code',i],destination=['out'+str(i),0])))
    box('control', text='js dream-control.js', rect=[30, 225, 160, 22], numinlets=1, numoutlets=1)
    box('synth', text='gen~', rect=[400, 290, 100, 22], numinlets=1, numoutlets=4, outlettype=['signal']*4, patcher=gen)
    wire('control','synth')
    box('table',text='buffer~ dream_machine_factory_v2 dream-waves.wav',rect=[30,260,345,22])
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
    patch['dependency_cache'] = [dict(name='dream-control.js',type='TEXT',implicit=1),dict(name='dream-waves.wav',type='WAVE',implicit=1)]
    patch['parameters']['parameterbanks'] = {
        '0': dict(index=0,name='Tuning',parameters=['base','octave','transpose','denominator','numerator0','numerator1','numerator2','numerator3']),
        '1': dict(index=1,name='Tone',parameters=['wavepos','shape','attack','release','slew','crossfade','wet','master']),
        '2': dict(index=2,name='Voices',parameters=['gate0','gate1','gate2','gate3','gate4','revtime','size','damping']),
        '3': dict(index=3,name='Wavetable',parameters=['wavetable','wavepos','shape','attack','release','crossfade','wet','master'])}
    return dict(patcher=patch)


if __name__ == '__main__':
    make_waves()
    code = dsp_code()
    (ROOT/'device/dream-engine.genexpr').write_text(code)
    data = json.dumps(make_patch(code), indent=2).encode()+b'\n'
    (OUT/'Hypna.maxpat').write_bytes(data)
    # Same ampf/iiii/meta/ptch layout as Live's installed Max Instrument template.
    payload = data + b'\0'
    header = b'ampf'+struct.pack('<I',4)+b'iiii'+b'meta'+struct.pack('<II',4,0)+b'ptch'+struct.pack('<I',len(payload))
    (OUT/'Hypna.amxd').write_bytes(header+payload)
    print('Built Hypna.maxpat, Hypna.amxd, and factory wavetable.')
