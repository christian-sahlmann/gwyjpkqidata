from six.moves import configparser
import io
import numpy
import PIL.Image
from six.moves import StringIO
import zipfile

plugin_type = "FILE"
plugin_desc = "JPK quantitative imaging data"

class Channel(numpy.ndarray):
    def get_coefficients(self, lcd_info, conversion):
        """
        When there are no coefficients, the data should not change when recalibrating
        >>> channel = Channel(1)
        >>> channel.shared_data = dict()
        >>> channel.get_coefficients(0, 'volts')
        (1.0, 0.0)

        When coefficients are specified, return them
        >>> channel.shared_data['lcd-info.0.conversion-set.conversion.distance.base-calibration-slot'] = 'volts'
        >>> channel.shared_data['lcd-info.0.conversion-set.conversion.distance.scaling.multiplier'] = 2
        >>> channel.shared_data['lcd-info.0.conversion-set.conversion.distance.scaling.offset'] = 3
        >>> channel.get_coefficients(0, 'distance')
        (2.0, 3.0)

        If the base calibration slot also has coefficients, calculate the resulting coefficients
        >>> channel.shared_data['lcd-info.0.conversion-set.conversion.force.base-calibration-slot'] = 'distance'
        >>> channel.shared_data['lcd-info.0.conversion-set.conversion.force.scaling.multiplier'] = 4
        >>> channel.shared_data['lcd-info.0.conversion-set.conversion.force.scaling.offset'] = 5
        >>> channel.get_coefficients(0, 'force')
        (8.0, 5.5)
        """
        prefix = 'lcd-info.{}.conversion-set.conversion.{}.'.format(lcd_info, conversion)
        try:
            base_calibration_slot = self.shared_data[prefix + 'base-calibration-slot']
            multiplier = float(self.shared_data[prefix + 'scaling.multiplier'])
            offset = float(self.shared_data[prefix + 'scaling.offset'])
            base_multiplier, base_offset = self.get_coefficients(lcd_info, base_calibration_slot)
            return base_multiplier * multiplier, base_offset + offset / base_multiplier
        except KeyError:
            return 1.0, 0.0

    def calibrate(self, conversion):
        multiplier, offset = self.get_coefficients(self.lcd_info, conversion)
        return (self + offset) * multiplier

class Segment:
    def channel(self, name):
        channel = numpy.empty((self.ilength, self.jlength, self.num_points)).view(Channel)
        channel.fill(float('nan'))

        channel.shared_data = self.shared_data
        channel.lcd_info = int(self.header['channel.{}.lcd-info.*'.format(name)])
        offset     = float(self.shared_data['lcd-info.{}.encoder.scaling.offset'.format(channel.lcd_info)])
        multiplier = float(self.shared_data['lcd-info.{}.encoder.scaling.multiplier'.format(channel.lcd_info)])

        for i, j in numpy.ndindex(self.ilength, self.jlength):
            index = j+(self.ilength-1-i)*self.jlength
            try:
                channel_file = self.zipfile.read('index/{}/segments/{}/channels/{}.dat'.format(index, self.number, name))
                channel_data = numpy.frombuffer(channel_file,
                                                numpy.dtype('>i'))
                length = len(channel_data)
                channel[i, j, :length] = channel_data*multiplier + offset
            except KeyError:
                pass

        return channel

class JpkQiDataException(Exception):
    pass

class JpkQiData:
    """
    >>> jpkqidata = JpkQiData(file_path)
    >>> channel = jpkqidata.segment('extend').channel('vDeflection')

    Check if the channel has proper content
    >>> channel[0, 0, 0]
    3.0

    If the channel data is too short to fill the channel, it gets set to NaN
    >>> channel[0, 0, 1]
    nan
    """
    segment_styles = dict()

    def __init__(self, filename):
        """
        >>> jpkqidata = JpkQiData(file_path)
        >>> segment_styles = jpkqidata.segment_styles
        >>> segment_styles['extend']
        0
        >>> segment_styles['retract']
        1
        """
        try:
            self.zipfile = zipfile.ZipFile(filename)

            self.header = self.read_properties('header.properties')
            self.ilength = int(self.header['quantitative-imaging-map.position-pattern.grid.ilength'])
            self.jlength = int(self.header['quantitative-imaging-map.position-pattern.grid.jlength'])
            self.ulength = float(self.header['quantitative-imaging-map.position-pattern.grid.ulength'])
            self.vlength = float(self.header['quantitative-imaging-map.position-pattern.grid.vlength'])
            self.grid_unit = self.header['quantitative-imaging-map.position-pattern.grid.unit.unit']

            self.shared_data = self.read_properties('shared-data/header.properties')
            segment_count = int(self.shared_data['force-segment-header-infos.count'])
            for segment_number in range(segment_count):
                segment_style = self.shared_data['force-segment-header-info.{}.settings.segment-settings.style'.format(segment_number)]
                if segment_style not in self.segment_styles:
                    self.segment_styles[segment_style] = segment_number
        except (zipfile.BadZipfile, KeyError):
            raise JpkQiDataException

    def segment(self, segment_style):
        segment = Segment()
        segment.zipfile = self.zipfile
        segment.ilength = self.ilength
        segment.jlength = self.jlength
        segment.num_points = int(self.header['quantitative-imaging-map.settings.force-settings.{}.num-points'.format(segment_style)])
        segment.duration = float(self.header['quantitative-imaging-map.settings.force-settings.{}.duration'.format(segment_style)])
        segment.number = self.segment_styles[segment_style]
        segment.header = self.read_properties('index/0/segments/{}/segment-header.properties'.format(segment.number))
        segment.shared_data = self.shared_data
        return segment

    def read_properties(self, path):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.readfp(StringIO('[DEFAULT]\n'+self.zipfile.read(path).decode()))
        return config.defaults()


