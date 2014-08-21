import ConfigParser
import gwy
import gwyutils
import io
import numpy
import PIL.Image
import StringIO
import zipfile

plugin_type = "FILE"
plugin_desc = "JPK quantitative imaging data"

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
        zip_file = zipfile.ZipFile(filename)
        zip_file.open('header.properties')
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
    """
    main_window = gwy.gwy_app_main_window_get()
    if main_window:
        gwy.gwy_app_wait_start(main_window, plugin_desc)
    zip_file = zipfile.ZipFile(filename)
    container = gwy.Container()
    
    data_image = PIL.Image.open(io.BytesIO(zip_file.read('data-image.jpk-qi-image')))
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

    def read_properties(path):
        config = ConfigParser.ConfigParser()
        config.optionxform = str
        config.readfp(StringIO.StringIO('[DEFAULT]\n'+zip_file.read(path).decode()))
        return config.defaults()
        
    header = read_properties('header.properties')
    shared_data = read_properties('shared-data/header.properties')
    
    ilength =   int(header['quantitative-imaging-map.position-pattern.grid.ilength'])
    jlength =   int(header['quantitative-imaging-map.position-pattern.grid.jlength'])
    ulength = float(header['quantitative-imaging-map.position-pattern.grid.ulength'])
    vlength = float(header['quantitative-imaging-map.position-pattern.grid.vlength'])
    gridunit = header['quantitative-imaging-map.position-pattern.grid.unit.unit']
    
    segmentcount = int(shared_data['force-segment-header-infos.count'])
    for segmentnumber in range(segmentcount):
        segment_header = read_properties('index/0/segments/{}/segment-header.properties'.format(segmentnumber))
        segment_style = shared_data['force-segment-header-info.{}.settings.segment-settings.style'.format(segmentnumber)]
        duration = float(header['quantitative-imaging-map.settings.force-settings.{}.duration'.format(segment_style)])
        num_points = int(header['quantitative-imaging-map.settings.force-settings.{}.num-points'.format(segment_style)])
        
        channels = segment_header['channels.list'].split(' ')
        for channelname in channels:
            lcd_info = int(segment_header['channel.{}.lcd-info.*'.format(channelname)])
            offset     = float(shared_data['lcd-info.{}.encoder.scaling.offset'.format(lcd_info)])
            multiplier = float(shared_data['lcd-info.{}.encoder.scaling.multiplier'.format(lcd_info)])
            
            brick = gwy.Brick(ilength, jlength, num_points, ulength, vlength, duration, False)
            brickarray = gwyutils.brick_data_as_array(brick)
            
            brick.get_si_unit_x().set_from_string(gridunit)
            brick.get_si_unit_y().set_from_string(gridunit)
            brick.get_si_unit_z().set_from_string('s')
            brick.get_si_unit_w().set_from_string(shared_data['lcd-info.{}.unit.unit'.format(lcd_info)])
            
            for i in range(ilength):
                if main_window:
                    gwy.gwy_app_wait_set_fraction(1.0*((segmentnumber*len(channels)+lcd_info)*ilength+i)/segmentcount/len(channels)/ilength)
                for j in range(jlength):
                    index = i+(jlength-1-j)*ilength
                    channel = numpy.frombuffer(zip_file.read('index/{}/segments/{}/channels/{}.dat'.format(index, segmentnumber, channelname)),
                                               numpy.dtype('>i'))
                    channel = channel*multiplier + offset
                    length = len(channel)
                    channel.resize(num_points)
                    channel[length:] = float('nan')
                    brickarray[i][j] = channel
                        
            bricknumber = lcd_info + len(channels)*segmentnumber
            container["/brick/{}".format(bricknumber)] = brick
            preview = gwy.DataField(ilength, jlength, ilength, jlength, False)
            brick.min_plane(preview, 0, 0, 0, ilength, jlength, -1, True)
            container["/brick/{}/preview".format(bricknumber)] = preview
            container["/brick/{}/title".format(bricknumber)] = "{} {}".format(segment_style, channelname)
        
            meta = gwy.Container()
            for key in shared_data:
                prefix = 'lcd-info.{}.conversion-set.conversion.'.format(lcd_info)
                if key.startswith(prefix):
                    meta.set_string_by_name(key[len(prefix):], shared_data[key])
            container["/brick/{}/meta".format(lcd_info)] = meta

    if main_window:
        gwy.gwy_app_wait_finish()
    return container

if __name__ == "__main__":
    import doctest
    import io
    import os
    import PIL.Image
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
        quantitative-imaging-map.position-pattern.grid.ulength=1
        quantitative-imaging-map.position-pattern.grid.vlength=1
        quantitative-imaging-map.position-pattern.grid.unit.unit=m
        quantitative-imaging-map.position-pattern.grid.ilength=1
        quantitative-imaging-map.position-pattern.grid.jlength=1
        '''))
    f.writestr('shared-data/header.properties', textwrap.dedent('''
        force-segment-header-infos.count=1
        force-segment-header-info.0.settings.segment-settings.style=extend
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
    f.writestr('index/0/segments/0/channels/vDeflection.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    f.writestr('index/0/segments/0/channels/height.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    data_image = io.BytesIO()
    PIL.Image.new('1', (1,1)).save(data_image, 'TIFF')
    f.writestr('data-image.jpk-qi-image', data_image.getvalue())
    f.close()
    
    gwy.gwy_app_wait_start        = lambda x,y: None
    gwy.gwy_app_wait_set_fraction = lambda x: None
    gwy.gwy_app_wait_finish       = lambda: None
    
    # run tests
    doctest.testmod()
    
    # remove testfile
    os.remove(file_path)
