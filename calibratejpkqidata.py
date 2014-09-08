import gwy

plugin_type = "VOLUME"
plugin_menu = "/Calibrate JPK quantitative imaging data"

def run():
    brick_id = gwy.gwy_app_data_browser_get_current(gwy.APP_BRICK_ID)
    brick   = gwy.data['/brick/{}'        .format(brick_id)]
    meta    = gwy.data['/brick/{}/meta'   .format(brick_id)]
    preview = gwy.data['/brick/{}/preview'.format(brick_id)]
    title   = gwy.data['/brick/{}/title'  .format(brick_id)]

    result = calibratejpkqidata(brick, meta, preview)

    for name, (brick, preview) in result.items():
        brick_id = gwy.gwy_app_data_browser_add_brick(brick, preview, gwy.data, True)
        gwy.data["/brick/{}/title".format(brick_id)] = "{} {}".format(title, name)

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

def calibratejpkqidata(brick, meta, preview, conversions=None):
    """
    Initialize the test data

    >>> meta = gwy.Container()
    >>> meta['distance.scaling.unit.unit'] = 'm'
    >>> meta['distance.base-calibration-slot'] = 'volts'
    >>> meta['distance.scaling.multiplier'] = 2
    >>> meta['distance.scaling.offset'] = 1
    >>> meta['distance.name'] = 'Distance'

    >>> brick = gwy.Brick(1,1,1,1,1,1,False)
    >>> brick.set_val(0,0,0,1)
    >>> brick.get_si_unit_w().set_from_string('V')

    >>> preview = gwy.DataField(1,1,1,1,False)
    >>> preview.set_val(0,0,2)

    Run the calibration for all conversions
    >>> result = calibratejpkqidata(brick, meta, preview)
    >>> brick, preview = result['Distance']

    The values get calibrated according to multiplier and offset
    >>> brick.get_val(0,0,0)
    4.0

    The unit gets set to the new value
    >>> brick.get_si_unit_w().get_string(0)
    'm'

    The preview gets also calibrated according to multiplier and offset
    >>> preview.get_val(0,0)
    6.0

    Run the calibration for one conversion
    >>> result = calibratejpkqidata(brick, meta, preview, ['distance'])
    >>> 'Distance' in result
    True
    """

    if not conversions:
        conversions = set()
        for key in meta.keys_by_name():
            conversions.add(key.split('.')[0])

    result = {}
    for conversion in conversions:
        result_brick = brick.duplicate()
        result_preview = preview.duplicate()

        try:
            unit = meta[conversion + '.scaling.unit.unit']
            result_brick.get_si_unit_w().set_from_string(unit)
            result_preview.get_si_unit_z().set_from_string(unit)
        except KeyError:
            pass

        multiplier, offset = get_coefficients(meta, conversion)

        result_brick.add(offset)
        result_preview.add(offset)

        result_brick.multiply(multiplier)
        result_preview.multiply(multiplier)

        name = meta[conversion + '.name']
        result[name] = (result_brick, result_preview)
    return result

if __name__ == "__main__":
    import doctest
    doctest.testmod()
