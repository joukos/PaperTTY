#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Jouko Strömmer, 2018
# Copyright and related rights waived via CC0
# https://creativecommons.org/publicdomain/zero/1.0/legalcode

# As you would expect, use this at your own risk! This code was created
# so you (yes, YOU!) can make it better.
#
# Requires Python 3

# display drivers - note: they are GPL licensed, unlike this file
import drivers.drivers_base as drivers_base
import drivers.drivers_partial as drivers_partial
import drivers.drivers_full as drivers_full
import drivers.drivers_color as drivers_color
import drivers.drivers_colordraw as drivers_colordraw
import drivers.driver_it8951 as driver_it8951
import drivers.drivers_4in2 as driver_4in2

# for ioctl
import fcntl
# for validating type of and access to device files
import os
# for gracefully handling signals (systemd service)
import signal
# for unpacking virtual console data
import struct
# for stdin and exit
import sys
import select
# for setting TTY size
import termios
# for sleeping
import time
# for command line usage
import click
# for drawing
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps
# for tidy driver list
from collections import OrderedDict
# for VNC
from vncdotool import api
# for reading stdin data for use with Pillow
from io import BytesIO


class PaperTTY:
    """The main class - handles various settings and showing text on the display"""
    defaultfont = "tom-thumb.pil"
    defaultsize = 8
    driver = None
    partial = None
    initialized = None
    font = None
    fontsize = None
    font_height = None
    font_width = None
    white = None
    black = None
    encoding = None
    spacing = 0
    cursor = None
    rows = None
    cols = None
    is_truetype = None
    fontfile = None

    def __init__(self, driver, font=defaultfont, fontsize=defaultsize, partial=None, encoding='utf-8', spacing=0, cursor=None):
        """Create a PaperTTY with the chosen driver and settings"""
        self.driver = get_drivers()[driver]['class']()
        self.spacing = spacing
        self.fontsize = fontsize
        self.font = self.load_font(font) if font else None
        self.partial = partial
        self.white = self.driver.white
        self.black = self.driver.black
        self.encoding = encoding
        self.cursor = cursor

    def ready(self):
        """Check that the driver is loaded and initialized"""
        return self.driver and self.initialized

    @staticmethod
    def error(msg, code=1):
        """Print error and exit"""
        print(msg)
        sys.exit(code)

    def set_tty_size(self, tty, rows, cols):
        """Set a TTY (/dev/tty*) to a certain size. Must be a real TTY that support ioctls."""
        self.rows = rows
        self.cols = cols
        with open(tty, 'w') as tty:
            size = struct.pack("HHHH", int(rows), int(cols), 0, 0)
            try:
                fcntl.ioctl(tty.fileno(), termios.TIOCSWINSZ, size)
            except OSError:
                print("TTY refused to resize (rows={}, cols={}), continuing anyway.".format(rows, cols))
                print("Try setting a sane size manually.")

    @staticmethod
    def band(bb):
        """Stretch a bounding box's X coordinates to be divisible by 8,
           otherwise weird artifacts occur as some bits are skipped."""
        return (int(bb[0] / 8) * 8, bb[1], int((bb[2] + 7) / 8) * 8, bb[3]) if bb else None

    @staticmethod
    def split(s, n):
        """Split a sequence into parts of size n"""
        return [s[begin:begin + n] for begin in range(0, len(s), n)]

    @staticmethod
    def fold(text, width=None, filter_fn=None):
        """Format a string to a specified width and/or filter it"""
        buff = text
        if width:
            buff = ''.join([r + '\n' for r in PaperTTY.split(buff, int(width))]).rstrip()
        if filter_fn:
            buff = [c for c in buff if filter_fn(c)]
        return buff

    @staticmethod
    def img_diff(img1, img2):
        """Return the bounding box of differences between two images"""
        return ImageChops.difference(img1, img2).getbbox()

    @staticmethod
    def ttydev(vcsa):
        """Return associated tty for vcsa device, ie. /dev/vcsa1 -> /dev/tty1"""
        return vcsa.replace("vcsa", "tty")
    
    def vcsudev(self, vcsa):
        """Return character width and associated vcs(u) for vcsa device,
           ie. for /dev/vcsa1, retunr (4, "/dev/vcsu1") if vcsu is available, or
           (1, "/dev/vcs1") if not"""
        dev = vcsa.replace("vcsa", "vcsu")
        if os.path.exists(dev):
            if isinstance(self.font, ImageFont.FreeTypeFont):
                return 4, dev
            else:
                print("Font {} doesn't support Unicode. Falling back to 8-bit encoding.".format(self.font.file))
                return 1, vcsa.replace("vcsa", "vcs")
        else:
            print("System does not have /dev/vcsu. Falling back to 8-bit encoding.")
            return 1, vcsa.replace("vcsa", "vcs")

    @staticmethod
    def valid_vcsa(vcsa):
        """Check that the vcsa device and associated terminal seem sane"""
        vcsa_kernel_major = 7
        tty_kernel_major = 4
        vcsa_range = range(128, 191)
        tty_range = range(1, 63)

        tty = PaperTTY.ttydev(vcsa)
        vs = os.stat(vcsa)
        ts = os.stat(tty)

        vcsa_major, vcsa_minor = os.major(vs.st_rdev), os.minor(vs.st_rdev)
        tty_major, tty_minor = os.major(ts.st_rdev), os.minor(ts.st_rdev)
        if not (vcsa_major == vcsa_kernel_major and vcsa_minor in vcsa_range):
            print("Not a valid vcsa device node: {} ({}/{})".format(vcsa, vcsa_major, vcsa_minor))
            return False
        read_vcsa = os.access(vcsa, os.R_OK)
        write_tty = os.access(tty, os.W_OK)
        if not read_vcsa:
            print("No read access to {} - maybe run with sudo?".format(vcsa))
            return False
        if not (tty_major == tty_kernel_major and tty_minor in tty_range):
            print("Not a valid TTY device node: {}".format(vcsa))
        if not write_tty:
            print("No write access to {} so cannot set terminal size, maybe run with sudo?".format(tty))
        return True

    def load_font(self, path, keep_if_not_found=False):
        """Load the PIL or TrueType font"""
        font = None
        # If no path is given, reuse existing font path. Good for resizing.
        path = path or self.fontfile
        if os.path.isfile(path):
            try:
                # first check if the font looks like a PILfont
                with open(path, 'rb') as f:
                    if f.readline() == b"PILfont\n":
                        self.is_truetype = False
                        print('Loading PIL font {}. Font size is ignored.'.format(path))
                        font = ImageFont.load(path)
                        # otherwise assume it's a TrueType font
                    else:
                        self.is_truetype = True
                        font = ImageFont.truetype(path, self.fontsize)
                    self.fontfile = path
            except IOError:
                self.error("Invalid font: '{}'".format(path))
        elif keep_if_not_found:
            print("The font '{}' could not be found, keep using old font.".format(path))
            font = self.font
        else:
            print("The font '{}' could not be found, using fallback font instead.".format(path))
            font = ImageFont.load_default()

        if font:
            # get physical dimensions of font. Take the average width of
            # 1000 M's because oblique fonts are complicated.
            self.font_width = font.getsize('M' * 1000)[0] // 1000
            if 'getmetrics' in dir(font):
                metrics_ascent, metrics_descent = font.getmetrics()
                self.spacing = int(self.spacing) if self.spacing != 'auto' else (metrics_descent - 2)
                print('Setting spacing to {}.'.format(self.spacing))
                # despite what the PIL docs say, ascent appears to be the
                # height of the font, while descent is not, in fact, negative.
                # Couuld use testing with more fonts.
                self.font_height = metrics_ascent + self.spacing
            else:
                # No autospacing for pil fonts, but they usually don't need it.
                self.spacing = int(self.spacing) if self.spacing != 'auto' else 0
                # pil fonts don't seem to have metrics, but all
                # characters seem to have the same height
                self.font_height = font.getsize('a')[1] + self.spacing

        return font

    def recalculate_font(self):
        """Load the PIL or TrueType font"""
        # get physical dimensions of font. Take the average width of
        # 1000 M's because oblique fonts a complicated.
        self.font_width = self.font.getsize('M' * 1000)[0] // 1000
        if 'getmetrics' in dir(self.font):
            metrics_ascent, metrics_descent = self.font.getmetrics()
            self.spacing = int(self.spacing) if self.spacing != 'auto' else (metrics_descent - 2)
            print('Setting spacing to {}.'.format(self.spacing))
            # despite what the PIL docs say, ascent appears to be the
            # height of the font, while descent is not, in fact, negative.
            # Couuld use testing with more fonts.
            self.font_height = metrics_ascent + self.spacing
        else:
            # No autospacing for pil fonts, but they usually don't need it.
            self.spacing = int(self.spacing) if self.spacing != 'auto' else 0
            # pil fonts don't seem to have metrics, but all
            # characters seem to have the same height
            self.font_height = self.font.getsize('a')[1] + self.spacing

    def init_display(self):
        """Initialize the display - call the driver's init method"""
        self.driver.init(partial=self.partial)
        self.initialized = True

    def fit(self, portrait=False):
        """Return the maximum columns and rows we can display with this font"""
        width = self.font.getsize('M')[0]
        height = self.font_height
        # hacky, subtract just a bit to avoid going over the border with small fonts
        pw = self.driver.width - 3
        ph = self.driver.height
        return int((pw if portrait else ph) / width), int((ph if portrait else pw) / height)

    def draw_line_cursor(self, cursor, draw):
        cur_x, cur_y = cursor[0], cursor[1]
        width = self.font_width
        # desired cursor width
        cur_width = width - 1
        # get font height
        height = self.font_height
        # starting X is the font width times current column
        start_x = cur_x * width
        offset = 0
        if self.cursor != 'default': # only default and a number are valid in this context
            offset = int(self.cursor)
        # add 1 because rows start at 0 and we want the cursor at the bottom
        start_y = (cur_y + 1) * height - 1 - offset
        # draw the cursor line
        draw.line((start_x, start_y, start_x + cur_width, start_y), fill=self.black)

    def draw_block_cursor(self, cursor, image):
        cur_x, cur_y = cursor[0], cursor[1]
        width = self.font_width
        # get font height
        height = self.font_height
        upper_left = (cur_x * width, cur_y * height)
        lower_right = ((cur_x + 1) * width, (cur_y + 1) * height)
        mask = Image.new('1', (image.width, image.height), self.black)
        draw = ImageDraw.Draw(mask)
        draw.rectangle([upper_left, lower_right], fill=self.white)
        return ImageChops.logical_xor(image, mask)
    
    def showvnc(self, host, display, password=None, rotate=None, invert=False, sleep=1, full_interval=100):
        with api.connect(':'.join([host, display]), password=password) as client:
            previous_vnc_image = None
            diff_bbox = None
            # number of updates; when it's 0, do a full refresh
            updates = 0
            client.timeout = 30
            while True:
                try:
                    client.refreshScreen()
                except TimeoutError:
                    print("Timeout to server {}:{}".format(host, display))
                    client.disconnect()
                    sys.exit(1)
                new_vnc_image = client.screen
                # apply rotation if any
                if rotate:
                    new_vnc_image = new_vnc_image.rotate(rotate, expand=True)
                # apply invert
                if invert:
                    new_vnc_image = ImageOps.invert(new_vnc_image)
                # rescale image if needed
                if new_vnc_image.size != (self.driver.width, self.driver.height):
                    new_vnc_image = new_vnc_image.resize((self.driver.width, self.driver.height))
                # if at least two frames have been processed, get a bounding box of their difference region
                if new_vnc_image and previous_vnc_image:
                    diff_bbox = self.band(self.img_diff(new_vnc_image, previous_vnc_image))
                # frames differ, so we should update the display
                if diff_bbox:
                    # increment update counter
                    updates = (updates + 1) % full_interval
                    # if partial update is supported and it's not time for a full refresh,
                    # draw just the different region
                    if updates > 0 and (self.driver.supports_partial and self.partial):
                        print("partial ({}): {}".format(updates, diff_bbox))
                        self.driver.draw(diff_bbox[0], diff_bbox[1], new_vnc_image.crop(diff_bbox))
                    # if partial update is not possible or desired, do a full refresh
                    else:
                        print("full ({}): {}".format(updates, new_vnc_image.size))
                        self.driver.draw(0, 0, new_vnc_image)
                # otherwise this is the first frame, so run a full refresh to get things going
                else:
                    if updates == 0:
                        updates = (updates + 1) % full_interval
                        print("initial ({}): {}".format(updates, new_vnc_image.size))
                        self.driver.draw(0, 0, new_vnc_image)
                previous_vnc_image = new_vnc_image.copy()
                time.sleep(float(sleep))

    def showtext(self, text, fill, cursor=None, portrait=False, flipx=False, flipy=False, oldimage=None):
        """Draw a string on the screen"""
        if self.ready():
            # set order of h, w according to orientation
            image = Image.new('1', (self.driver.width, self.driver.height) if portrait else (
                self.driver.height, self.driver.width),
                              self.white)
            # create the Draw object and draw the text
            draw = ImageDraw.Draw(image)
            draw.text((0, 0), text, font=self.font, fill=fill, spacing=self.spacing)

            # if we want a cursor, draw it - the most convoluted part
            if cursor and self.cursor:
                if self.cursor == 'block':
                    image = self.draw_block_cursor(cursor, image)
                else:
                    self.draw_line_cursor(cursor, draw)
            # rotate image if using landscape
            if not portrait:
                image = image.rotate(90, expand=True)
            # apply flips if desired
            if flipx:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            if flipy:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            # find out which part changed and draw only that on the display
            if oldimage and self.driver.supports_partial and self.partial:
                # create a bounding box of the altered region and
                # make the X coordinates divisible by 8
                diff_bbox = self.band(self.img_diff(image, oldimage))
                # crop the altered region and draw it on the display
                if diff_bbox:
                    self.driver.draw(diff_bbox[0], diff_bbox[1], image.crop(diff_bbox))
            else:
                # if no previous image, draw the entire display
                self.driver.draw(0, 0, image)
            return image
        else:
            self.error("Display not ready")
    
    def clear(self):
        """Clears the display; set all black, then all white, or use INIT mode, if driver supports it."""
        if self.ready():
            self.driver.clear()
            print('Display reinitialized.')
        else:
            self.error("Display not ready")


