import copy_reg
import gwy
import gwyutils
import pickle

plugin_type = "FILE"
plugin_desc = "Pickle"

def detect_by_name(filename):
    if filename.endswith(".pickle"):
        return 100
    else:
        return 0

def detect_by_content(filename, head, tail, filesize):
    return detect_by_name(filename)

def container_reduce(container):
    values = dict()
    for key in container.keys_by_name():
        value = container[key]
        if 'GwySelectionPoint' not in str(value):
            values[key] = value
    return gwy.Container, (), None, None, values.iteritems()
copy_reg.pickle(gwy.Container, container_reduce)

def datafield_create(data, xres, yres, si_unit_xy, si_unit_z):
    shape = data.shape
    datafield = gwy.DataField(shape[0], shape[1], xres, yres, False)
    gwyutils.data_field_set_data(datafield, data)
    datafield.get_si_unit_xy().set_from_string(si_unit_xy)
    datafield.get_si_unit_z().set_from_string(si_unit_z)
    return datafield

def datafield_reduce(datafield):
    return datafield_create, (gwyutils.data_field_data_as_array(datafield),
                              datafield.get_xres(),
                              datafield.get_yres(),
                              datafield.get_si_unit_xy().get_string(gwy.SI_UNIT_FORMAT_PLAIN),
                              datafield.get_si_unit_z().get_string(gwy.SI_UNIT_FORMAT_PLAIN),
                             )
copy_reg.pickle(gwy.DataField, datafield_reduce)

def brick_create(data, xres, yres, zres, si_unit_x, si_unit_y, si_unit_z, si_unit_w):
    shape = data.shape
    brick = gwy.Brick(shape[0], shape[1], shape[2], xres, yres, zres, False)
    gwyutils.brick_set_data(brick, data)
    brick.get_si_unit_x().set_from_string(si_unit_x)
    brick.get_si_unit_y().set_from_string(si_unit_y)
    brick.get_si_unit_z().set_from_string(si_unit_z)
    brick.get_si_unit_w().set_from_string(si_unit_w)
    return brick

def brick_reduce(brick):
    return brick_create, (gwyutils.brick_data_as_array(brick),
                          brick.get_xres(),
                          brick.get_yres(),
                          brick.get_zres(),
                          brick.get_si_unit_x().get_string(gwy.SI_UNIT_FORMAT_PLAIN),
                          brick.get_si_unit_y().get_string(gwy.SI_UNIT_FORMAT_PLAIN),
                          brick.get_si_unit_z().get_string(gwy.SI_UNIT_FORMAT_PLAIN),
                          brick.get_si_unit_w().get_string(gwy.SI_UNIT_FORMAT_PLAIN),
                         )
copy_reg.pickle(gwy.Brick, brick_reduce)

def load(filename, mode=None):
    with open(filename, 'rb') as f:
        data = pickle.load(f)
    return data

def save(data, filename, mode=None):
    with open(filename, 'wb') as f:
        pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)
    return True
