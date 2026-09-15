/* Max's classic js object uses ES5. The pure tuning functions also run in Node. */
autowatch = 1;
inlets = 1;
outlets = 1;

function bounded(value, low, high) {
    value = Number(value);
    return isFinite(value) ? Math.max(low, Math.min(high, value)) : low;
}

function isPrime(n) {
    if (n < 2 || n !== Math.floor(n)) return false;
    for (var d = 2; d * d <= n; d++) if (n % d === 0) return false;
    return true;
}

function nearestPrime(value, allowOne) {
    var n = Math.round(bounded(value, allowOne ? 1 : 2, 32767));
    if (allowOne && n === 1) return 1;
    for (var distance = 0; distance < 32767; distance++) {
        if (n - distance >= 2 && isPrime(n - distance)) return n - distance;
        if (n + distance <= 32767 && isPrime(n + distance)) return n + distance;
    }
    return 2;
}

function allowedValues(primes, maximum) {
    var result = [];
    for (var n = 1; n <= maximum; n++) {
        var remainder = n;
        for (var j = 0; j < primes.length; j++) {
            var p = primes[j];
            if (p > 1) while (remainder % p === 0) remainder /= p;
        }
        if (remainder === 1) result.push(n);
    }
    return result;
}

function nearestAllowed(value, values) {
    var best = values[0];
    for (var i = 1; i < values.length; i++) {
        if (Math.abs(values[i] - value) < Math.abs(best - value)) best = values[i];
    }
    return best;
}

function gcd(a, b) {
    while (b) { var temp = b; b = a % b; a = temp; }
    return a;
}

function tuning(state) {
    var primes = state.primes.map(function (p, i) { return nearestPrime(p, i > 0); });
    var den = nearestAllowed(bounded(state.denominator, 1, 256), allowedValues(primes, 256));
    var choices = allowedValues(primes, 1024);
    var nums = state.numerators.map(function (n) { return nearestAllowed(bounded(n, 1, 1024), choices); });
    var hz = bounded(state.base, 0.001, 32.767) * Math.pow(2, Math.round(bounded(state.octave, -8, 8)) + Math.round(bounded(state.transpose, -60, 60)) / 12);
    return {
        primes: primes, denominator: den, numerators: nums,
        frequencies: [hz].concat(nums.map(function (n) { return hz * n / den; })),
        ratios: nums.map(function (n) { var d = gcd(n, den); return (n / d) + "/" + (den / d); })
    };
}

var state = {base: 29.135, octave: 1, transpose: 0, primes: [2, 3, 7, 31], denominator: 32, numerators: [42, 56, 62, 63]};
var ready = false;

function setUI(name, value) {
    var control = this.patcher.getnamed(name);
    if (control) control.message("set", value);
}

function refresh() {
    var result = tuning(state);
    state.primes = result.primes;
    state.denominator = result.denominator;
    state.numerators = result.numerators;
    for (var p = 0; p < 4; p++) {
        setUI("prime" + p, state.primes[p]);
        setUI("numerator" + p, state.numerators[p]);
    }
    setUI("denominator", state.denominator);
    for (var v = 0; v < 5; v++) {
        outlet(0, "freq" + v, result.frequencies[v]);
        setUI("pitch" + v, (v ? result.ratios[v - 1] + "   " : "1/1   ") + result.frequencies[v].toFixed(3) + " Hz");
    }
}

function anything() {
    if (!ready) return;
    var value = Number(arguments[0]);
    if (!isFinite(value)) return;
    var name = messagename;
    if (name === "base" || name === "octave" || name === "transpose" || name === "denominator") state[name] = value;
    else if (/^prime[0-3]$/.test(name)) state.primes[Number(name.slice(-1))] = value;
    else if (/^numerator[0-3]$/.test(name)) state.numerators[Number(name.slice(-1))] = value;
    else return;
    refresh();
}

// After Live restores parameters, read them together before snapping ratios.
// Initial output messages can arrive in any order, so defer the initial read.
function restore() {
    var names = ["base", "octave", "transpose", "denominator"];
    for (var i = 0; i < names.length; i++) state[names[i]] = Number(this.patcher.getnamed(names[i]).getvalueof());
    for (var p = 0; p < 4; p++) {
        state.primes[p] = Number(this.patcher.getnamed("prime" + p).getvalueof());
        state.numerators[p] = Number(this.patcher.getnamed("numerator" + p).getvalueof());
    }
    ready = true;
    refresh();
}

if (typeof module !== "undefined") module.exports = {isPrime: isPrime, nearestPrime: nearestPrime, allowedValues: allowedValues, nearestAllowed: nearestAllowed, tuning: tuning};
