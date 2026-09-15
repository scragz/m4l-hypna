// Execute the generated GenExpr arithmetic in a small JS harness. This checks
// signal behavior, not the Max compiler, host integration, or realtime CPU use.
const fs = require('node:fs');
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.join(__dirname, '../device');
const wav = fs.readFileSync(path.join(root,'hypna-waves.wav'));
const waveData = Float64Array.from({length:(wav.length-44)/2},(_,i)=>wav.readInt16LE(44+i*2)/32768);

class Delay {
    constructor(size) { this.data=new Float64Array(size); this.index=0; }
    read(time) {
        const pos=(this.index-time+this.data.length)%this.data.length;
        const first=Math.floor(pos),frac=pos-first;
        return this.data[first]*(1-frac)+this.data[(first+1)%this.data.length]*frac;
    }
    write(v) { this.data[this.index]=v; this.index=(this.index+1)%this.data.length; }
}

function engine(samplerate=48000) {
    let code=fs.readFileSync(path.join(root,'hypna-engine.genexpr'),'utf8').replace(/\/\/[^\n]*/g,'');
    const functionEnd=code.indexOf('\nBuffer');
    const fn=code.slice(0,functionEnd);
    code=code.slice(functionEnd);
    const params={},history=[];
    code=code.replace(/Param (\w+)\(([^)]+)\);/g,(_,name,value)=>{params[name]=Number(value);return '';});
    code=code.replace(/History (\w+)\(([^)]+)\);/g,(_,name,value)=>{history.push([name,value]);return '';});
    code=code.replace(/Buffer waves\("[^"]+"\);/,'');
    code=code.replace(/Delay (\w+)\((\d+)\);/g,(_,name,size)=>{history.push([name,`new Delay(${size})`]);return '';});
    const assigned=s=>[...new Set([...s.matchAll(/\b([a-zA-Z]\w*)\s*=(?!=)/g)].map(m=>m[1]))];
    const locals=assigned(code).filter(n=>!history.some(h=>h[0]===n));
    const func='function '+fn.replace('{','{\nlet '+assigned(fn).join(',')+';');
    const make=new Function('params','samplerate','waves','Delay',`"use strict";
        const {sin,cos,tanh,exp,pow,ceil,floor,log2,min,max}=Math;
        const pi=Math.PI,twopi=2*pi;
        const clamp=(v,a,b)=>min(b,max(a,v)),mix=(a,b,t)=>a*(1-t)+b*t;
        const wrap=(v,a,b)=>((v-a)%(b-a)+(b-a))%(b-a)+a;
        const peek=(data,index)=>{
            if(index<0 || index>=data.length || !Number.isFinite(index)) throw new Error('Invalid wavetable index '+index);
            return data[Math.floor(index)];
        };
        ${func}
        let ${history.map(([n,v])=>n+'='+v).join(',')};
        return function sample() {
            let {${Object.keys(params).join(',')}}=params;
            let ${locals.join(',')};
            ${code}
            return [out1,out2,out3,out4];
        };`);
    return {params,sample:make(params,samplerate,waveData,Delay),samplerate};
}

test('closed gates are silent and AR reaches its endpoints at the specified times', () => {
    const e=engine();
    for(let n=0;n<1000;n++) assert.deepEqual(e.sample().slice(0,2),[0,0]);
    e.params.gate0=1; e.params.attack=100;
    for(let n=0;n<2400;n++) e.sample();
    assert.ok(Math.abs(e.sample()[3]-0.5)<0.001);
    for(let n=0;n<2400;n++) e.sample();
    assert.equal(e.sample()[3],1);
    e.params.gate0=0; e.params.release=50;
    for(let n=0;n<2401;n++) e.sample();
    assert.equal(e.sample()[3],0);
});

test('fundamental oscillates at the documented frequency', () => {
    const e=engine(); e.params.shape=1;
    let positiveCrossings=0,prev=0;
    for(let n=0;n<48000;n++) {const v=e.sample()[2]; if(prev<0 && v>=0)positiveCrossings++; prev=v;}
    assert.equal(positiveCrossings,58);
});

test('out-of-band fundamentals are silent after retune rather than aliasing', () => {
    const e=engine(); e.params.freq0=30000; e.params.crossfade=0;
    for(let n=0;n<100;n++) e.sample();
    assert.equal(e.sample()[2],0);
});