class Settings:
    """A class to store CLI settings so they can be referenced in the subcommands"""
    args = {}

    def __init__(self, **kwargs):
        self.args = kwargs

    def get_init_tty(self):
        tty = PaperTTY(**self.args)
        tty.init_display()
        return tty


def get_drivers():
    """Get the list of available drivers as a dict
    Format: { '<NAME>': { 'desc': '<DESCRIPTION>', 'class': <CLASS> }, ... }"""
    driverdict = {}
    driverlist = [drivers_partial.EPD1in54, drivers_partial.EPD2in13,
                  drivers_partial.EPD2in13v2, drivers_partial.EPD2in9,
                  drivers_partial.EPD2in13d, driver_4in2.EPD4in2,

                  drivers_full.EPD2in7, drivers_full.EPD7in5,
                  drivers_full.EPD7in5v2,

                  drivers_color.EPD4in2b, drivers_color.EPD7in5b,
                  drivers_color.EPD5in83, drivers_color.EPD5in83b,

                  drivers_colordraw.EPD1in54b, drivers_colordraw.EPD1in54c,
                  drivers_colordraw.EPD2in13b, drivers_colordraw.EPD2in7b,
                  drivers_colordraw.EPD2in9b,

                  driver_it8951.IT8951,

                  drivers_base.Dummy, drivers_base.Bitmap]
    for driver in driverlist:
        driverdict[driver.__name__] = {'desc': driver.__doc__, 'class': driver}
    return driverdict


