import ConfigParser
import gwy
import numpy
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
    
    Check if the brick has proper units and content
    >>> brick = container.get_object_by_name('/brick/0')
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
    
    Check if the preview has proper content
    >>> preview = container.get_object_by_name('/brick/0/preview')
    >>> preview.get_val(0,0)
    3.0
    
    The title should be set correctly
    >>> container.get_string_by_name('/brick/0/title')
    'extend vDeflection'
    
    The metadata should be initialized
    >>> meta = container.get_object_by_name('/brick/0/meta')
    >>> meta.get_string_by_name('distance.name')
    'Distance'
    """
    zip_file = zipfile.ZipFile(filename)
    container = gwy.Container()
    
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

    gridunit = gwy.SIUnit()
    gridunit.set_from_string(header['quantitative-imaging-map.position-pattern.grid.unit.unit'])
    
    timeunit = gwy.SIUnit()
    timeunit.set_from_string('s')
    
    for segmentnumber in range(int(shared_data['force-segment-header-infos.count'])):
        segment_header = read_properties('index/0/segments/{}/segment-header.properties'.format(segmentnumber))
        segment_style = shared_data['force-segment-header-info.{}.settings.segment-settings.style'.format(segmentnumber)]
        duration = float(header['quantitative-imaging-map.settings.force-settings.{}.duration'.format(segment_style)])
        num_points = int(header['quantitative-imaging-map.settings.force-settings.{}.num-points'.format(segment_style)])
        
        channels = segment_header['channels.list'].split(' ')
        for channelname in channels:
            lcd_info = int(segment_header['channel.{}.lcd-info.*'.format(channelname)])
            offset     = float(shared_data['lcd-info.{}.encoder.scaling.offset'.format(lcd_info)])
            multiplier = float(shared_data['lcd-info.{}.encoder.scaling.multiplier'.format(lcd_info)])
            
            brick = gwy.Brick(ilength, jlength, num_points, ulength, vlength, duration, True)
            
            brick.set_si_unit_x(gridunit)
            brick.set_si_unit_y(gridunit)
            brick.set_si_unit_z(timeunit)
            channelunit = gwy.SIUnit()
            channelunit.set_from_string(shared_data['lcd-info.{}.unit.unit'.format(lcd_info)])
            brick.set_si_unit_w(channelunit)
            
            for i in range(ilength):
                for j in range(jlength):
                    index = i+(jlength-1-j)*ilength
                    channel = numpy.frombuffer(zip_file.read('index/{}/segments/{}/channels/{}.dat'.format(index, segmentnumber, channelname)),
                                               numpy.dtype('>i'))
                    channel = channel*multiplier + offset
                    for k,value in enumerate(channel):
                        brick.set_val(i, j, k, value)
                        
            bricknumber = lcd_info + len(channels)*segmentnumber
            container.set_object_by_name("/brick/{}".format(bricknumber), brick)
            preview = gwy.DataField(ilength, jlength, ilength, jlength, False)
            brick.min_plane(preview, 0, 0, 0, ilength, jlength, -1, True)
            container.set_object_by_name("/brick/{}/preview".format(bricknumber), preview)
            container.set_string_by_name("/brick/{}/title".format(bricknumber), "{} {}".format(segment_style, channelname))
        
        meta = gwy.Container()
        for key in shared_data:
            prefix = 'lcd-info.{}.conversion-set.conversion.'.format(lcd_info)
            if key.startswith(prefix):
                meta.set_string_by_name(key[len(prefix):], shared_data[key])
        container.set_object_by_name("/brick/{}/meta".format(lcd_info), meta)
        
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
        quantitative-imaging-map.settings.force-settings.extend.num-points=1
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
        '''))
    f.writestr('index/0/header.properties', 'type=quantitative-imaging-series')
    f.writestr('index/0/segments/0/segment-header.properties', textwrap.dedent('''
        channels.list=vDeflection
        channel.vDeflection.lcd-info.*=0
        '''))
    f.writestr('index/0/segments/0/channels/vDeflection.dat', numpy.array([1], numpy.dtype('>i')).tostring())
    data_image = io.BytesIO()
    PIL.Image.new('1', (1,1)).save(data_image, 'TIFF')
    f.writestr('data-image.jpk-qi-image', data_image.getvalue())
    f.close()
    
    # run tests
    doctest.testmod()
    
    # remove testfile
    os.remove(file_path)
