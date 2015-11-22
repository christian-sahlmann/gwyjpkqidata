import multiprocessing
import numpy as np
import scipy.optimize


def hertz(x, xc, E, Rc=1e-6, nu=.5):
    """
    >>> xdata = np.array([5,4,3,2,1])
    >>> hertz(xdata, 4, 1, 1)
    array([ 0.        ,  0.        ,  1.77777778,  5.02831489,  9.23760431])
    """
    F = 4.0/3 * E/(1-nu**2) * scipy.sqrt(Rc * (xc-x)**3)
    return F.real


def line(x, slope, offset):
    """
    >>> line(1, 2, 3)
    5
    """
    return x*slope + offset


def threshold_level(data, factor):
    """
    >>> threshold_level(np.array([5,4,3,2,1]), 5)
    2.5
    >>> xdata = np.array([1,2,3,4,5])
    >>> ydata = hertz(xdata, 4, 1, 1)
    >>> threshold_level(ydata, 1)
    2.1046447092981704
    """
    noise_level = data[ : len(data) * .4 ].std()
    return factor * noise_level


def find_fit_region_start(data, threshold_factor):
    """
    >>> xdata = np.array([5,4,3,2,1])
    >>> ydata = hertz(xdata, 4, 1, 1)
    >>> find_fit_region_start(ydata, 1)
    2
    """
    try:
        fit_region_start = np.argwhere(data > threshold_level(data,threshold_factor))[0,0]
    except IndexError:
        fit_region_start = 0
    return fit_region_start


def fit(xdata, ydata, depth=None, setpoint=None, depthcount=None, threshold_factor=5):
    """
    >>> xdata = np.array([5,4,3,2,1])
    >>> ydata = hertz(xdata, 4, 1, 1)
    >>> fit(xdata, ydata)
    (array([    4.,  1000.]), array([  1.02387605e-15,   6.26993478e-13]))
    """
    ydata = subtract_baseline(xdata, ydata)
    fit_region_start = find_fit_region_start(ydata, threshold_factor)
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
    """
    >>> xdata = np.array([1,2,3,4,5])
    >>> subtract_baseline(xdata,xdata)
    array([  8.72857342e-13,  -4.36539693e-13,  -1.74615877e-12,
            -3.05533376e-12,  -4.36450875e-12])
    """
    baseline, _ = scipy.optimize.curve_fit(line,
                                           xdata[:len(xdata)*.4],
                                           ydata[:len(xdata)*.4])
    return ydata - line(xdata, *baseline)


def fit_index(index, xdata, ydata, depth, setpoint, threshold_factor):
    return index, fit(xdata, ydata, depth, setpoint, threshold_factor=threshold_factor)


def fit_all(nominal_height, force, depth=None, setpoint=None, threshold_factor=5):
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
        pool.apply_async(fit_index, (index, nominal_height[index], force[index], depth, setpoint, threshold_factor), callback=fit_callback)

    pool.close()
    pool.join()

    return cp, cperr, E, Eerr

plugin_type = "VOLUME"
plugin_menu = "/Hertz fit"

import gtk, gwy, site
site.addsitedir(gwy.gwy_find_self_dir('data')+'/pygwy')
import gwyutils

dataView = None
forceGraph = gwy.Graph(gwy.GraphModel())
youngGraph = gwy.Graph(gwy.GraphModel())
youngErrorGraph = gwy.Graph(gwy.GraphModel())
indentationDepthEntry = gtk.Entry()

