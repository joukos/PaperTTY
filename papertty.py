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
# for setting TTY size
import termios
# for sleeping
import time
# for command line usage
import click
# for drawing
from PIL import Image, ImageChops, ImageDraw, ImageFont
# for tidy driver list
from collections import OrderedDict


class PaperTTY:
    """The main class - handles various settings and showing text on the display"""
    defaultfont = "tom-thumb.pil"
    defaultsize = 8
    driver = None
    partial = None
    initialized = None
    font = None
    fontsize = None
    white = None
    black = None
    encoding = None

    def __init__(self, driver, font=defaultfont, fontsize=defaultsize, partial=None, encoding='utf-8'):
        """Create a PaperTTY with the chosen driver and settings"""
        self.driver = get_drivers()[driver]['class']()
        self.font = self.load_font(font, fontsize) if font else None
        self.fontsize = fontsize
        self.partial = partial
        self.white = self.driver.white
        self.black = self.driver.black
        self.encoding = encoding

    def ready(self):
        """Check that the driver is loaded and initialized"""
        return self.driver and self.initialized

    @staticmethod
    def error(msg, code=1):
        """Print error and exit"""
        print(msg)
        sys.exit(code)

    @staticmethod
    def set_tty_size(tty, rows, cols):
        """Set a TTY (/dev/tty*) to a certain size. Must be a real TTY that support ioctls."""
        with open(tty, 'w') as tty:
            size = struct.pack("HHHH", int(rows), int(cols), 0, 0)
            try:
                fcntl.ioctl(tty.fileno(), termios.TIOCSWINSZ, size)
            except OSError:
                print("TTY refused to resize (rows={}, cols={}), continuing anyway.".format(rows, cols))
                print("Try setting a sane size manually.")

    @staticmethod
    def font_height(font, spacing=0):
        """Calculate 'actual' height of a font"""
        # check if font is a TrueType font
        truetype = isinstance(font, ImageFont.FreeTypeFont)
        # dirty trick to get "maximum height"
        fh = font.getsize('hg')[1]
        # get descent value
        descent = font.getmetrics()[1] if truetype else 0
        # the reported font size
        size = font.size if truetype else fh
        # Why descent/2? No idea, but it works "well enough" with
        # big and small sizes
        return size - (descent / 2) + spacing

    @staticmethod
    def band(bb):
        """Stretch a bounding box's X coordinates to be divisible by 8,
           otherwise weird artifacts occur as some bits are skipped."""
        return (bb[0] & 0xF8, bb[1], (bb[2] + 8) & 0xF8, bb[3]) if bb else None

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

    def load_font(self, path, size):
        """Load the PIL or TrueType font"""
        font = None
        if os.path.isfile(path):
            try:
                # first check if the font looks like a PILfont
                with open(path, 'rb') as f:
                    if f.readline() == b"PILfont\n":
                        font = ImageFont.load(path)
                        # otherwise assume it's a TrueType font
                    else:
                        font = ImageFont.truetype(path, size)
            except IOError:
                self.error("Invalid font: '{}'".format(path))
        else:
            print("The font '{}' could not be found, using fallback font instead.".format(path))
            font = ImageFont.load_default()

        return font

    def init_display(self):
        """Initialize the display - call the driver's init method"""
        self.driver.init(partial=self.partial)
        self.initialized = True

    def fit(self, portrait=False, spacing=0):
        """Return the maximum columns and rows we can display with this font"""
        width = self.font.getsize('M')[0]
        height = self.font_height(self.font, spacing)
        # hacky, subtract just a bit to avoid going over the border with small fonts
        pw = self.driver.width - 3
        ph = self.driver.height
        return int((pw if portrait else ph) / width), int((ph if portrait else pw) / height)

    def showtext(self, text, fill, cursor=None, portrait=False, flipx=False, flipy=False, oldimage=None, spacing=0):
        """Draw a string on the screen"""
        if self.ready():
            # set order of h, w according to orientation
            image = Image.new('1', (self.driver.width, self.driver.height) if portrait else (
                self.driver.height, self.driver.width),
                              self.white)
            # create the Draw object and draw the text
            draw = ImageDraw.Draw(image)
            draw.text((0, 0), text, font=self.font, fill=fill, spacing=spacing)

            # if we want a cursor, draw it - the most convoluted part
            if cursor:
                cur_x, cur_y = cursor[0], cursor[1]
                # get the width of the character under cursor
                # (in case we didn't use a fixed width font...)
                fw = self.font.getsize(chr(cursor[2]))[0]
                # desired cursor width
                cur_width = fw - 1
                # get font height
                height = self.font_height(self.font, spacing)
                # starting X is the font width times current column
                start_x = cur_x * fw
                # add 1 because rows start at 0 and we want the cursor at the bottom
                start_y = (cur_y + 1) * height - 1 - spacing
                # draw the cursor line
                draw.line((start_x, start_y, start_x + cur_width, start_y), fill=self.black)
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
    driverlist = [drivers_partial.EPD1in54, drivers_partial.EPD2in13, drivers_partial.EPD2in9,
                  drivers_partial.EPD2in13d,
                  drivers_full.EPD2in7, drivers_full.EPD4in2, drivers_full.EPD7in5,
                  drivers_color.EPD4in2b, drivers_color.EPD7in5b, drivers_color.EPD5in83, drivers_color.EPD5in83b,
                  drivers_colordraw.EPD1in54b, drivers_colordraw.EPD1in54c, drivers_colordraw.EPD2in13b,
                  drivers_colordraw.EPD2in7b, drivers_colordraw.EPD2in9b,
                  drivers_base.Dummy, drivers_base.Bitmap]
    for driver in driverlist:
        driverdict[driver.__name__] = {'desc': driver.__doc__, 'class': driver}
    return driverdict