def detect_by_name(filename):
    """
    When we have a QI file, we are 100% sure
    >>> detect_by_name("test.jpk-qi-data")
    100
    
    A text file is not a QI file
    >>> detect_by_name("test.txt")
    0
    """
    if filename.endswith(".jpk-qi-data"):
        return 100
    else:
        return 0

def detect_by_content(filename, head, tail, filesize):
    """
    Our test file should be 100% a QI file
    >>> detect_by_content(file_path, None, None, None)
    100
    
    A nonexisting file or text file is not a QI file
    >>> detect_by_content("test.txt", None, None, None)
    0
    
    An regular zip file is not a QI file
    >>> import os, tempfile
    >>> handle, file_path = tempfile.mkstemp()
    >>> os.close(handle)
    >>> f = zipfile.ZipFile(file_path, 'w')
    >>> f.close()
    >>> detect_by_content(file_path, None, None, None)
    0
    """
    try:
        JpkQiData(filename)
        return 100
    except:
        return 0

def load(filename, mode=None):
    """
    >>> container = load(file_path)
    
    Check if the channel has proper content
    >>> container['/0/data'].get_val(0,0)
    0.0

    Check if the brick has proper units and content
    >>> brick = container['/brick/0']
    >>> import gwy
    >>> brick.get_si_unit_x().get_string(gwy.SI_UNIT_FORMAT_PLAIN)
    'm'
    >>> brick.get_si_unit_y().get_string(gwy.SI_UNIT_FORMAT_PLAIN)
    'm'
    >>> brick.get_si_unit_z().get_string(gwy.SI_UNIT_FORMAT_PLAIN)
    's'
    >>> brick.get_si_unit_w().get_string(gwy.SI_UNIT_FORMAT_PLAIN)
    'V'
    >>> brick.get_val(0,0,0)
    3.0
    
    If the channel data is too short to fill the brick, it gets set to NaN
    >>> brick.get_val(0,0,1)
    nan
    
    Check if the preview has proper content
    >>> preview = container['/brick/0/preview']
    >>> preview.get_val(0,0)
    3.0
    
    The title should be set correctly
    >>> container['/brick/0/title']
    'extend vDeflection'
    
    The metadata should be initialized
    >>> meta = container['/brick/0/meta']
    >>> meta['distance.name']
    'Distance'
    >>> container['/brick/1/meta']['force.name']
    'Force'
    >>> container['/brick/2/meta']['distance.name']
    'Distance'
    """
    import gwy, site
    site.addsitedir(gwy.gwy_find_self_dir('data')+'/pygwy')
    import gwyutils
    main_window = gwy.gwy_app_main_window_get()
    if main_window:
        gwy.gwy_app_wait_start(main_window, plugin_desc)
    jpkqidata = JpkQiData(filename)
    container = gwy.Container()
    
    data_image = PIL.Image.open(io.BytesIO(jpkqidata.zipfile.read('data-image.jpk-qi-image')))
    data_image.load()
    try:
        while True:
            index = data_image.tell()
            field = gwy.DataField(data_image.size[0], data_image.size[1], data_image.size[0], data_image.size[1], False)
            array = gwyutils.data_field_data_as_array(field)
            array[:] = numpy.array(data_image.getdata()).reshape(data_image.size)
            container['/{}/data'.format(index)] = field
            data_image.seek(index+1)
            data_image.mode = 'I'
    except EOFError:
        pass
    
    for segment_progress, (segment_style, segmentnumber) in enumerate(jpkqidata.segment_styles.iteritems()):
        
        segment_header = jpkqidata.read_properties('index/0/segments/{}/segment-header.properties'.format(segmentnumber))
        channels = segment_header['channels.list'].split(' ')
        for channelname in channels:
            lcd_info = int(segment_header['channel.{}.lcd-info.*'.format(channelname)])
            
            segment = jpkqidata.segment(segment_style)
            brick_data = segment.channel(channelname)
            ilength, jlength, num_points = brick_data.shape
            brick = gwy.Brick(ilength, jlength, num_points, jpkqidata.ulength, jpkqidata.vlength, segment.duration, False)
            gwyutils.brick_set_data(brick, brick_data)
            
            brick.get_si_unit_x().set_from_string(jpkqidata.grid_unit)
            brick.get_si_unit_y().set_from_string(jpkqidata.grid_unit)
            brick.get_si_unit_z().set_from_string('s')
            brick.get_si_unit_w().set_from_string(jpkqidata.shared_data['lcd-info.{}.unit.unit'.format(lcd_info)])
            
            bricknumber = lcd_info + len(channels)*segmentnumber
            container["/brick/{}".format(bricknumber)] = brick
            preview = gwy.DataField(ilength, jlength, ilength, jlength, False)
            brick.min_plane(preview, 0, 0, 0, ilength, jlength, -1, True)
            container["/brick/{}/preview".format(bricknumber)] = preview
            container["/brick/{}/title".format(bricknumber)] = "{} {}".format(segment_style, channelname)
        
            meta = gwy.Container()
            for key in jpkqidata.shared_data:
                prefix = 'lcd-info.{}.conversion-set.conversion.'.format(lcd_info)
                if key.startswith(prefix):
                    meta.set_string_by_name(key[len(prefix):], jpkqidata.shared_data[key])
            container["/brick/{}/meta".format(bricknumber)] = meta

            if main_window:
                gwy.gwy_app_wait_set_fraction(1.0 * (segment_progress*len(channels) + lcd_info) / len(jpkqidata.segment_styles) / len(channels))

    if main_window:
        gwy.gwy_app_wait_finish()
    return container

