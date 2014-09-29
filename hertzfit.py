import site, os
site.addsitedir(os.path.expanduser('~/.gwyddion/pygwy'))

from jpkqidata import JpkQiData
import matplotlib.pyplot as plt
import numpy as np
import sys
import scipy.optimize

def hertzfit(filename):
    def get_data(x, y):
        xdata = nominal_height[x, y]
        ydata = force[x, y]
        ydata = subtract_baseline(xdata, ydata)
        return xdata, ydata

    def on_click(event):
        if event.inaxes == ax0:
            global point
            point = event.xdata, event.ydata
            xdata, ydata = get_data(*point)
            ax1.plot(xdata, ydata)

            popt, _ = fit(xdata, ydata)
            ax1.plot(xdata, hertz(xdata, *popt))

            fit_region_start = find_fit_region_start(ydata)
            cp = []
            E = []
            Eerr = []
            for i in range(2, len(xdata)-fit_region_start):
                popt, perr = fit(xdata, ydata, i)
                cp.append(popt[0])
                E.append(popt[1])
                Eerr.append(perr[1])
                if i % 50 == 0:
                    ax2.clear()
                    ax2.plot(E)
                    ax3.clear()
                    ax3.plot(Eerr)
                    plt.draw()
                    plt.pause(0.01)

        elif event.inaxes == ax2:
            indentation_depth = event.xdata
            xdata, ydata = get_data(*point)
            popt, perr = fit(xdata, ydata, indentation_depth)
            fit_start = find_fit_region_start(ydata)
            ax1.clear()
            ax1.plot(xdata, ydata)
            ax1.plot(xdata[fit_start:fit_start+indentation_depth], hertz(xdata[fit_start:fit_start+indentation_depth], *popt))

        elif not event.inaxes:
            ax1.clear()
            ax2.clear()

        plt.draw()

    jpkqidata = JpkQiData(filename)

    nominal_height = jpkqidata.segment('extend').channel('capacitiveSensorHeight').calibrate('nominal')
    force = jpkqidata.segment('extend').channel('vDeflection').calibrate('force')

    fig, ((ax0, ax3), (ax1, ax2)) = plt.subplots(2, 2)
    ax0.imshow(np.nanmin(nominal_height, 2).T, plt.cm.afmhot)

    fig.canvas.mpl_connect('button_press_event', on_click)
    plt.show()

    cp = np.empty((64, 64))
    E = np.empty((64, 64))
    for i in range(64):
        for j in range(64):
            data = get_data(i,j)
            popt, perr = fit(*data, depth=600)
            cp[i,j] = popt[0]
            E[i,j] = popt[1]

    fig, ((ax0, ax3), (ax1, ax2)) = plt.subplots(2, 2)
    ax0.imshow(np.nanmin(nominal_height, 2), plt.cm.afmhot)
    ax1.imshow(E, plt.cm.afmhot)
    ax3.imshow(cp, plt.cm.afmhot)
    plt.show()

def hertz(x, xc, E, Rc=1e-6, nu=.5):
    F = 4.0/3 * E/(1-nu**2) * scipy.sqrt(Rc * (xc-x)**3)
    return F.real

def line(x, slope, offset):
    return x*slope + offset

def find_fit_region_start(data):
    noise_level = data[ : len(data) * .4 ].std()
    threshold_level = 5 * noise_level
    try:
        fit_region_start = np.argwhere(data > threshold_level)[0,0]
    except IndexError:
        fit_region_start = 0
    return fit_region_start

def fit(xdata, ydata, depth=None, setpoint=None):
    fit_region_start = find_fit_region_start(ydata)
    approximate_cp = xdata[fit_region_start]

    if not depth:
        depth = len(xdata) - fit_region_start

    if setpoint:
        depth = np.min(depth, fit_region_start - (np.argwhere(ydata > setpoint)[0,0]))

    try:
        popt, pcov = scipy.optimize.curve_fit(hertz,
                                              xdata[fit_region_start : fit_region_start+depth],
                                              ydata[fit_region_start : fit_region_start+depth],
                                              (approximate_cp, 0))
        perr = np.sqrt(np.diag(pcov))
    except RuntimeError:
        popt = perr = float('nan'), float('nan')
    except TypeError:
        popt = perr = float('nan'), float('nan')

    return popt, perr

def subtract_baseline(xdata, ydata):
    baseline, _ = scipy.optimize.curve_fit(line,
                                           xdata[:len(xdata)*.4],
                                           ydata[:len(xdata)*.4])
    return ydata - line(xdata, *baseline)

if __name__ == "__main__":
    hertzfit(sys.argv[1])
