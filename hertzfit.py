import site, os
site.addsitedir(os.path.expanduser('~/.gwyddion/pygwy'))

from jpkqidata import JpkQiData
import matplotlib
import matplotlib.pyplot as plt
import multiprocessing
import numpy as np
import sys
import scipy.optimize

matplotlib.rcParams['axes.formatter.limits'] = [-4, 4]
matplotlib.rcParams['image.cmap'] = 'afmhot'

def interactive(nominal_height, force):
    def on_click(event):
        if event.inaxes == ax0:
            global point
            point = event.ydata, event.xdata
            xdata = nominal_height[point]
            ydata = force[point]
            ax1.plot(xdata, subtract_baseline(xdata, ydata))

            popt, _ = fit(xdata, ydata)
            ax1.plot(xdata, hertz(xdata, *popt))

            fit_region_start = find_fit_region_start(subtract_baseline(xdata, ydata))
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
                    ax2.xaxis.set_label_text('Indentation depth')
                    ax2.yaxis.set_label_text('Young modulus')

                    ax3.clear()
                    ax3.plot(Eerr)
                    ax3.xaxis.set_label_text('Indentation depth')
                    ax3.yaxis.set_label_text('Young modulus standard error')

                    plt.draw()
                    plt.pause(0.01)

        elif event.inaxes == ax2:
            indentation_depth = event.xdata
            xdata = nominal_height[point]
            ydata = force[point]
            popt, perr = fit(xdata, ydata, indentation_depth)
            fit_start = find_fit_region_start(subtract_baseline(xdata, ydata))
            ax1.clear()
            ax1.plot(xdata, subtract_baseline(xdata, ydata))
            ax1.plot(xdata[fit_start:fit_start+indentation_depth], hertz(xdata[fit_start:fit_start+indentation_depth], *popt))

        elif not event.inaxes:
            ax1.clear()
            ax2.clear()

        plt.draw()

    fig, ((ax0, ax3), (ax1, ax2)) = plt.subplots(2, 2)
    im = ax0.imshow(np.nanmin(nominal_height, 2))
    fig.colorbar(im, ax=ax0)

    ax1.xaxis.set_label_text('Nominal height / m')
    ax1.yaxis.set_label_text('Force / N')

    fig.canvas.mpl_connect('button_press_event', on_click)

    def fit_all_clicked(event):
        cp, cperr, E, Eerr = fit_all(nominal_height, force)
        fig, ((ax0, ax1), (ax3, ax5), (ax2, ax4)) = plt.subplots(3, 2)
        im0 = ax0.imshow(np.nanmin(nominal_height, 2))
        im2 = ax2.imshow(E)
        im3 = ax3.imshow(cp)
        im4 = ax4.imshow(Eerr)
        im5 = ax5.imshow(cperr)
        fig.colorbar(im0, ax=ax0)
        fig.colorbar(im2, ax=ax2)
        fig.colorbar(im3, ax=ax3)
        fig.colorbar(im4, ax=ax4)
        fig.colorbar(im5, ax=ax5)
        def on_click(event):
            if event.inaxes in [ax0,ax2,ax3,ax4,ax5]:
                point = event.ydata, event.xdata
                xdata = nominal_height[point]
                ydata = force[point]
                ax1.plot(xdata, subtract_baseline(xdata, ydata))
                ax1.plot(xdata, hertz(xdata, cp[point], E[point]))
            else:
                ax1.clear()
            plt.draw()
        fig.canvas.mpl_connect('button_press_event', on_click)
        plt.show()
    ax = plt.axes([0.8, 0.025, 0.1, 0.04])
    button = matplotlib.widgets.Button(ax, 'Fit all')
    button.on_clicked(fit_all_clicked)
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
    ydata = subtract_baseline(xdata, ydata)
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

def fit_index(index, xdata, ydata):
    return index, fit(xdata, ydata)

def fit_all(nominal_height, force):
    cp = np.empty(force.shape[:2])
    cperr = np.empty(force.shape[:2])
    E = np.empty(force.shape[:2])
    Eerr = np.empty(force.shape[:2])
    def fit_callback(parameters):
        index, (popt, perr) = parameters
        cp[index] = popt[0]
        cperr[index] = perr[0]
        E[index] = popt[1]
        Eerr[index] = perr[1]

    pool = multiprocessing.Pool()
    for index in np.ndindex(E.shape):
        pool.apply_async(fit_index, (index, nominal_height[index], force[index]), callback=fit_callback)

    pool.close()
    pool.join()

    return cp, cperr, E, Eerr

if __name__ == "__main__":
    jpkqidata = JpkQiData(sys.argv[1])
    extend = jpkqidata.segment('extend')
    nominal_height = extend.channel('capacitiveSensorHeight').calibrate('nominal')
    force = extend.channel('vDeflection').calibrate('force')

    interactive(nominal_height, force)