test('retuning and worst-case gain/reverb remain finite and bounded at 44.1/48/96 kHz', () => {
    for(const sr of [44100,48000,96000]) {
        const e=engine(sr);
        Object.assign(e.params,{wet:50,revtime:30000,master:0,attack:0,release:0,crossfade:30,slew:20});
        for(let v=0;v<5;v++) {e.params['gate'+v]=1;e.params['gain'+v]=6;}
        let energy=0;
        for(let n=0;n<sr/2;n++) {
            if(n%4000===0) {e.params.freq1=60+n/20;e.params.wavepos=(n%12000)/60-100;}
            const [l,r]=e.sample();
            assert.ok(Number.isFinite(l)&&Number.isFinite(r));
            assert.ok(Math.abs(l)<=1 && Math.abs(r)<=1);
            energy+=l*l+r*r;
        }
        assert.ok(energy>1);
    }
});

test('minus 40 dB mutes a voice and stereo pan reaches both sides', () => {
    const e=engine(); Object.assign(e.params,{gate1:1,attack:0,pan1:-100});
    for(let n=0;n<10000;n++)e.sample();
    let l=0,r=0;
    for(let n=0;n<1000;n++){const x=e.sample();l+=x[0]*x[0];r+=x[1]*x[1];}
    assert.ok(l>r*10000);
    e.params.pan1=100;
    for(let n=0;n<10000;n++)e.sample();
    l=0;r=0;
    for(let n=0;n<1000;n++){const x=e.sample();l+=x[0]*x[0];r+=x[1]*x[1];}
    assert.ok(r>l*10000);
    e.params.gain1=-40;
    for(let n=0;n<24000;n++)e.sample();
    assert.ok(Math.abs(e.sample()[1])<1e-12);
});

test('reverb produces a tail that decays after gates close', () => {
    const e=engine();
    Object.assign(e.params,{gate0:1,attack:0,release:0,wet:100,revtime:400,damping:0});
    for(let n=0;n<4800;n++)e.sample();
    e.params.gate0=0;
    let early=0,late=0;
    for(let n=0;n<96000;n++) {
        const [l,r]=e.sample(),energy=l*l+r*r;
        if(n<4800)early+=energy;
        if(n>=91200)late+=energy;
    }
    assert.ok(early>0.001);
    assert.ok(late<early*0.000001);
});

test('all eight banks have audible and distinct movement across the scan range', () => {
    const midpoints=[];
    for(let bank=0;bank<8;bank++) {
        const scans=[];
        for(const position of [-100,0,100]) {
            const e=engine(); Object.assign(e.params,{wavetable:bank,wavepos:position});
            for(let n=0;n<9600;n++)e.sample();
            const raw=[];
            for(let n=0;n<1000;n++)raw.push(e.sample()[2]);
            assert.ok(raw.every(v=>Number.isFinite(v)&&Math.abs(v)<=1.01));
            assert.ok(raw.reduce((s,v)=>s+v*v,0)>5, `silent bank ${bank}`);
            scans.push(raw);
        }
        const difference=(a,b)=>a.reduce((s,v,i)=>s+(v-b[i])**2,0)/a.length;
        assert.ok(difference(scans[0],scans[2])>0.005, `no movement in bank ${bank}`);
        for(const other of midpoints) assert.ok(difference(other,scans[1])>0.005, `duplicate bank ${bank}`);
        midpoints.push(scans[1]);
    }
});

test('bank switching starts continuously and rapid edits settle on the latest bank', () => {
    const e=engine(), reference=engine();
    for(let n=0;n<4800;n++){e.sample();reference.sample();}
    e.params.wavetable=7;
    assert.ok(Math.abs(e.sample()[2]-reference.sample()[2])<0.00001);
    reference.params.wavetable=4;
    for(let n=0;n<4800;n++){
        if(n<1800 && n%100===0)e.params.wavetable=(n/100)%8;
        if(n===1800)e.params.wavetable=4;
        e.sample();reference.sample();
    }
    assert.ok(Math.abs(e.sample()[2]-reference.sample()[2])<1e-10);
});

test('dedicated fundamental shapes ignore the selected bank', () => {
    for(const shape of [1,2,3]) {
        const a=engine(),b=engine();
        Object.assign(a.params,{shape,wavetable:0});
        Object.assign(b.params,{shape,wavetable:7});
        for(let n=0;n<6000;n++)assert.ok(Math.abs(a.sample()[2]-b.sample()[2])<1e-12);
    }
});

test('last bank and frame remain within table bounds across sample rates and pitches', () => {
    for(const sr of [44100,48000,96000]) {
        const e=engine(sr);Object.assign(e.params,{wavetable:7,wavepos:100,crossfade:0});
        for(let n=0;n<sr/10;n++)e.sample();
        for(const frequency of [1,300,700,1400,2800,5600,12000,21500,42000]) {
            e.params.freq0=frequency;
            for(let n=0;n<100;n++)assert.ok(e.sample().every(Number.isFinite));
        }
    }
});
