const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const c = require('../device/hypna-control.js');
const defaults = () => ({base:29.135, octave:1, transpose:0, primes:[2,3,7,31], denominator:32, numerators:[42,56,62,63]});

test('documented defaults and reduced ratios', () => {
    const t = c.tuning(defaults());
    assert.deepEqual(t.ratios, ['21/16','7/4','31/16','63/32']);
    [58.27,76.479375,101.9725,112.898125,114.7190625].forEach((hz,i) => assert.ok(Math.abs(t.frequencies[i]-hz)<1e-9));
});

test('optional primes, duplicates, and primes larger than the ratio range', () => {
    assert.deepEqual(c.allowedValues([2,1,1,1],32),[1,2,4,8,16,32]);
    assert.deepEqual(c.allowedValues([2,2,32749,1],32),[1,2,4,8,16,32]);
    assert.deepEqual(c.allowedValues([32749,1,1,1],1024),[1]);
    assert.equal(c.nearestPrime(1,false),2);
    assert.equal(c.nearestPrime(1,true),1);
    assert.equal(c.nearestPrime(32767,false),32749);
    assert.equal(c.nearestPrime(6,true),5);
});

test('all snapped ratios contain only allowed prime factors', () => {
    for (const primes of [[2,3,7,31],[2,1,1,1],[3,5,11,17],[32749,1,1,1]]) {
        const allowed = c.allowedValues(primes,1024);
        for (let n=1;n<=1024;n++) {
            const snapped=c.nearestAllowed(n,allowed);
            assert.ok(allowed.includes(snapped));
            assert.ok(allowed.every(v => Math.abs(v-n)>=Math.abs(snapped-n)));
        }
    }
});

test('octave and transpose preserve ratios and support 60 Hz', () => {
    const s = defaults(); s.base=30;
    assert.equal(c.tuning(s).frequencies[0],60);
    s.transpose=12;
    assert.equal(c.tuning(s).frequencies[0],120);
    s.octave=0;
    assert.equal(c.tuning(s).frequencies[0],60);
});

test('initial UI messages cannot overwrite restored custom tuning', () => {
    const s = defaults();
    const values = {base:30,octave:1,transpose:0,denominator:25,prime0:5,prime1:1,prime2:1,prime3:1,numerator0:25,numerator1:125,numerator2:625,numerator3:1};
    const output=[];
    const context={outlet:(...x)=>output.push(x),patcher:{getnamed:name=>({getvalueof:()=>values[name],message:(selector,v)=>values[name]=v})}};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(require.resolve('../device/hypna-control.js'),'utf8'),context);
    context.messagename='prime0'; context.anything(2);
    assert.equal(output.length,0);
    context.restore();
    assert.equal(values.denominator,25);
    assert.equal(values.numerator2,625);
    assert.equal(output[0][2],60);
    context.messagename='prime0'; context.anything(2);
    assert.equal(values.prime0,2);
    assert.equal(values.denominator,32);
});