def get_driver_list():
    """Get a neat printable driver list"""
    order = OrderedDict(sorted(get_drivers().items()))
    return '\n'.join(["{}{}".format(driver.ljust(15), order[driver]['desc']) for driver in order])


def display_image(driver, image, stretch=False, no_resize=False, fill_color="white"):
    """
    Display the given image using the given driver and options.
    :param driver: device driver (subclass of `WaveshareEPD`)
    :param image: image data to display
    :param stretch: whether to stretch the image so that it fills the screen in both dimentions
    :param no_resize: whether the image should not be resized if it does not fit the screen (will raise `RuntimeError`
    if image is too large)
    :param fill_color: colour to fill space when image is resized but one dimension does not fill the screen
    :return: the image that was rendered
    """
    if stretch and no_resize:
        raise ValueError('Cannot set "no-resize" with "stretch"')

    image_width, image_height = image.size

    if stretch:
        if (image_width, image_height) == (driver.width, driver.height):
            output_image = image
        else:
            output_image = image.resize((driver.width, driver.height))
    else:
        if no_resize:
            if image_width > driver.width or image_height > driver.height:
                raise RuntimeError('Image ({0}x{1}) needs to be resized to fit the screen ({2}x{3})'
                                   .format(image_width, image_height, driver.width, driver.height))
            # Pad only
            output_image = Image.new(image.mode, (driver.width, driver.height), color=fill_color)
            output_image.paste(image, (0, 0))
        else:
            # Scales and pads
            output_image = ImageOps.pad(image, (driver.width, driver.height), color=fill_color)

    driver.draw(0, 0, output_image)

    return output_image


