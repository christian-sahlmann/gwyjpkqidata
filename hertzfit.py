import multiprocessing
import numpy as np
import scipy.optimize

def hertz(x, xc, E, Rc=1e-6, nu=.5):
    F = 4.0/3 * E/(1-nu**2) * scipy.sqrt(Rc * (xc-x)**3)
    return F.real

def line(x, slope, offset):
    return x*slope + offset

def threshold_level(data):
    noise_level = data[ : len(data) * .4 ].std()
    return 5 * noise_level

def find_fit_region_start(data):
    try:
        fit_region_start = np.argwhere(data > threshold_level(data))[0,0]
    except IndexError:
        fit_region_start = 0
    return fit_region_start

def fit(xdata, ydata, depth=None, setpoint=None, depthcount=None):
    ydata = subtract_baseline(xdata, ydata)
    fit_region_start = find_fit_region_start(ydata)
    approximate_cp = xdata[fit_region_start]

    fit_region_end = len(xdata)
    if depthcount:
        fit_region_end = min([fit_region_end, fit_region_start+depthcount])
    if depth:
        try:
            fit_region_end = min([fit_region_end, np.argwhere(xdata < xdata[fit_region_start]-depth)[0,0]])
        except IndexError:
            pass
    if setpoint:
        fit_region_end = min([fit_region_end, np.argwhere(ydata > setpoint)[0,0]])

    try:
        popt, pcov = scipy.optimize.curve_fit(hertz,
                                              xdata[fit_region_start : fit_region_end],
                                              ydata[fit_region_start : fit_region_end],
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

def fit_index(index, xdata, ydata, depth, setpoint):
    return index, fit(xdata, ydata, depth, setpoint)

def fit_all(nominal_height, force, depth=None, setpoint=None):
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
        pool.apply_async(fit_index, (index, nominal_height[index], force[index], depth, setpoint), callback=fit_callback)

    pool.close()
    pool.join()

    return cp, cperr, E, Eerr

plugin_type = "VOLUME"
plugin_menu = "/Hertz fit"

import gtk, gwy, site
site.addsitedir(gwy.gwy_find_self_dir('data')+'/pygwy')
import gwyutils

def run():
    global force_brick, height_brick
    force_brick = gwy.data['/brick/0']
    height_brick = gwy.data['/brick/1']
    pascal = gwy.SIUnit()
    pascal.set_from_string('Pa')
    dialog = gtk.Dialog('Hertz fit', buttons=('Fit all', gtk.RESPONSE_ACCEPT))
    dialog.connect('response', on_response)
    def add_checkbutton(method, title, *args):
        checkButton = gtk.CheckButton(title)
        checkButton.connect('toggled', method, title, *args)
        dialog.vbox.add(checkButton)
    add_checkbutton(map, '2D map')
    add_checkbutton(toggle_window, 'Force', force_brick.get_si_unit_w(), None, 'Distance')
    add_checkbutton(toggle_window, 'Young modulus', pascal, 5, 'Indentation depth')
    add_checkbutton(toggle_window, 'Young modulus standard error', pascal, 5, 'Indentation depth')
    add_checkbutton(toggle_window, 'Contact point', height_brick.get_si_unit_w(), 5, 'Indentation depth')
    add_checkbutton(toggle_window, 'Contact point standard error', height_brick.get_si_unit_w(), 5, 'Indentation depth')
    dialog.show_all()

def on_response(dialog, response_id):
    if response_id != gtk.RESPONSE_ACCEPT:
        return
    force = gwyutils.brick_data_as_array(force_brick)
    height = gwyutils.brick_data_as_array(height_brick)
    cp, cperr, E, Eerr = fit_all(height, force, depth=indentation_depth)
    def add_datafield(index, data, title, unit):
        datafield = gwy.DataField(height_brick.get_xres(), height_brick.get_yres(),
                                  height_brick.get_xreal(), height_brick.get_yreal(), False)
        datafield.set_si_unit_xy(height_brick.get_si_unit_x())
        datafield.set_si_unit_z(unit)
        mask = np.isinf(data)
        data[mask] = 0
        gwyutils.data_field_set_data(datafield, data)
        key = '/{}/data'.format(index)
        gwy.data[key] = datafield
        gwy.data[key + '/title'] = title
    pascal = gwy.SIUnit()
    pascal.set_from_string('Pa')
    add_datafield(0, E, 'Young modulus', pascal)
    add_datafield(1, Eerr, 'Young modulus standard error', pascal)
    add_datafield(2, cp, 'Contact point', height_brick.get_si_unit_w())
    add_datafield(3, cperr, 'Contact point standard error', height_brick.get_si_unit_w())
    dialog.destroy()

def map(togglebutton, title):
    def on_button_press(dataView, event):
        global points
        x, y = dataView.coords_xy_to_real(int(event.x), int(event.y))
        points.append((x,y))
        coords = '({:.1e},{:.1e})'.format(x,y)
        i = force_brick.rtoi(x)
        j = force_brick.rtoj(y)
        force = gwyutils.brick_data_as_array(force_brick)[i,j]
        height = gwyutils.brick_data_as_array(height_brick)[i,j]

        def add_curve(title, xdata, ydata, description=None, mode=2, line_style=gtk.gdk.LINE_SOLID):
            if title not in windows:
                return
            xdata = np.array(xdata)
            ydata = np.array(ydata)
            mask = np.isfinite(ydata)
            graphCurveModel = gwy.GraphCurveModel()
            graphCurveModel.set_data(xdata[mask].tolist(), ydata[mask].tolist(), len(xdata[mask]))
            graphCurveModel.props.mode = mode
            graphCurveModel.props.line_style = line_style
            if description:
                graphCurveModel.props.description = description + ' ' + coords
            else:
                graphCurveModel.props.description = coords
            windows[title].get_graph().get_model().add_curve(graphCurveModel)

        (cp, E), _ = fit(height, force)
        threshold = threshold_level(force)
        add_curve('Force', height, subtract_baseline(height, force), 'data')
        add_curve('Force', height, hertz(height, cp, E), 'fit')
        add_curve('Force', [cp], [hertz(cp, cp, E)], 'contact point', mode=3)
        add_curve('Force', [height.min(), height.max()], [threshold, threshold], 'threshold level', line_style=gtk.gdk.LINE_ON_OFF_DASH)

        fit_region_start = find_fit_region_start(subtract_baseline(height, force))
        cp = []
        cperr = []
        E = []
        Eerr = []
        for i in range(2, len(height)-fit_region_start):
            popt, perr = fit(height, force, depthcount=i)
            cp.append(popt[0])
            cperr.append(perr[0])
            E.append(popt[1])
            Eerr.append(perr[1])
        depth = height[fit_region_start] - height[fit_region_start:fit_region_start+i-1]
        add_curve('Young modulus', depth, E)
        add_curve('Young modulus standard error', depth, Eerr)
        add_curve('Contact point', depth, cp)
        add_curve('Contact point standard error', depth, cperr)

    global dataWindow
    if togglebutton.props.active:
        layer = gwy.LayerBasic()
        layer.set_data_key('/brick/1/preview')
        dataView = gwy.DataView(gwy.data)
        dataView.set_base_layer(layer)
        dataView.connect('button-press-event', on_button_press)
        dataWindow = gwy.DataWindow(dataView)
        dataWindow.connect('delete-event', lambda a,b: togglebutton.set_active(False))
        dataWindow.show_all()
    else:
        dataWindow.destroy()
        del dataWindow

windows = {}
points = []
indentation_depth = None
def toggle_window(togglebutton, title, unit, status, label_bottom):
    def on_selection_finished(selection):
        global indentation_depth
        indentation_depth = selection.get_data()[0]
        for title, window in windows.iteritems():
            window.get_graph().get_area().get_selection(5).set_data(1, selection.get_data())
        for num, (x, y) in enumerate(points):
            i = force_brick.rtoi(x)
            j = force_brick.rtoj(y)
            force = gwyutils.brick_data_as_array(force_brick)[i,j]
            height = gwyutils.brick_data_as_array(height_brick)[i,j]
            (cp, E), _ = fit(height, force, depth=indentation_depth)
            model = windows['Force'].get_graph().get_model()
            model.get_curve(num*3 + 1).set_data(height.tolist(), hertz(height, cp, E).tolist(), len(force))
            model.get_curve(num*3 + 2).set_data([cp], [hertz(cp, cp, E)], 1)

    if togglebutton.props.active:
        windows[title] = window = gwy.Graph(gwy.GraphModel()).window_new()
        window.props.title = title
        graph = window.get_graph()
        if status:
            graph.set_status(status)
            graph.get_area().get_selection(status).connect('finished', on_selection_finished)
        model = graph.get_model()
        model.props.si_unit_x = height_brick.get_si_unit_w()
        model.props.si_unit_y = unit
        model.props.axis_label_bottom = label_bottom
        model.props.axis_label_left = title
        window.connect('delete-event', lambda a,b: togglebutton.set_active(False))
        window.show_all()
    else:
        windows[title].destroy()
        del windows[title]
        if title == 'Force':
            points.clear()