def get_driver_list():
    """Get a neat printable driver list"""
    order = OrderedDict(sorted(get_drivers().items()))
    return '\n'.join(["{}{}".format(driver.ljust(15), order[driver]['desc']) for driver in order])


@click.group()
@click.option('--driver', default=None, help='Select display driver')
@click.option('--nopartial', is_flag=True, default=False, help="Don't use partial updates even if display supports it")
@click.option('--encoding', default='utf-8', help='Encoding to use for the buffer', show_default=True)
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
    if size not in range(8, 32):
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
@click.option('--spacing', default=0, help='Line spacing for the text', show_default=True)
@click.pass_obj
def stdin(settings, font, fontsize, width, portrait, nofold, spacing):
    """Display standard input and leave it on screen"""
    settings.args['font'] = font
    settings.args['fontsize'] = fontsize
    ptty = settings.get_init_tty()
    text = sys.stdin.read()
    if not nofold:
        if width:
            text = ptty.fold(text, width)
        else:
            font_width = ptty.font.getsize('M')[0]
            max_width = int((ptty.driver.width - 8) / font_width) if portrait else int(ptty.driver.height / font_width)
            text = ptty.fold(text, width=max_width)
    ptty.showtext(text, fill=ptty.driver.black, portrait=portrait, spacing=spacing)


@click.command()
@click.option('--vcsa', default='/dev/vcsa1', help='Virtual console device (/dev/vcsa[1-63])', show_default=True)
@click.option('--font', default=PaperTTY.defaultfont, help='Path to a TrueType or PIL font', show_default=True)
@click.option('--size', 'fontsize', default=8, help='Font size', show_default=True)
@click.option('--noclear', default=False, is_flag=True, help='Leave display content on exit')
@click.option('--nocursor', default=False, is_flag=True, help="Don't draw the cursor")
@click.option('--sleep', default=0.1, help='Minimum sleep between refreshes', show_default=True)
@click.option('--rows', 'ttyrows', default=None, help='Set TTY rows (--cols required too)')
@click.option('--cols', 'ttycols', default=None, help='Set TTY columns (--rows required too)')
@click.option('--portrait', default=False, is_flag=True, help='Use portrait orientation', show_default=False)
@click.option('--flipx', default=False, is_flag=True, help='Flip X axis (EXPERIMENTAL/BROKEN)', show_default=False)
@click.option('--flipy', default=False, is_flag=True, help='Flip Y axis (EXPERIMENTAL/BROKEN)', show_default=False)
@click.option('--spacing', default=0, help='Line spacing for the text', show_default=True)
@click.option('--scrub', 'apply_scrub', is_flag=True, default=False, help='Apply scrub when starting up',
              show_default=True)