@click.group()
@click.option('--driver', default=None, help='Select display driver')
@click.option('--nopartial', is_flag=True, default=False, help="Don't use partial updates even if display supports it")
@click.option('--encoding', default='latin_1', help='Encoding to use for the buffer', show_default=True)
@click.pass_context
def cli(ctx, driver, nopartial, encoding):
    """Display stdin or TTY on a Waveshare e-Paper display"""
    if not driver:
        PaperTTY.error(
            "You must choose a display driver. If your 'C' variant is not listed, use the 'B' driver.\n\n{}".format(
                get_driver_list()))
    else:
        matched_drivers = [n for n in get_drivers() if n.lower() == driver.lower()]
        if not matched_drivers:
            PaperTTY.error('Invalid driver selection, choose from:\n{}'.format(get_driver_list()))
        ctx.obj = Settings(driver=matched_drivers[0], partial=not nopartial, encoding=encoding)
    pass


@click.command(name='list')
def list_drivers():
    """List available display drivers"""
    PaperTTY.error(get_driver_list(), code=0)


@click.command()
@click.option('--size', default=16, help='Stripe size to fill with (8-32)')
@click.pass_obj
def scrub(settings, size):
    """Slowly fill with black, then white"""
    if size not in range(8, 32 + 1):
        PaperTTY.error("Invalid stripe size, must be 8-32")
    ptty = settings.get_init_tty()
    ptty.driver.scrub(fillsize=size)


