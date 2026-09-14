"""Packaging/wiring checks. These do not substitute for opening the device in Live."""
import json
import struct
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'device'
raw = (root/'Hypna.amxd').read_bytes()
assert raw[:4] == b'ampf' and raw[8:12] == b'iiii'
assert raw[24:28] == b'ptch'
assert struct.unpack('<I', raw[28:32])[0] == len(raw)-32
doc = json.loads(raw[32:].rstrip(b'\0'))
assert doc == json.loads((root/'Hypna.maxpat').read_text())

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
assert boxes['synth']['patcher']['boxes'][0]['box']['code']==(root/'dream-engine.genexpr').read_text()
with wave.open(str(root/'dream-waves.wav')) as w:
    assert (w.getnchannels(),w.getsampwidth(),w.getnframes())==(1,2,8*7*16*2048)
catalog=json.loads((root/'dream-waves.json').read_text())
assert boxes['wavetable']['saved_attribute_attributes']['valueof']['parameter_enum']==catalog['banks']
assert boxes['wavetable']['saved_attribute_attributes']['valueof']['parameter_initial']==[0]
assert boxes['wavetable-message']['text']=='prepend wavetable'
assert any(e['patchline']['source']==['wavetable-message',0] and e['patchline']['destination']==['synth',0] for e in p['lines'])
assert 'wavetable' in p['parameters']['parameterbanks']['3']['parameters']
assert 'dream_machine_factory_v2' in boxes['table']['text']
print('AMXD container, patch wiring, parameter persistence metadata, presentation bounds, and wavetable checks passed.')
