"""Packaging/wiring checks. These do not substitute for opening the device in Live."""
import json
import re
import struct
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'device'


def outer(name):
    """Read the ampf/meta/ptch chunks. Outer chunk sizes are little-endian."""
    raw = (name if isinstance(name, bytes) else (root/name).read_bytes())
    assert raw[:4] == b'ampf' and raw[8:12] == b'iiii'
    assert raw[12:16] == b'meta' and struct.unpack('<I', raw[16:20])[0] == 4
    assert raw[24:28] == b'ptch'
    assert struct.unpack('<I', raw[28:32])[0] == len(raw)-32
    return raw[32:]


def chunks(data):
    """Walk collective chunks. Sizes are big-endian and include the 8-byte header."""
    fields = []
    while len(data) >= 8:
        tag = data[:4].decode('ascii')
        size = struct.unpack('>I', data[4:8])[0]
        assert 8 <= size <= len(data), tag
        fields.append((tag, data[8:size]))
        data = data[size:]
    assert not data
    return fields


def unfreeze(payload):
    """Parse an mx@c collective back into {name: (type, flag, bytes)}."""
    assert payload[:4] == b'mx@c'
    assert struct.unpack('>I', payload[4:8])[0] == 16
    footer_at = int.from_bytes(payload[8:16], 'big')
    footer = payload[footer_at:]
    [(tag, directory)] = chunks(footer)
    assert tag == 'dlst'
    contents, covered = {}, 16
    for tag, record in chunks(directory):
        assert tag == 'dire'
        fields = dict(chunks(record))
        name = fields['fnam'].rstrip(b'\0').decode('ascii')
        offset = struct.unpack('>I', fields['of32'])[0]
        size = struct.unpack('>I', fields['sz32'])[0]
        # Entries are stored back to back between the header and the footer.
        assert offset == covered, name
        covered += size
        assert struct.unpack('>I', fields['vers'])[0] == 0
        # HFS+ dates count seconds from 1904; anything else is a bad timestamp.
        assert struct.unpack('>I', fields['mdat'])[0] > 2082844800
        contents[name] = (fields['type'].rstrip(b'\0').decode('ascii'),
                          struct.unpack('>I', fields['flag'])[0],
                          payload[offset:offset+size])
    assert covered == footer_at
    return contents


source = json.loads((root/'Hypna.maxpat').read_text())

# The development device carries the patch alone and reads sibling dependencies.
assert json.loads(outer('Hypna.dev.amxd').rstrip(b'\0')) == source

# The distribution device is frozen: patcher plus every dependency, in one file.
frozen = unfreeze(outer('Hypna.amxd'))
assert list(frozen) == ['Hypna.amxd', 'hypna-control.js', 'hypna-waves.wav', 'hypna-theme.js', 'hypna-art.js']
kind, flag, patch_data = frozen['Hypna.amxd']
assert (kind, flag) == ('JSON', 17)
doc = json.loads(patch_data.rstrip(b'\0'))
# Freezing only marks the project read-only; nothing else about the patch moves.
assert doc['patcher'].pop('project')['readonly'] == 1
assert source['patcher'].pop('project')['readonly'] == 0
assert doc == source
for dependency in ['hypna-control.js', 'hypna-waves.wav', 'hypna-theme.js', 'hypna-art.js']:
    kind, flag, data = frozen[dependency]
    assert flag == 0 and data == (root/dependency).read_bytes(), dependency
assert frozen['hypna-control.js'][0] == 'TEXT'
assert frozen['hypna-waves.wav'][0] == 'WAVE'
doc = json.loads((root/'Hypna.maxpat').read_text())

def check(p):
    ids = [x['box']['id'] for x in p['boxes']]
    assert len(ids) == len(set(ids))
    for edge in p['lines']:
        assert edge['patchline']['source'][0] in ids
        assert edge['patchline']['destination'][0] in ids
    for b in p['boxes']:
        b=b['box']
        if 'patcher' in b: check(b['patcher'])
        if b.get('presentation'):
            x,y,w,h=b['presentation_rect']
            assert x>=0 and y>=0 and x+w<=1110 and y+h<=169, b['id']
check(doc['patcher'])
p=doc['patcher']
boxes={x['box']['id']:x['box'] for x in p['boxes']}
for name,b in boxes.items():
    if b.get('parameter_enable'):
        assert name in p['parameters']
        assert b['saved_attribute_attributes']['valueof']['parameter_initial_enable']==1
        assert any(e['patchline']['source'][0]==name for e in p['lines'])
for dep in p['dependency_cache']:
    assert (root/dep['name']).is_file()
assert boxes['synth']['patcher']['boxes'][0]['box']['code']==(root/'hypna-engine.genexpr').read_text()
catalog=json.loads((root/'hypna-waves.json').read_text())
banks,mips,frames,cycle=len(catalog['banks']),len(catalog['harmonics']),catalog['frames'],catalog['cycle_samples']
with wave.open(str(root/'hypna-waves.wav')) as w:
    assert (w.getnchannels(),w.getsampwidth(),w.getnframes())==(1,2,banks*mips*frames*cycle)

# The DSP indexes the table with constants expanded from the same manifest that
# generated it. If a layout change ever reaches one and not the other, the device
# reads the wrong offsets and still sounds plausible, so assert they agree.
dsp=(root/'hypna-engine.genexpr').read_text()
indexing=re.search(r'offset = \(\(clamp\(floor\(bank\), 0, (\d+)\) \* (\d+) \+ level\) \* (\d+) \+ first\) \* (\d+);',dsp)
assert indexing, 'wavetable indexing line not found in the generated DSP'
assert [int(n) for n in indexing.groups()]==[banks-1,mips,frames,cycle]
assert 'frame = clamp(position, 0, %d);'%(frames-1) in dsp
assert 'first = min(floor(frame), %d);'%(frames-2) in dsp
assert 'hz * %d / (sr * 0.45)'%catalog['harmonics'][0] in dsp
assert 'clamp(floor(wavetable + 0.5), 0, %d)'%(banks-1) in dsp
# Positions within a frame set may be fractional; tableosc interpolates. Format
# them the way the generator does, or this check only passes for some layouts.
literal=lambda v: repr(int(v) if float(v).is_integer() else v)
assert '+ 100) * %s,'%literal((frames-1)/200) in dsp
assert 'History smoothwave(%s);'%literal((frames-1)/2) in dsp
# The template's voice block is unrolled once per voice, fundamental extras aside.
assert dsp.count('// Voice ')==5 and dsp.count('osc4 = mix(a4, b4, weight4);')==1
assert 'pos0 = shape == 2 ? %s :'%literal((frames-1)/3) in dsp
assert boxes['wavetable']['saved_attribute_attributes']['valueof']['parameter_enum']==catalog['banks']
assert boxes['wavetable']['saved_attribute_attributes']['valueof']['parameter_initial']==[0]
assert boxes['wavetable-message']['text']=='prepend wavetable'
assert any(e['patchline']['source']==['wavetable-message',0] and e['patchline']['destination']==['synth',0] for e in p['lines'])
assert 'wavetable' in p['parameters']['parameterbanks']['3']['parameters']
assert 'hypna_factory_v2' in boxes['table']['text']
print('Frozen and development AMXD containers, patch wiring, parameter persistence metadata, '
      'presentation bounds, and wavetable checks passed.')
