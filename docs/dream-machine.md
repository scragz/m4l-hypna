### **Hypna**

**Controls / Inputs / Outputs mapping diagram:**

* **L Knob:** Wave offset
* **R Knob:** *(Unlabeled rotary control)*
* **Input 5:** Wave input
* **Output 1 & 2:** Stereo outputs
* **Output 3:** Fundamental wave
* **Output 4:** Fundamental envelope

This algorithm is designed to generate drones, allowing the user to explore non-traditional harmonies based on prime ratios. It was inspired by the theories of composer La Monte Young. An interesting read is the pdf "Notes on The Theatre of Eternal Music" available in a number of places online e.g. here.

The output is a combination of five sounds - the fundamental and four harmonies. The prime ratios that define the frequency relationships are controlled by parameters.

The algorithm uses wavetable synthesis to generate the tones. Additionally the fundamental may instead be a pure sine, triangle or square wave.

Each tone has a simple attack/release envelope, controlled by its own gate parameter.

By default little is mapped to the CV inputs, and it is perfectly possible to drive the algorithm entirely by hand. You may however like to map the inputs as FM inputs, or to control the gates.

An overall reverb effect is included which is applied to the stereo outputs.

#### **Setting the fundamental**

The fundamental is the fixed tone (usually the bass note) that everything else revolves around. You may like to set it to a concert pitch (it defaults to concert Bb) or some other frequency (La Monte Young sometimes chose the mains frequency - 60Hz in the USA - or you could tune it to the resonant frequency of whatever environment you find yourself in).

---

### **Page 78**

It can be dialled in via the parameter (in thousandths of a Hz), or set from the algorithm's menu.

*(Image of screen: Hypna menu showing "Set Fundamental")*

Note that the Hz value shown in the display also takes into account the octave parameter.

*(Images of screen showing: 2. Fundamental 29135 58.270Hz and 13:Octave 1 2048 58.270Hz)*

#### **Setting the primes**

Parameters 8-11 let you choose the set of prime numbers that will make up the allowable values for the frequency ratios. La Monte Young famously chose the primes 2, 3, 7 & 31, and moreover specifically avoided the prime 5, thereby excluding major thirds from his tunings.

If you want less than four primes, set the unwanted parameters to '1'.

#### **Setting the frequency ratios**

To set the ratios of tones 1-4 relative to the fundamental, set the parameters for the denominator and the four numerators.

*(Images of screen showing: 14: Denominator 32 32 1024 and 15: Numerator 1 42 42/32 76.47Hz 1024)*

When setting the numerators, the pitch of the tone is shown, as well as the ratio reduced to its lowest form. For example 48/32 reduces to 3/2, the familiar form of the perfect fifth in just intonation.

*(Image of screen showing: 16: Numerator 2 48 48/32 87.40Hz 1024)*

#### **Outputs**

* **Outputs 1 & 2** are the main stereo mix.


* **Output 3** is the fundamental waveform (unaffected by its gain and envelope).


* **Output 4** is the fundamental's envelope.



#### **Parameters**

| # | Name | Min | Max | Default | Unit | Description |
| --- | --- | --- | --- | --- | --- | --- |
| 1-6 | Attenuverter 1-6 | -200 | 200 | 100 | % | Applies an attenuverter to the corresponding input. A negative value indicates that the CV will be inverted. |
| 7 | Wavetable | 0 | 999 | 0 |  | Chooses the wavetable from those installed on the MicroSD card. See below. |
| 8 | Prime 1 | 2 | 32767 | 2 |  | Sets one of the four primes that may be multiplied to create the denominator and numerators of the frequency ratios. |
| 9 | Prime 2 | 1 | 32767 | 3 |  | Sets the second prime. |
| 10 | Prime 3 | 1 | 32767 | 7 |  | Sets the third prime. |
| 11 | Prime 4 | 1 | 32767 | 31 |  | Sets the fourth prime. |

---

### **Page 79**

