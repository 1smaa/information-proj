# Visibility Extraction Script for Tektronix Oscilloscopes (TekScope + TCPIP)

This Python script acquires **pulsed interference data** from a **Tektronix oscilloscope** via **TCPIP (TekScope / SCPI)** and computes the **visibility** of an interference fringe during a **temperature scan of an unbalanced Mach–Zehnder Interferometer (MZI) chip)**.

It is designed for **quantum optics experiments** where the interferometer produces distinct pulse bins:

* **Early–early** (non-interfering)
* **Interference bin** (early–late + late–early)
* **Late–late** (non-interfering)

The script automatically **selects the interference bin**, discards the other two, and extracts amplitude via **Gaussian fitting**. The full interference fringe across temperature is then **cos² fitted** for accurate visibility extraction.

---

## Features

* Remote **TCPIP connection** to Tektronix oscilloscopes using TekScope/SCPI
* Acquisition of waveform data in real-time during temperature scans
* **Automatic peak detection** in each pulse window
* **Exclusion of early–early and late–late bins**
* **Gaussian fit** to each interference pulse for precise amplitude extraction
* Construction of the interference vs. temperature curve
* **Cos² fit** of the full fringe to compute visibility
* Optional **error bars** from repeated acquisitions
* Logging of raw and processed data with timestamps
* Publication-quality plots of interference fringes

---

## Requirements

* Python 3.9+
* Packages: `numpy`, `scipy`, `matplotlib`, `pyvisa`, `tqdm`

Install via pip:

```bash
pip install numpy scipy matplotlib pyvisa tqdm
```

* Tektronix oscilloscope compatible with TekScope SCPI commands
* OSC and TEC devices configured in `devices/instrument_coordinates.json`
* Settings provided in `settings.json` (sampling rate, TEC range, delay, etc.)

---

## How It Works

1. **Connects to oscilloscope and TEC controller** using VISA/TCPIP.
2. Loops over a **temperature scan** (set in `settings.json`).
3. For each waveform:

   * Segments the waveform into pulse windows
   * Detects peaks using automatic **peak detection**
   * Chooses the **central interference pulse**
   * **Excludes early–early and late–late peaks**
   * Fits a **Gaussian** to the interference peak and extracts its amplitude
4. Builds the interference curve as a function of temperature.
5. Performs a **cos² fit** of the interference fringe to determine visibility.
6. Saves **JSON data**, **plots**, and prints both **raw** and **fit-based visibility**.

---

## Usage

```bash
python visibility.py
```

Optional settings are read from `settings.json`:

* TEC start/end/step temperature
* Sampling rate and period
* Delay around the interference peak
* Active oscilloscope channels
* Debug plotting flags

The script automatically saves outputs in `measurements/<timestamp>/`:

* `data.json` → raw temperature, mean amplitude, and std
* `fig.png` → interference curve plot
* Console prints of **raw** and **cos²-fit visibility**

---

## Output

* **Scatter plot** of interference amplitudes vs. temperature
* **Error bars** representing amplitude variation (optional)
* **Cos² fit curve** overlay
* Visibility values:

```text
Raw Visibility: (I_max - I_min)/(I_max + I_min)
Fitted Visibility: B / (2A + B)  # from cos² fit
```

---

## Notes

* Gaussian fitting provides robust amplitude extraction from noisy pulsed signals.
* Cos² fitting accounts for the periodic physics of the MZI, giving more accurate visibility than raw max/min.
* Script is optimized for **unbalanced MZI chips** in pulsed quantum optics setups.
* Designed for Tektronix + TekScope combo, remote-controlled via TCPIP, compatible with your lab configuration.

---

## File Structure

```
├── visibility.py             # Main acquisition & processing script
├── devices/                  # OSC & TEC classes
├── measurements/             # Output data saved automatically
├── settings.json             # Acquisition and TEC parameters
├── instrument_coordinates.json
└── README.md
```