@click.command()
@click.option('--font', default=PaperTTY.defaultfont, help='Path to a TrueType or PIL font',
              show_default=True)
@click.option('--size', 'fontsize', default=8, help='Font size', show_default=True)
@click.option('--width', default=None, help='Fit to width [default: display width / font width]')
@click.option('--portrait', default=False, is_flag=True, help='Use portrait orientation', show_default=True)
@click.option('--nofold', default=False, is_flag=True, help="Don't fold the input", show_default=True)
@click.option('--spacing', default='0', help='Line spacing for the text, "auto" to automatically determine a good value', show_default=True)
@click.pass_obj
def stdin(settings, font, fontsize, width, portrait, nofold, spacing):
    """Display standard input and leave it on screen"""
    settings.args['font'] = font
    settings.args['fontsize'] = fontsize
    settings.args['spacing'] = spacing
    ptty = settings.get_init_tty()
    text = sys.stdin.read()
    if not nofold:
        if width:
            text = ptty.fold(text, width)
        else:
            font_width = ptty.font.getsize('M')[0]
            max_width = int((ptty.driver.width - 8) / font_width) if portrait else int(ptty.driver.height / font_width)
            text = ptty.fold(text, width=max_width)
    ptty.showtext(text, fill=ptty.driver.black, portrait=portrait)