def run():
    """
    >>> gwy.data = gwy.Container()
    >>> gwy.data['/brick/0'] = gwy.Brick(1,1,1,1,1,1,True)
    >>> gwy.data['/brick/1'] = gwy.Brick(1,1,1,1,1,1,True)
    >>> run()
    """
    global force_brick, height_brick
    for key in gwy.data.keys_by_name():
        if key.endswith('/title'):
            title = gwy.data[key]
            brick = gwy.data[key[:-6]]
            if title == 'extend vDeflection force':
                force_brick = brick
            if title == 'extend height calibrated':
                height_brick = brick
    dialog = gtk.Window()
    dialog.add(gtk.HBox())
    right = gtk.VBox()
    left = gtk.VBox()
    dialog.child.add(left)
    dialog.child.add(right)

    forceModel = forceGraph.get_model()
    forceModel.props.si_unit_x = height_brick.get_si_unit_w()
    forceModel.props.si_unit_y = force_brick.get_si_unit_w()
    forceModel.props.axis_label_bottom = 'Distance'
    forceModel.props.axis_label_left = 'Force'
    forceGraphWindow = gwy.Graph.window_new(forceGraph)
    forceGraphWindowChild = forceGraphWindow.child
    forceGraphWindow.remove(forceGraphWindowChild)
    right.add(forceGraphWindowChild)

    base_layer = gwy.LayerBasic()
    base_layer.props.data_key = '/brick/0/preview'
    global dataView
    dataView = gwy.DataView(gwy.data)
    dataView.set_base_layer(base_layer)
    dataWindow = gwy.DataWindow(dataView)
    dataWindowChild = dataWindow.child
    dataWindow.remove(dataWindowChild)
    import gobject
    top_layer = gobject.new("GwyLayerPoint")
    dataView.set_top_layer(top_layer)
    top_layer.props.selection_key = "/0/select/pointer"
    top_layer.props.point_numbers = True
    selection = top_layer.ensure_selection()
    selection.props.max_objects = 10
    selection.connect('finished', on_dataView_button_press)
    rightbottom = gtk.HBox()
    rightbottom.add(dataWindowChild)
    controls = gtk.VBox()
    rightbottom.add(controls)
    controls.add(indentationDepthEntry)
    controls.add(gtk.Button("Fit all"))
    right.add(rightbottom)

    pascal = gwy.SIUnit()
    pascal.set_from_string('Pa')

    youngErrorModel = youngErrorGraph.get_model()
    youngErrorModel.props.si_unit_x = height_brick.get_si_unit_w()
    youngErrorModel.props.si_unit_y = pascal
    youngErrorModel.props.axis_label_bottom = 'Indentation depth'
    youngErrorModel.props.axis_label_left = 'Young modulus standard error'
    youngErrorGraph.set_status(gwy.GRAPH_STATUS_XLINES)
    youngErrorGraph.get_area().get_selection(gwy.GRAPH_STATUS_XLINES).connect('finished', on_selection_finished)
    youngErrorGraphWindow = gwy.Graph.window_new(youngErrorGraph)
    youngErrorGraphWindowChild = youngErrorGraphWindow.child
    youngErrorGraphWindow.remove(youngErrorGraphWindowChild)
    left.add(youngErrorGraphWindowChild)

    youngModel = youngGraph.get_model()
    youngModel.props.si_unit_x = height_brick.get_si_unit_w()
    youngModel.props.si_unit_y = pascal
    youngModel.props.axis_label_bottom = 'Indentation depth'
    youngModel.props.axis_label_left = 'Young modulus'
    youngGraph.set_status(gwy.GRAPH_STATUS_XLINES)
    youngGraph.get_area().get_selection(gwy.GRAPH_STATUS_XLINES).connect('finished', on_selection_finished)
    youngGraphWindow = gwy.Graph.window_new(youngGraph)
    youngGraphWindowChild = youngGraphWindow.child
    youngGraphWindow.remove(youngGraphWindowChild)
    left.add(youngGraphWindowChild)

    dialog.show_all()


def on_response(dialog, response_id):
    if response_id != gtk.RESPONSE_ACCEPT:
        return
    force = gwyutils.brick_data_as_array(force_brick)
    height = gwyutils.brick_data_as_array(height_brick)
    cp, cperr, E, Eerr = fit_all(height, force, depth=indentation_depth, threshold_factor=threshold_factor)
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