if __name__ == "__main__":
    import doctest
    import os
    import tempfile
    import textwrap
    
    # create test file
    handle, file_path = tempfile.mkstemp()
    os.close(handle)
    f = zipfile.ZipFile(file_path, 'w')
    f.writestr('header.properties', textwrap.dedent('''
        type=quantitative-imaging-map
        quantitative-imaging-map.settings.force-settings.extend.duration=0
        quantitative-imaging-map.settings.force-settings.extend.num-points=2
        quantitative-imaging-map.settings.force-settings.retract.duration=0
        quantitative-imaging-map.settings.force-settings.retract.num-points=2
        quantitative-imaging-map.position-pattern.grid.ulength=1
        quantitative-imaging-map.position-pattern.grid.vlength=1
        quantitative-imaging-map.position-pattern.grid.unit.unit=m
        quantitative-imaging-map.position-pattern.grid.ilength=1
        quantitative-imaging-map.position-pattern.grid.jlength=1
        '''))
    f.writestr('shared-data/header.properties', textwrap.dedent('''
        force-segment-header-infos.count=3
        force-segment-header-info.0.settings.segment-settings.style=extend
        force-segment-header-info.1.settings.segment-settings.style=retract
        force-segment-header-info.2.settings.segment-settings.style=extend
        lcd-info.0.unit.unit=V
        lcd-info.0.encoder.scaling.offset=1
        lcd-info.0.encoder.scaling.multiplier=2
        lcd-info.0.conversion-set.conversion.distance.name=Distance
        lcd-info.1.unit.unit=V
        lcd-info.1.encoder.scaling.offset=1
        lcd-info.1.encoder.scaling.multiplier=2
        lcd-info.1.conversion-set.conversion.force.name=Force
        '''))
    f.writestr('index/0/header.properties', 'type=quantitative-imaging-series')
    f.writestr('index/0/segments/0/segment-header.properties', textwrap.dedent('''
        channels.list=vDeflection height
        channel.vDeflection.lcd-info.*=0
        channel.height.lcd-info.*=1
        '''))
    f.writestr('index/0/segments/1/segment-header.properties', textwrap.dedent('''
        channels.list=vDeflection height
        channel.vDeflection.lcd-info.*=0
        channel.height.lcd-info.*=1
        '''))
    f.writestr('index/0/segments/2/segment-header.properties', textwrap.dedent('''
        channels.list=vDeflection height
        channel.vDeflection.lcd-info.*=0
        channel.height.lcd-info.*=1
        '''))
    f.writestr('index/0/segments/0/channels/vDeflection.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    f.writestr('index/0/segments/0/channels/height.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    f.writestr('index/0/segments/1/channels/vDeflection.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    f.writestr('index/0/segments/1/channels/height.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    f.writestr('index/0/segments/2/channels/vDeflection.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    f.writestr('index/0/segments/2/channels/height.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    data_image = io.BytesIO()
    PIL.Image.new('1', (1,1)).save(data_image, 'TIFF')
    f.writestr('data-image.jpk-qi-image', data_image.getvalue())
    f.close()
    
    # run tests
    doctest.testmod()
    
    # remove testfile
    os.remove(file_path)