@click.command()
@click.option('--image', 'image_location', help='Location of image to display (omit for stdin)', show_default=True)
@click.option('--stretch', default=False, is_flag=True,
              help='Stretch image so that it fills the entire screen (may distort your image!)')
@click.option('--no-resize', default=False, is_flag=True,
              help='Do not resize image to fit the screen (an error will occur if the image is too large!)')
@click.option('--portrait', default=False, is_flag=True, help='Use portrait orientation', show_default=True)
@click.option('--fill-color', default='white', help='Colour to pad image with', show_default=True)
@click.pass_obj
def image(settings, image_location, stretch, no_resize, portrait, fill_color):
    """ Display an image """
    if image_location is None or image_location == '-':
        # XXX: logging to stdout, in line with the rest of this project
        print('Reading image data from stdin... (set "--image" to load an image from a given file path)')
        image_data = BytesIO(sys.stdin.buffer.read())
        image = Image.open(image_data)
    else:
        image = Image.open(image_location)

    if portrait:
        image = image.transpose(Image.ROTATE_90)

    ptty = settings.get_init_tty()

    display_image(ptty.driver, image, stretch, no_resize, fill_color)


@click.command()
@click.option('--host', default="localhost", help="VNC host to connect to", show_default=True)
@click.option('--display', default="0", help="VNC display to use (0 = port 5900)", show_default=True)
@click.option('--password', default=None, help="VNC password")
@click.option('--rotate', default=None, help="Rotate screen (90 / 180 / 270)")
@click.option('--invert', default=False, is_flag=True, help="Invert colors")
@click.option('--sleep', default=1, show_default=True, help="Refresh interval (s)", type=float)
@click.option('--fullevery', default=50, show_default=True, help="# of partial updates between full updates")
@click.pass_obj
def vnc(settings, host, display, password, rotate, invert, sleep, fullevery):
    ptty = settings.get_init_tty()
    ptty.showvnc(host, display, password, int(rotate) if rotate else None, invert, sleep, fullevery)


@click.command()
@click.option('--vcsa', default='/dev/vcsa1', help='Virtual console device (/dev/vcsa[1-63])', show_default=True)
@click.option('--font', default=PaperTTY.defaultfont, help='Path to a TrueType or PIL font', show_default=True)
@click.option('--size', 'fontsize', default=8, help='Font size', show_default=True)
@click.option('--noclear', default=False, is_flag=True, help='Leave display content on exit')
@click.option('--nocursor', default=False, is_flag=True, help="(DEPRECATED, use --cursor=none instead) Don't draw the cursor")
@click.option('--cursor', default='legacy', help='Set cursor type. Valid values are default (underscore cursor at a sensible place), block (inverts colors at cursor), none (draws no cursor) or a number n (underscore cursor n pixels from the bottom)', show_default=False)
@click.option('--sleep', default=0.1, help='Minimum sleep between refreshes', show_default=True)
@click.option('--rows', 'ttyrows', default=None, help='Set TTY rows (--cols required too)')
@click.option('--cols', 'ttycols', default=None, help='Set TTY columns (--rows required too)')
@click.option('--portrait', default=False, is_flag=True, help='Use portrait orientation', show_default=False)
@click.option('--flipx', default=False, is_flag=True, help='Flip X axis (EXPERIMENTAL/BROKEN)', show_default=False)
@click.option('--flipy', default=False, is_flag=True, help='Flip Y axis (EXPERIMENTAL/BROKEN)', show_default=False)
@click.option('--spacing', default='0', help='Line spacing for the text, "auto" to automatically determine a good value', show_default=True)
@click.option('--scrub', 'apply_scrub', is_flag=True, default=False, help='Apply scrub when starting up',
              show_default=True)
