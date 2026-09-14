// Tuning controller for Hypna. Owns the prime set, ratio snapping, the
// frequency messages sent to the embedded gen~ patcher, and the ratio/Hz
// readout.
//
// Max loads this as `js dream-control.js`; the Node tests require it directly.
// Nothing outside the Max-only guard at the bottom may touch a Max global at
// load time, or `require` of this file would throw.

var PRIME_MAX = 32767;
var DENOMINATOR_MAX = 256;
var NUMERATOR_MAX = 1024;

var state = {
    base: 29.135,
    octave: 1,
    transpose: 0,
    primes: [2, 3, 7, 31],
    denominator: 32,
    numerators: [42, 56, 62, 63]
};

// Live restores parameters one at a time, in no guaranteed order. Ignore every
// UI message until live.thisdevice reports the device is loaded: resnapping a
// half-restored prime set would quietly rewrite a saved custom tuning.
var restored = false;

function isPrime(value) {
    if (value < 2) return false;
    if (value % 2 === 0) return value === 2;
    for (var factor = 3; factor * factor <= value; factor += 2) {
        if (value % factor === 0) return false;
    }
    return true;
}

// Prime 1 cannot be disabled; the other three accept 1 to drop out of the set.
// Composite entries snap to the nearest prime, lower value winning ties.
function nearestPrime(value, optional) {
    var target = Math.round(value);
    if (optional && target <= 1) return 1;
    if (target < 2) return 2;
    if (target > PRIME_MAX) target = PRIME_MAX;
    for (var distance = 0; distance <= PRIME_MAX; distance++) {
        if (target - distance >= 2 && isPrime(target - distance)) return target - distance;
        if (target + distance <= PRIME_MAX && isPrime(target + distance)) return target + distance;
    }
    return 2;
}

// Every value up to max whose factors all belong to the selected primes.
// Duplicate and disabled (1) primes contribute nothing, so 1 is always allowed.
function allowedValues(primes, max) {
    var factors = [];
    for (var i = 0; i < primes.length; i++) {
        var prime = Math.round(primes[i]);
        if (prime > 1 && factors.indexOf(prime) < 0) factors.push(prime);
    }
    var values = [1];
    for (var f = 0; f < factors.length; f++) {
        var grown = [];
        for (var v = 0; v < values.length; v++) {
            for (var value = values[v]; value <= max; value *= factors[f]) grown.push(value);
        }
        values = grown;
    }
    values.sort(function (a, b) { return a - b; });
    return values;
}

// `allowed` is ascending, so a strict comparison keeps the lower value on ties.
function nearestAllowed(value, allowed) {
    var best = allowed[0];
    for (var i = 1; i < allowed.length; i++) {
        if (Math.abs(allowed[i] - value) < Math.abs(best - value)) best = allowed[i];
    }
    return best;
}

function greatestCommonDivisor(a, b) {
    while (b) {
        var remainder = a % b;
        a = b;
        b = remainder;
    }
    return a;
}

// fundamental Hz = base x 2^(octave + transpose/12); tone Hz = fundamental x n/d.
function tuning(settings) {
    var fundamental = settings.base * Math.pow(2, settings.octave + settings.transpose / 12);
    var frequencies = [fundamental];
    var ratios = [];
    for (var i = 0; i < settings.numerators.length; i++) {
        var numerator = settings.numerators[i];
        var divisor = greatestCommonDivisor(numerator, settings.denominator);
        ratios.push((numerator / divisor) + '/' + (settings.denominator / divisor));
        frequencies.push(fundamental * numerator / settings.denominator);
    }
    return { ratios: ratios, frequencies: frequencies };
}

function named(name) {
    return typeof patcher === 'undefined' ? null : patcher.getnamed(name);
}

function read(name, fallback) {
    var box = named(name);
    if (!box) return fallback;
    var value = box.getvalueof();
    if (value instanceof Array) value = value[0];
    return typeof value === 'number' && isFinite(value) ? value : fallback;
}

// `set` updates a live.numbox without making it send again, so writing a
// snapped value back cannot start a message loop.
function write(name, value) {
    var box = named(name);
    if (box && box.getvalueof() !== value) box.message('set', value);
}

function hertz(value) {
    var text = value.toFixed(4);
    while (text.indexOf('.') >= 0 && (text.charAt(text.length - 1) === '0' || text.charAt(text.length - 1) === '.')) {
        text = text.slice(0, -1);
    }
    return text + ' Hz';
}

function display(result) {
    var fundamental = named('pitch0');
    if (fundamental) fundamental.message('set', hertz(result.frequencies[0]));
    for (var i = 0; i < result.ratios.length; i++) {
        var box = named('pitch' + (i + 1));
        if (box) box.message('set', result.ratios[i] + '   ' + hertz(result.frequencies[i + 1]));
    }
}

// Snap the current settings, push the corrections back to the UI, then report
// the resulting frequencies to gen~.
function apply() {
    for (var i = 0; i < state.primes.length; i++) {
        state.primes[i] = nearestPrime(state.primes[i], i > 0);
    }
    var denominators = allowedValues(state.primes, DENOMINATOR_MAX);
    var numerators = allowedValues(state.primes, NUMERATOR_MAX);
    state.denominator = nearestAllowed(state.denominator, denominators);
    for (var n = 0; n < state.numerators.length; n++) {
        state.numerators[n] = nearestAllowed(state.numerators[n], numerators);
    }

    for (var p = 0; p < state.primes.length; p++) write('prime' + p, state.primes[p]);
    write('denominator', state.denominator);
    for (var w = 0; w < state.numerators.length; w++) write('numerator' + w, state.numerators[w]);

    var result = tuning(state);
    display(result);
    for (var voice = 0; voice < result.frequencies.length; voice++) {
        outlet(0, 'freq' + voice, result.frequencies[voice]);
    }
}

function update(name, value) {
    var index = Number(name.slice(-1));
    if (name === 'base') state.base = value;
    else if (name === 'octave') state.octave = Math.round(value);
    else if (name === 'transpose') state.transpose = Math.round(value);
    else if (name === 'denominator') state.denominator = Math.round(value);
    else if (name.indexOf('prime') === 0 && index >= 0 && index < state.primes.length) {
        state.primes[index] = Math.round(value);
    } else if (name.indexOf('numerator') === 0 && index >= 0 && index < state.numerators.length) {
        state.numerators[index] = Math.round(value);
    } else return;
    apply();
}

// Every tuning parameter arrives as `<name> <value>` via a prepend object.
function anything() {
    if (!restored || arguments.length === 0) return;
    update(messagename, arguments[0]);
}

// Sent once by live.thisdevice through deferlow, after Live has restored the
// whole parameter set.
function restore() {
    restored = true;
    state.base = read('base', state.base);
    state.octave = read('octave', state.octave);
    state.transpose = read('transpose', state.transpose);
    state.denominator = read('denominator', state.denominator);
    for (var p = 0; p < state.primes.length; p++) {
        state.primes[p] = read('prime' + p, state.primes[p]);
    }
    for (var n = 0; n < state.numerators.length; n++) {
        state.numerators[n] = read('numerator' + n, state.numerators[n]);
    }
    apply();
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        tuning: tuning,
        allowedValues: allowedValues,
        nearestPrime: nearestPrime,
        nearestAllowed: nearestAllowed
    };
} else {
    inlets = 1;
    outlets = 1;
    autowatch = 1;
}