@click.option('--autofit', is_flag=True, default=False, help='Autofit terminal size to font size', show_default=True)
@click.pass_obj
def terminal(settings, vcsa, font, fontsize, noclear, nocursor, sleep, ttyrows, ttycols, portrait, flipx, flipy,
             spacing, apply_scrub, autofit):
    """Display virtual console on an e-Paper display, exit with Ctrl-C."""
    settings.args['font'] = font
    settings.args['fontsize'] = fontsize
    ptty = settings.get_init_tty()

    if apply_scrub:
        ptty.driver.scrub()
    oldbuff = ''
    oldimage = None
    oldcursor = None
    # dirty - should refactor to make this cleaner
    flags = {'scrub_requested': False}

    # handle SIGINT from `systemctl stop` and Ctrl-C
    def sigint_handler(sig, frame):
        print("Exiting (SIGINT)...")
        if not noclear:
            ptty.showtext(oldbuff, fill=ptty.white, **textargs)
            sys.exit(0)

    # toggle scrub flag when SIGUSR1 received
    def sigusr1_handler(sig, frame):
        print("Scrubbing display (SIGUSR1)...")
        flags['scrub_requested'] = True

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGUSR1, sigusr1_handler)

    # group the various params for readability
    textargs = {'portrait': portrait, 'flipx': flipx, 'flipy': flipy, 'spacing': spacing}

    if any([ttyrows, ttycols]) and not all([ttyrows, ttycols]):
        ptty.error("You must define both --rows and --cols to change terminal size.")
    if ptty.valid_vcsa(vcsa):
        if all([ttyrows, ttycols]):
            ptty.set_tty_size(ptty.ttydev(vcsa), ttyrows, ttycols)
        else:
            # if size not specified manually, see if autofit was requested
            if autofit:
                max_dim = ptty.fit(portrait, spacing)
                print("Automatic resize of TTY to {} rows, {} columns".format(max_dim[1], max_dim[0]))
                ptty.set_tty_size(ptty.ttydev(vcsa), max_dim[1], max_dim[0])
        print("Started displaying {}, minimum update interval {} s, exit with Ctrl-C".format(vcsa, sleep))
        while True:
            # if SIGUSR1 toggled the scrub flag, scrub display and start with a fresh image
            if flags['scrub_requested']:
                ptty.driver.scrub()
                # clear old image and buffer and restore flag
                oldimage = None
                oldbuff = ''
                flags['scrub_requested'] = False
            with open(vcsa, 'rb') as f:
                # read the first 4 bytes to get the console attributes
                attributes = f.read(4)
                rows, cols, x, y = list(map(ord, struct.unpack('cccc', attributes)))

                # read rest of the console content into buffer
                buff = f.read()
                # SKIP all the attribute bytes
                # (change this (and write more code!) if you want to use the attributes with a
                # three-color display)
                buff = buff[0::2]
                # find character under cursor (in case using a non-fixed width font)
                char_under_cursor = buff[y * rows + x]
                cursor = (x, y, char_under_cursor)
                # add newlines per column count
                buff = ''.join([r.decode(ptty.encoding, 'ignore') + '\n' for r in ptty.split(buff, cols)])
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
    cli.add_command(list_drivers)
    cli()