def on_dataView_button_press(selection):

    def add_curve(graph_model, xdata, ydata, description=None, mode=2, line_style=gtk.gdk.LINE_SOLID):
        xdata = np.array(xdata)
        ydata = np.array(ydata)
        mask = np.isfinite(ydata)
        if len(xdata[mask]) == 0:
            return
        graphCurveModel = gwy.GraphCurveModel()
        graphCurveModel.set_data(xdata[mask].tolist(), ydata[mask].tolist(), len(xdata[mask]))
        graphCurveModel.props.mode = mode
        graphCurveModel.props.line_style = line_style
        if description:
            graphCurveModel.props.description = description + ' ' + str(num+1)
        else:
            graphCurveModel.props.description = str(num+1)
        graph_model.add_curve(graphCurveModel)

    data = selection.get_data()
    fit_region_start = []
    force = []
    height = []
    cp = []
    cperr = []
    E = []
    Eerr = []
    forceGraphModel = gwy.GraphModel()
    try:
        depth = float(indentationDepthEntry.props.text)
    except ValueError:
        depth = None
    for num in range(len(data)/2):
        x, y = data[num:num+2]
        i = force_brick.rtoi(x)
        j = force_brick.rtoj(y)
        force.append(gwyutils.brick_data_as_array(force_brick)[i,j])
        height.append(gwyutils.brick_data_as_array(height_brick)[i,j])
        add_curve(forceGraphModel, height[num], subtract_baseline(height[num], force[num]), 'data')

        (cp1, E1), _ = fit(height[num], force[num], depth=depth, threshold_factor=threshold_factor)
        add_curve(forceGraphModel, height[num], hertz(height[num], cp1, E1), 'fit')
        add_curve(forceGraphModel, [cp1], [hertz(cp1, cp1, E1)], 'contact point', mode=3)

        threshold = threshold_level(force[num], threshold_factor)
        add_curve(forceGraphModel, [height[num].min(), height[num].max()], [threshold, threshold], 'threshold level', line_style=gtk.gdk.LINE_ON_OFF_DASH)
        fit_region_start.append(find_fit_region_start(subtract_baseline(height[num], force[num]), threshold_factor))
        cp.append([])
        cperr.append([])
        E.append([])
        Eerr.append([])
    forceGraph.get_model().remove_all_curves()
    forceGraph.get_model().append_curves(forceGraphModel, 4)

    for i in range(2, len(height[num])-fit_region_start[num]):
        youngGraphModel = gwy.GraphModel()
        youngErrorGraphModel = gwy.GraphModel()
        for num in range(len(data)/2):
            popt, perr = fit(height[num], force[num], depthcount=i, threshold_factor=threshold_factor)
            cp[num].append(popt[0])
            cperr[num].append(perr[0])
            E[num].append(popt[1])
            Eerr[num].append(perr[1])
            depth = height[num][fit_region_start[num]] - height[num][fit_region_start[num]:fit_region_start[num]+i-1]
            add_curve(youngGraphModel, depth, E[num])
            add_curve(youngErrorGraphModel, depth, Eerr[num])
        youngGraph.get_model().remove_all_curves()
        youngGraph.get_model().append_curves(youngGraphModel, 1)
        youngErrorGraph.get_model().remove_all_curves()
        youngErrorGraph.get_model().append_curves(youngErrorGraphModel, 1)
        gtk.main_iteration(False)
    #add_curve('Contact point', depth, cp)
    #add_curve('Contact point standard error', depth, cperr)


def on_selection_finished(selection):
    update_indentation_depth(selection.get_data()[0])

def update_indentation_depth(indentation_depth):
    youngErrorGraph.get_area().get_selection(gwy.GRAPH_STATUS_XLINES).set_data(1, [indentation_depth])
    youngGraph.get_area().get_selection(gwy.GRAPH_STATUS_XLINES).set_data(1, [indentation_depth])
    indentationDepthEntry.props.text = indentation_depth
    dataViewSelection = dataView.get_top_layer().ensure_selection()
    on_dataView_button_press(dataViewSelection)


threshold_factor = 5
if __name__ == "__main__":
    import jpkqidata
    import sys
    gwy.data = jpkqidata.load(sys.argv[1])
    run()
    gtk.main()
