import os
from devices.OscilloscopeDPO70k import Oscilloscope
from devices.TEC1092 import TEC1092
import json
import numpy as np
from scipy.signal import find_peaks
from scipy.optimize import curve_fit
import time
from datetime import datetime as dt
import matplotlib.pyplot as plt
import tqdm

COORDINATES_FILE = "devices\\instrument_coordinates.json"
with open(COORDINATES_FILE, "r") as f:
    COORDINATES = json.load(f)

SETTINGS_FILE = "settings.json"
with open(SETTINGS_FILE, "r") as f:
    SETTINGS = json.load(f)

SOURCE="measurements\\20251119_195906\\data.json"

def chunk_array(arr, size):
    return [arr[i:i + size] for i in range(0, len(arr), size)]


def gaussian(x, A, mu, sigma):
    return A * np.exp(-(x - mu) ** 2 / (2 * sigma ** 2))


def cos2(x, A, B, k, phi):
    return A + B * (np.cos(k * x + phi)) ** 2


def interference_voltage_estimation(osc: Oscilloscope) -> tuple:
    """
    Returns (mean_peak_amplitude, std_peak_amplitude).
    If no valid peaks are found returns (np.nan, np.nan).
    """
    voltages = np.asarray(osc.readVolt()[0])  # ensure numpy array

    sampling_rate = SETTINGS["sampling_rate"]
    sampling_period = int(SETTINGS["period"] * sampling_rate)
    if sampling_period <= 0:
        raise ValueError("Computed sampling_period <= 0. Check SETTINGS['period'] and sampling_rate.")

    chunks = chunk_array(voltages, sampling_period)[1:]
    heights = []

    delay = SETTINGS["delay"]
    delay_samples = int((delay * sampling_rate) // 2)
    if delay_samples < 1:
        delay_samples = 1
    vai=SETTINGS["debug"]
    for chunk in chunks:
        chunk = np.asarray(chunk)
        if chunk.size == 0:
            continue

        # Find peak indices
        peaks = find_peaks(chunk)[0]  # properties not requested; use chunk[peaks] for heights
        if peaks.size == 0:
            continue

        heights_arr = chunk[peaks]
        # Create list of [index_in_chunk, height] and sort by height desc
        arr = [[int(peaks[i]), float(heights_arr[i])] for i in range(len(peaks))]
        arr = sorted(arr, key=lambda x: x[1], reverse=True)

        # Not enough peaks? skip this chunk
        if len(arr) < 3:
            # If there are at least 1 peak, we can still try to fit around the largest
            if len(arr) == 1:
                interference_peak_index = arr[0][0]
            else:
                # two peaks -> take the larger
                interference_peak_index = arr[0][0]
        else:
            # take the middle of the top-3 peaks after sorting by position
            top3_by_height = arr[:3]
            top3_sorted_by_pos = sorted(top3_by_height, key=lambda x: x[0])
            interference_peak_index = top3_sorted_by_pos[1][0]

        # Choose window around that peak within chunk
        low = max(0, interference_peak_index - delay_samples)
        high = min(len(chunk), interference_peak_index + delay_samples)
        if high - low < 3:
            # too few points to fit a Gaussian
            continue
        xs = np.arange(low, high, dtype=float)
        ys = chunk[low:high].astype(float)

        # initial guess for gaussian: amplitude, mean (in chunk coordinates), sigma
        A0 = float(np.max(ys))
        mu0 = float(interference_peak_index)
        sigma0 = max(1.0, (high - low) / 6.0)
        p0 = [A0, mu0, sigma0]

        try:
            popt, pcov = curve_fit(gaussian, xs, ys, p0=p0, maxfev=2000)
            A, mu, sigma = popt
            heights.append(float(A))
                
            if vai:
                peaks_x=[]
                peaks_y=[]
                vai=False
                peaks_x+=[low,interference_peak_index,high]
                peaks_y+=[0,chunk[interference_peak_index],0]
                plt.scatter(peaks_x,peaks_y,color="green")
                plt.plot(np.arange(len(chunk)),chunk,color="blue")
                xspace=np.arange(len(chunk))
                yspace=gaussian(xspace,A,mu,sigma)
                plt.plot(xspace,yspace,color="red")
                plt.show()
        except Exception:
            # fit failed for this chunk; skip it
            continue

    if len(heights) == 0:
        return float("nan"), float("nan")

    return float(np.mean(heights)), float(np.std(heights))


def set_and_wait(tec: TEC1092, end: float, tolerance: float) -> None:
    tec.set_temperature(end)
    # simple polling loop with a bit longer sleep to avoid hammering the COM port
    count=0
    while count<3:
        while abs(tec.read_temperature() - end) > tolerance:
            time.sleep(0.1)
            count=0
        count+=1
        time.sleep(0.1)


def initial_guess(x: list, y: list) -> tuple:
    """
    Provide an initial guess (A, B, k, phi) for cos2 fit.
    A = offset (min)
    B = amplitude (max-min)
    k = spatial frequency guess -> one full oscillation across span
    phi = 0
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    if x_arr.size == 0:
        return (0.0, 1.0, 1.0, 0.0)
    A = float(np.min(y_arr))
    B = float(np.max(y_arr) - np.min(y_arr))
    span = float(np.max(x_arr) - np.min(x_arr))
    k = (2 * np.pi / span) if span != 0 else 1.0
    phi = 0.0
    return (A, B, k, phi)


def main() -> None:
    OSC = Oscilloscope(
        usb_address=COORDINATES["DPO"],
        active_channels=SETTINGS["channels"],
        connect_at_start=True,
        memory=SETTINGS["memory"],
    )
    TEC = TEC1092(port=SETTINGS["TEC"]["port"])

    # use numpy.arange but ensure numeric types are plain floats for JSON later
    temperatures = np.arange(
        SETTINGS["TEC"]["start"],
        SETTINGS["TEC"]["end"],
        SETTINGS["TEC"]["step"],
        dtype=float,
    )
    temperature_it=tqdm.tqdm(temperatures)
    interference = []
    
    # safe filename (no slashes or colons)
    file_name = dt.now().strftime("%Y%m%d_%H%M%S")
    # Convert to JSON-serializable structure
    data_to_save = {
        "data": [{"temperature": t, "mean": m, "std": s} for (t, m, s) in interference],
        "settings": SETTINGS,
    }
    with open(SOURCE,mode="r") as f:
        data=json.load(f)
    bha=data["data"]
    # Prepare plotting, skip any NaN measurements
    temps = bha["temperature"]
    means = bha["mean"]
    std = bha["std"]
    if len(temps) == 0:
        print("No valid interference data collected.")
        return
    plt.scatter(temps,means,marker='o',color="blue")
    plt.errorbar(temps, means,
                 yerr=std,label="data",
                 barsabove=True,
                 fmt='none',
                 capsize=6,
                 capthick=2,
                 elinewidth=2,
                 color="blue")
    x_space = np.linspace(SETTINGS["TEC"]["start"], SETTINGS["TEC"]["end"], 1000)

    try:
        p0 = initial_guess(temps, means)
        temps_arr = np.asarray(temps)
        means_arr = np.asarray(means)

        popt, pcov = curve_fit(
            cos2,
            temps_arr,
            means_arr,
            p0=p0,
            maxfev=5000,
            bounds=([0,0,0,-np.inf],[np.inf,np.inf,np.inf,np.inf])
        )

        y_space = cos2(x_space, *popt)
        plt.plot(x_space, y_space, label="fit",color="green")
        A, B, k, phi = popt
        visibility = B / (2 * A + B) if (2 * A + B) != 0 else float("nan")
        print(f"Fitted Visibility: {visibility:.3f}")
        M,m=max(means),min(means)
        raw=((M-m)/(M+m))
        print(f"Raw Visibility: {raw:.3f}")
    except Exception as e:
        print(f"cos2 fit failed: {e}")

    plt.xlabel("Temperature")
    plt.ylabel("Interference amplitude (mean)")
    plt.legend()
    plt.grid(True)
    plt.show()


if __name__ == "__main__":
    main()
