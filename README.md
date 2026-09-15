# Hypna for Max for Live

An initial **audio instrument** based on the five-voice, prime-ratio drone algorithm.

## Open the device

1. Drag `device/Hypna.amxd` onto a MIDI track in Ableton Live with Max for Live.
2. Turn a voice's **Gate** to **On**. Gates are independent, sustained switches; MIDI notes and Live's transport do not trigger them.
3. Turn gates off to release the drone. Reverb can continue ringing afterward.

The initial output is silent: all five gates are off. Output starts at −12 dB. The device has five fixed voices, not keyboard polyphony.

`device/Hypna.amxd` is **frozen**: the controller script and the factory wavetable are bundled inside the file, so it is the only file you need to move or share. A frozen patcher opens read-only in Max.

For patch work, `scripts/build.py` also writes `device/Hypna.dev.amxd`, an unfrozen device that reads `hypna-control.js` and `hypna-waves.wav` as siblings from `device/`. Keep that folder together when using it. The editable patch is `device/Hypna.maxpat`.

## Tuning

`fundamental Hz = Base Hz × 2^(Octave + Transpose / 12)`

`tone Hz = fundamental Hz × numerator / denominator`

Base Hz represents the manual's thousandths-of-a-Hz parameter in readable Hz, before the octave shift. The default 29.135 × 2 gives **58.270 Hz**. Set Base Hz to 30 with Octave 1 for a 60 Hz fundamental.

| Voice | Default ratio | Default frequency |
| --- | --- | --- |
| Fundamental | 1/1 | 58.270 Hz |
| Tone 1 | 42/32 → 21/16 | 76.479375 Hz |
| Tone 2 | 56/32 → 7/4 | 101.9725 Hz |
| Tone 3 | 62/32 → 31/16 | 112.898125 Hz |
| Tone 4 | 63/32 | 114.7190625 Hz |

Prime controls accept primes up to 32767; composite entries snap to the nearest prime, with lower values winning ties. Prime 1 cannot be disabled. Set any other prime to 1 to disable it. Duplicate primes are harmless.

Denominator values from 1–256 and numerators from 1–1024 snap to the nearest integer whose factors all belong to the selected prime set. Changing primes resnaps the current ratios. Ties choose the lower value. This nearest-value policy is a design choice; the reference does not specify the hardware's selection behavior. The display reports effective ratios and frequencies.

## Sound controls

- Five independent gates and gains. Gain −40 dB means silence. The fundamental is centered; the other four voices have independent pan.
- **Wavetable** selects one of eight original banks. **Wave offset** continuously scans 16 frames within the selected bank, from −100 to +100. Seven harmonic-bandwidth levels reduce aliasing as pitch increases. These tables are generated locally and contain no extracted hardware assets.
- The fundamental can use the shared wavetable, a sine, a band-limited triangle, or a band-limited square.
- Shared linear attack and release times control five independent envelopes. Time controls are in milliseconds. Defaults are 10 ms attack and 1000 ms release.
- Frequency slew is a one-pole time constant in milliseconds. Crossfade uses two phase-aligned oscillators per voice and a complementary cosine fade, defaulting to 20 ms. During a fade, later retunes wait until it finishes; the latest target wins. The displayed Hz is the target while the voice is transitioning.
- Reverb has wet/dry mix, approximate RT60, size, and high-frequency damping. It uses an original four-delay feedback network. Size changes can produce pitch motion in the tail.
- Gains, pan, wavetable position, master output, and reverb mix have 10 ms smoothing. The mix includes per-voice headroom and a final soft saturation stage.
- Frequencies at or above 45% of the current sample rate are muted instead of being folded to another pitch. The target remains visible in the frequency display.

All visible sound and tuning controls are exposed as Live parameters, with named parameter banks. The controller waits for `live.thisdevice` before reading restored tuning values together.

## Wavetable library

| Bank | Movement across Wave offset |
| --- | --- |
| Classic | Sine → triangle → soft saw → square-like; preserves the original prototype's scan |
| Bloom | A soft, dark harmonic stack gradually opens into a bright spectrum |
| Hollow | A resonant band moves through odd harmonics |
| Glass | Two narrow upper-harmonic bands move at different rates |
| Formant | Three broad peaks shift through vocal-like shapes |
| Reed | Odd/even balance and brightness evolve together |
| Fold | Partial polarities progressively invert, changing the waveform's contour |
| Comb | Repeated spectral peaks and notches sweep through the harmonics |

All banks retain integer harmonics of each voice, preserving the prime-ratio tuning. Adjacent frames interpolate continuously and Wave offset has 10 ms smoothing. Bank selection crossfades over 50 ms without resetting oscillator phase; rapid selection changes finish the current fade before switching to the latest request. This is separate from the frequency **Crossfade** control.