@click.option('--autofit', is_flag=True, default=False, help='Autofit terminal size to font size', show_default=True)
@click.option('--attributes', is_flag=True, default=False, help='Use attributes', show_default=True)
@click.option('--interactive', is_flag=True, default=False, help='Interactive mode')
@click.pass_obj
def terminal(settings, vcsa, font, fontsize, noclear, nocursor, cursor, sleep, ttyrows, ttycols, portrait, flipx, flipy,
             spacing, apply_scrub, autofit, attributes, interactive):
    """Display virtual console on an e-Paper display, exit with Ctrl-C."""
    settings.args['font'] = font
    settings.args['fontsize'] = fontsize
    settings.args['spacing'] = spacing

    if cursor != 'legacy' and nocursor:
        print("--cursor and --nocursor can't be used together. To hide the cursor, use --cursor=none")
        sys.exit(1)

    if nocursor:
        print("--nocursor is deprecated. Use --cursor=none instead")
        settings.args['cursor'] = None

    if cursor == 'default' or cursor == 'legacy':
        settings.args['cursor'] = 'default'
    elif cursor == 'none':
        settings.args['cursor'] = None
    else:
        settings.args['cursor'] = cursor

    ptty = settings.get_init_tty()

    if apply_scrub:
        ptty.driver.scrub()
    oldbuff = ''
    oldimage = None
    oldcursor = None
    # dirty - should refactor to make this cleaner
    flags = {'scrub_requested': False, 'show_menu': False, 'clear': False}
    
    # handle SIGINT from `systemctl stop` and Ctrl-C
    def sigint_handler(sig, frame):
        if not interactive:
            print("Exiting (SIGINT)...")
            if not noclear:
                ptty.showtext(oldbuff, fill=ptty.white, **textargs)
            sys.exit(0)
        else:
             print('Showing menu, please wait ...')
             flags['show_menu'] = True

    # toggle scrub flag when SIGUSR1 received
    def sigusr1_handler(sig, frame):
        print("Scrubbing display (SIGUSR1)...")
        flags['scrub_requested'] = True

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGUSR1, sigusr1_handler)

    # group the various params for readability
    textargs = {'portrait': portrait, 'flipx': flipx, 'flipy': flipy}

    if any([ttyrows, ttycols]) and not all([ttyrows, ttycols]):
        ptty.error("You must define both --rows and --cols to change terminal size.")
    if ptty.valid_vcsa(vcsa):
        if all([ttyrows, ttycols]):
            ptty.set_tty_size(ptty.ttydev(vcsa), ttyrows, ttycols)
        else:
            # if size not specified manually, see if autofit was requested
            if autofit:
                max_dim = ptty.fit(portrait)
                print("Automatic resize of TTY to {} rows, {} columns".format(max_dim[1], max_dim[0]))
                ptty.set_tty_size(ptty.ttydev(vcsa), max_dim[1], max_dim[0])
        if interactive:
            print("Started displaying {}, minimum update interval {} s, open menu with Ctrl-C".format(vcsa, sleep))
        else:
            print("Started displaying {}, minimum update interval {} s, exit with Ctrl-C".format(vcsa, sleep))
        character_width, vcsudev = ptty.vcsudev(vcsa)
        while True:
            if flags['show_menu']:
                flags['show_menu'] = False
                print()
                print('Rendering paused. Enter')
                print('    (f) to change font,')
                print('    (s) to change spacing,')
                if ptty.is_truetype:
                    print('    (h) to change font size,')
                print('    (c) to scrub,')
                print('    (i) reinitialize display,')
                print('    (r) do a full refresh,')
                print('    (x) to exit,')
                print('    anything else to continue.')
                print('Command line arguments for current settings:\n    --font {} --size {} --spacing {}'.format(ptty.fontfile, ptty.fontsize, ptty.spacing))

                ch = sys.stdin.readline().strip()
                if ch == 'x':
                    if not noclear:
                        ptty.showtext(oldbuff, fill=ptty.white, **textargs)
                    sys.exit(0)
                elif ch == 'f':
                    print('Current font: {}'.format(ptty.fontfile))
                    new_font = click.prompt('Enter new font (leave empty to abort)', default='', show_default=False)
                    if new_font:
                        ptty.spacing = spacing
                        ptty.font = ptty.load_font(new_font, keep_if_not_found=True)
                        if autofit:
                            max_dim = ptty.fit(portrait)
                            print("Automatic resize of TTY to {} rows, {} columns".format(max_dim[1], max_dim[0]))
                            ptty.set_tty_size(ptty.ttydev(vcsa), max_dim[1], max_dim[0])
                        oldbuff = None
                    else:
                        print('Font not changed')
                elif ch == 's':
                    print('Current spacing: {}'.format(ptty.spacing))
                    new_spacing = click.prompt('Enter new spacing (leave empty to abort)', default='empty', type=int, show_default=False)
                    if new_spacing != 'empty':
                        ptty.spacing = new_spacing
                        ptty.recalculate_font()
                        if autofit:
                            max_dim = ptty.fit(portrait)
                            print("Automatic resize of TTY to {} rows, {} columns".format(max_dim[1], max_dim[0]))
                            ptty.set_tty_size(ptty.ttydev(vcsa), max_dim[1], max_dim[0])
                        oldbuff = None
                    else:
                        print('Spacing not changed')
                elif ch == 'h' and ptty.is_truetype:
                    print('Current font size: {}'.format(ptty.fontsize))
                    new_fontsize = click.prompt('Enter new font size (leave empty to abort)', default='empty', type=int, show_default=False)
                    if new_fontsize != 'empty':
                        ptty.fontsize = new_fontsize
                        ptty.spacing = spacing
                        ptty.font = ptty.load_font(path=None)
                        if autofit:
                            max_dim = ptty.fit(portrait)
                            print("Automatic resize of TTY to {} rows, {} columns".format(max_dim[1], max_dim[0]))
                            ptty.set_tty_size(ptty.ttydev(vcsa), max_dim[1], max_dim[0])
                        oldbuff = None
                    else:
                        print('Font size not changed')
                elif ch == 'c':
                    flags['scrub_requested'] = True
                elif ch == 'i':
                    ptty.clear()
                    oldimage = None
                    oldbuff = None
                elif ch == 'r':
                    if oldimage:
                        ptty.driver.reset()
                        ptty.driver.init(partial=False)
                        ptty.driver.draw(0, 0, oldimage)
                        ptty.driver.reset()
                        ptty.driver.init(ptty.partial)

            # if user or SIGUSR1 toggled the scrub flag, scrub display and start with a fresh image
            if flags['scrub_requested']:
                ptty.driver.scrub()
                # clear old image and buffer and restore flag
                oldimage = None
                oldbuff = ''
                flags['scrub_requested'] = False
            
            with open(vcsa, 'rb') as f:
                with open(vcsudev, 'rb') as vcsu:
                    # read the first 4 bytes to get the console attributes
                    attributes = f.read(4)
                    rows, cols, x, y = list(map(ord, struct.unpack('cccc', attributes)))

                    # read from the text buffer 
                    buff = vcsu.read()
                    if character_width == 4:
                        # work around weird bug
                        buff = buff.replace(b'\x20\x20\x20\x20', b'\x20\x00\x00\x00')
                    # find character under cursor (in case using a non-fixed width font)
                    char_under_cursor = buff[character_width * (y * rows + x):character_width * (y * rows + x + 1)]
                    encoding = 'utf_32' if character_width == 4 else ptty.encoding
                    cursor = (x, y, char_under_cursor.decode(encoding, 'ignore'))
                    # add newlines per column count
                    buff = ''.join([r.decode(encoding, 'replace') + '\n' for r in ptty.split(buff, cols * character_width)])
                    # do something only if content has changed or cursor was moved
                    if buff != oldbuff or cursor != oldcursor:
                        # show new content
                        oldimage = ptty.showtext(buff, fill=ptty.black, cursor=cursor if not nocursor else None,
                                                oldimage=oldimage,
                                                **textargs)
                        oldbuff = buff
                        oldcursor = cursor
                    else:
                        # delay before next update check
                        time.sleep(float(sleep))


if __name__ == '__main__':
    # add all the CLI commands
    cli.add_command(scrub)
    cli.add_command(terminal)
    cli.add_command(stdin)
    cli.add_command(image)
    cli.add_command(vnc)
    cli.add_command(list_drivers)
    cli()
