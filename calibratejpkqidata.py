import gwy

plugin_type = "VOLUME"
plugin_menu = "/Calibrate JPK quantitative imaging data"

def run():
    brick_id = gwy.gwy_app_data_browser_get_current(gwy.APP_BRICK_ID)
    result = calibratejpkqidata(brick_id)
    for brick, preview, title in result:
        id = gwy.gwy_app_data_browser_add_brick(brick, preview, gwy.data, True)
        gwy.data["/brick/{}/title".format(id)] = title

def get_coefficients(meta, calibration_slot):
    """
    When there are no coefficients, the data should not change when recalibrating
    >>> meta = gwy.Container()
    >>> get_coefficients(meta, 'volts')
    (1.0, 0.0)

    When coefficients are specified, return them
    >>> meta['distance.base-calibration-slot'] = 'volts'
    >>> meta['distance.scaling.multiplier'] = 2
    >>> meta['distance.scaling.offset'] = 3
    >>> get_coefficients(meta, 'distance')
    (2.0, 3.0)

    If the base calibration slot also has coefficients, calculate the resulting coefficients
    >>> meta['force.base-calibration-slot'] = 'distance'
    >>> meta['force.scaling.multiplier'] = 4
    >>> meta['force.scaling.offset'] = 5
    >>> get_coefficients(meta, 'force')
    (8.0, 5.5)
    """
    try:
        base_calibration_slot = meta[calibration_slot + '.base-calibration-slot']
        multiplier = float(meta[calibration_slot + '.scaling.multiplier'])
        offset = float(meta[calibration_slot + '.scaling.offset'])
        base_multiplier, base_offset = get_coefficients(meta, base_calibration_slot)
        return base_multiplier * multiplier, base_offset + offset / base_multiplier
    except KeyError:
        return 1.0, 0.0

def calibratejpkqidata(brick_id):
    """
    Initialize the test data
    >>> gwy.data = gwy.Container()

    >>> meta = gwy.Container()
    >>> meta['distance.scaling.unit.unit'] = 'm'
    >>> meta['distance.base-calibration-slot'] = 'volts'
    >>> meta['distance.scaling.multiplier'] = 2
    >>> meta['distance.scaling.offset'] = 1
    >>> meta['distance.name'] = 'Distance'
    >>> gwy.data["/brick/0/meta"] = meta

    >>> brick = gwy.Brick(1,1,1,1,1,1,False)
    >>> brick.set_val(0,0,0,1)
    >>> brick.get_si_unit_w().set_from_string('V')
    >>> gwy.data["/brick/0"] = brick

    >>> preview = gwy.DataField(1,1,1,1,False)
    >>> preview.set_val(0,0,2)
    >>> gwy.data["/brick/0/preview"] = preview

    >>> gwy.data["/brick/0/title"] = "extend vDeflection"

    Run the calibration
    >>> result = calibratejpkqidata(0)
    >>> brick, preview, title = result[0]

    The values get calibrated according to multiplier and offset
    >>> brick.get_val(0,0,0)
    4.0

    The unit gets set to the new value
    >>> brick.get_si_unit_w().get_string(0)
    'm'

    The preview gets also calibrated according to multiplier and offset
    >>> preview.get_val(0,0)
    6.0

    The title gets appended the calibration name
    >>> title
    'extend vDeflection Distance'
    """
    brick_path = "/brick/{}".format(brick_id)
    meta = gwy.data[brick_path + "/meta"]

    conversion_set = set()
    for key in meta.keys_by_name():
        conversion_set.add(key.split('.')[0])

    result = []
    for conversion in conversion_set:
        brick = gwy.data[brick_path].duplicate()
        preview = gwy.data[brick_path + "/preview"].duplicate()
        title = "{} {}".format(gwy.data[brick_path + "/title"], meta[conversion + '.name'])

        try:
            unit = meta[conversion + '.scaling.unit.unit']
            brick.get_si_unit_w().set_from_string(unit)
            preview.get_si_unit_z().set_from_string(unit)
        except KeyError:
            pass

        multiplier, offset = get_coefficients(meta, conversion)

        brick.add(offset)
        preview.add(offset)

        brick.multiply(multiplier)
        preview.multiply(multiplier)

        result.append((brick, preview, title))
    return result

if __name__ == "__main__":
    import doctest
    doctest.testmod()