| # | Name | Min | Max | Default | Unit | Description |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | Fundamental | 1 | 32767 | 29135 |  | Sets the fundamental frequency, in thousandths of a Hz. |
| 13 | Octave | -8 | 8 | 1 |  | Sets an octave shift for the fundamental. |
| 14 | Denominator | 1 | 256 | 32 |  | Sets the denominator of the frequency ratios. |
| 15 | Numerator 1 | 1 | 1024 | 42 |  | Sets the numerator of the frequency ratio of tone 1. |
| 16 | Numerator 2 | 1 | 1024 | 56 |  | Sets the numerator of the frequency ratio of tone 2. |
| 17 | Numerator 3 | 1 | 1024 | 62 |  | Sets the numerator of the frequency ratio of tone 3. |
| 18 | Numerator 4 | 1 | 1024 | 63 |  | Sets the numerator of the frequency ratio of tone 4. |
| 19 | Gate 0 | 0 | 1 | 0 |  | Gate for the fundamental. |
| 20-23 | Gate 1-4 | 0 | 1 | 0 |  | Gates for tones 1-4. |
| 24 | Gain 0 | -40 | 6 | 0 | dB | Gain for the fundamental. "-40" is treated as -∞dB. |
| 25-28 | Gain 1-4 | -40 | 6 | 0 | dB | Gains for tones 1-4. "-40" is treated as -∞dB. |
| 29-32 | Pan 1-4 | -100 | 100 | 0 | % | Stereo pan position for tones 1-4. |
| 33 | Wave input | 0 | 6 | 5 |  | Which input to use to control the position in the wavetable, or '0' for 'None'. |
| 34 | Wave offset | -100 | 100 | 0 |  | An offset for the wavetable position, added to that set from the wave input. |
| 35 | Attack time | 0 | 127 | 0 |  | Attack time for the envelopes. |
| 36 | Decay time | 0 | 127 | 0 |  | Decay time for the envelopes. |
| 37-40 | FM input 1-4 | 0 | 6 | 0 |  | Which input to use to frequency modulate (FM) tones 1-4, or '0' for 'None'. The inputs are scaled according to the FM Range parameter. |
| 41 | Waveform 0 | 0 | 3 | 0 |  | Chooses the waveform for the fundamental. Options 0-3 are Wavetable, Sine, Triangle and Square, respectively. |
| 42 | FM Range | 0 | 3 | 0 |  | Sets the scaling for the FM inputs. The options are 1Hz/V, 10Hz/V, 100Hz/V or 1kHz/V. |
| 43 | Frequency slew | 0 | 127 | 0 |  | Sets a slew rate for any change in voice frequency. |
| 44 | Crossfade time | 0 | 127 | 0 |  | Sets a crossfade time for any change in voice frequency. |
| 45 | Reverb mix | 0 | 100 | 0 | % | A wet/dry control for the reverb effect. |
| 46 | Reverb time | 400 | 30000 | 1700 | ms | The reverb time. |

---

### **Page 80**

| # | Name | Min | Max | Default | Unit | Description |
| --- | --- | --- | --- | --- | --- | --- |
| 47 | Reverb model | 0 | 3 | 1 |  | Chooses the reverb model. |
| 48 | Reverb size | 1 | 100 | 100 | % | Sets the size of the reverb space - mainly affects the times of the early reflections. |
| 49 | Reverb high damp | 0 | 100 | 60 |  | Sets the amount of high frequency damping in the reverb tail. |
| 50 | Reverb mod speed | 1 | 500 | 250 | 0.01 Hz | Sets the speed of reverb modulation. |
| 51 | Reverb mod depth | 0 | 100 | 25 |  | Sets the depth of reverb modulation. |
| 52 | Reverb early gain | -40 | 6 | -12 | dB | Sets the output level of the early reflections. |
| 53 | Reverb diff gain | -40 | 6 | -6 | dB | Sets the output level of the diffuse reflections. |
| 54 | Transpose | -60 | 60 | 0 |  | Adjusts the tuning of all frequencies in (12-TET) semitone steps. |

#### **Default mappings**

* The **'L' knob** is mapped to 'Wave offset'.


* **Input 5** is mapped to 'Wave input'.