For evolving drones, automate **Wave offset** with a slow sweep. The **Wavetable** parameter can also be automated and saved in the Set. The fundamental follows the bank when **Bass wave** is set to **Wavetable**; its dedicated Sine, Triangle, and Square modes remain independent of bank selection.

This release adds a factory selector, not an import browser. The wavetable is frozen into `Hypna.amxd`; only the unfrozen `Hypna.dev.amxd` needs `hypna-waves.wav` beside it. `hypna-waves.json` describes the bank layout for development and is not required at runtime.

## Differences from the reference

This first version implements the musical core and stereo output. It does **not** yet implement:

- The original hardware's MicroSD wavetable library or user wavetable import. The selector currently offers the eight original banks above.
- Six hardware CV inputs, their attenuverters, input selection, and per-voice external FM.
- The hardware's four reverb models, separate early/diffuse levels, or reverb modulation speed/depth.
- The hardware's undocumented 0–127 timing curves. Millisecond controls are used instead.
- Physical fundamental-wave/envelope outputs. The corresponding raw signals are available at the embedded `gen~` object's third and fourth outlets for patch development, but only stereo audio is sent to Live.

The factory wavetable, timing defaults, reverb, snapping policy, and retuning behavior are explicit adaptations, not claims about the original DSP.

## Build and verification

Requires Python 3 to rebuild; Node.js to run the behavioral tests. No third-party packages are required.

```sh
python3 scripts/build.py
node --test tests/*.test.cjs
python3 tests/structure.py
```

Everything hand-maintained lives in `src/`; the whole `device/` folder is build output and is not tracked, so changes made only to generated files are overwritten by a rebuild.

| `src/` | role |
| --- | --- |
| `hypna-control.js` | The tuning controller, copied into `device/` and frozen into the device. |
| `hypna-engine.genexpr` | The GenExpr DSP, as real GenExpr. `scripts/build.py` expands it into the `gen~` patcher. |
| `hypna-waves.json` | Declares the wavetable layout: banks, frames, cycle length, and mip harmonics. |

`src/hypna-waves.json` is the single layout source. It drives the generated tables **and** supplies the constants the DSP indexes them with, so a layout change reaches both. `tests/structure.py` asserts the two agree; before, the indexing constants were hardcoded in the DSP and a change to the frame count would have silently produced wrong offsets.

`src/hypna-engine.genexpr` uses three markers, because GenExpr has no arrays of `History` and the five voices must be unrolled:

- `//@voices` … `//@end` repeats once per voice, with `$V` as the voice index and `$F` as that voice's default frequency.
- `//@fundamental` … `//@end`, inside a voices block, emits for voice 0 only — the `Bass wave` overrides.
- `//@doc` … `//@end` documents the template and is stripped from the output.

Any other `$NAME` is a layout constant from the manifest.

`scripts/build.py` owns the patch layout and the wavetable math (`spectrum()` defines the eight banks). It generates `Hypna.maxpat`, the frozen `Hypna.amxd`, the unfrozen `Hypna.dev.amxd`, the expanded `.genexpr`, and the `.wav`. The wavetable is deterministic output of `spectrum()` and the declared layout, so it is generated rather than tracked.

Freezing writes Max's collective format: an `mx@c` header, each file's bytes, then a `dlst` footer of `dire` records naming each file's type, size, offset, and modification date. Chunk sizes inside the collective are big-endian and include their own 8-byte header; the outer `ampf`/`meta`/`ptch` sizes are little-endian. The layout was checked against [Ableton's `maxdiff`](https://github.com/Ableton/maxdevtools/tree/main/maxdiff), which reads the result as a frozen Instrument Device with both dependencies bundled.

The structural checks parse the frozen device back out and compare every bundled entry against the file on disk, so a container mistake fails the build rather than Live. The 15 behavioral tests cover tuning/factor restrictions, restored tuning, DSP arithmetic, envelopes, frequency, pan, muting, output bounds, distinct bank/scan sounds, smooth bank changes, rapid selection, independent bass shapes, and table indexing across sample rates. Additional structural checks cover dependency presence, AMXD chunk sizes, frozen-collective round-tripping, selector wiring/persistence metadata, and presentation bounds. The DSP harness translates the generated arithmetic into JavaScript; it **does not compile GenExpr or emulate Live**.

Implementation references: Cycling '74's [GenExpr documentation](https://docs.cycling74.com/userguide/gen/gen_genexpr/), [Gen operators](https://docs.cycling74.com/userguide/gen/gen~_operators/), and [Live parameter controls](https://docs.cycling74.com/reference/live.numbox/). The AMXD header follows the installed Ableton Max Instrument template.
