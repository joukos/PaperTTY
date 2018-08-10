#!/usr/bin/python
# -*- coding: utf-8 -*-

# Jouko Strömmer, 2018
# Copyright and related rights waived via CC0
# https://creativecommons.org/publicdomain/zero/1.0/legalcode

# As you would expect, use this at your own risk! This code was created
# so you (yes, YOU!) can make it better.
#
# Requires Python 2.7+


_WHITE=255
_BLACK=0
defaultfont = "Andale_Mono.ttf"

# for command line usage
import click
# for sleeping
import time
# for drawing
import Image
import ImageDraw
import ImageFont
import ImageChops
import ImageOps
# for stdin and exit
import sys
# for unpacking virtual console data
import struct
# for setting TTY size
import termios
import struct
import fcntl
# for validating type of and access to device files
import os
# for dynamic import of required display module
import importlib
# for gracefully handling signals (systemd service)
import signal

# critical globals
epd = None
_PAPER_WIDTH = None
_PAPER_HEIGHT = None


def error(msg, code=1):
    """Print error and exit"""
    print(msg)
    sys.exit(code)


def init_display(model):
    """Import the necessary module and initialize the display"""
    global epd
    global _PAPER_WIDTH
    global _PAPER_HEIGHT
   
    # attempt to import the module for the particular model
    try:
        module = importlib.import_module(model)
    except ImportError:
        error("Failed to import module '{}', aborting.".format(model))

    try:
        epd = module.EPD()
        # Initialize and use partial update
        epd.init(epd.lut_partial_update)
        # Set global width and height
        _PAPER_WIDTH = module.EPD_WIDTH
        _PAPER_HEIGHT = module.EPD_HEIGHT
    except NameError:
        error("Failed to instantiate display, does the model match the module name?")


def set_tty_size(tty, rows, cols):
    """Set a TTY (/dev/tty*) to a certain size. Must be a real TTY that support ioctls."""
    with open(tty, 'w') as tty:
        size = struct.pack("HHHH", int(rows), int(cols), 0, 0)
        fcntl.ioctl(tty.fileno(), termios.TIOCSWINSZ, size)


def showtext(text,fill,font=None,size=None,cursor=None,portrait=False,flipx=False,flipy=False,oldimage=None,spacing=0):
    """Draw a string on the screen"""
    # set order of h, w according to orientation
    image = Image.new('1', (_PAPER_WIDTH, _PAPER_HEIGHT) if portrait else (_PAPER_HEIGHT, _PAPER_WIDTH), _WHITE)
    # create the Draw object and draw the text
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), text, font = font, fill = fill, spacing = spacing)
    # if we want a cursor, draw it - the most convoluted part
    if cursor:
        cur_x, cur_y = cursor[0], cursor[1]
        # get the width of the character under cursor
        # (in case we didn't use a fixed width font...)
        fw = font.getsize(cursor[2])[0]
        # dirty trick to get "maximum height"
        fh = font.getsize('hg')[1]
        # desired cursor width
        cur_width = fw - 1
        # get descent value
        descent = font.getmetrics()[1]
        # the reported font size
        size = font.size
        # Why descent/2? No idea, but it works "well enough" with
        # big and small sizes
        HEIGHT = size - (descent / 2) + spacing
        # starting X is the font width times current column
        start_x = cur_x * fw
        # add 1 because rows start at 0 and we want the cursor at the bottom
        start_y = (cur_y + 1) * HEIGHT - 1 - spacing
        # draw the cursor line
        draw.line((start_x, start_y, start_x + cur_width, start_y),fill = _BLACK)
    # rotate image if using landscape
    if not portrait:
        image = image.rotate(90, expand=True)
    # apply flips if desired
    if flipx:
        print("flip x")
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    if flipy:
        print("flip y")
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
    # find out which part changed and draw only that on the display
    if oldimage:
        # create a bounding box of the altered region and
        # make the X coordinates divisible by 8
        diff_bbox = band(img_diff(image, oldimage))
        # crop the altered region and draw it on the display
        if diff_bbox:
            replace_area(diff_bbox[0], diff_bbox[1], image.crop(diff_bbox))
    else:
        # if no previous image, draw the entire display
        replace_area(0,0,image)
    return image


def band(bb):
    """Stretch a bounding box's X coordinates to be divisible by 8,
       otherwise weird artifacts occur as some bits are skipped."""
    return (bb[0] & 0xF8, bb[1], (bb[2] + 8) & 0xF8, bb[3]) if bb else None


def fill(color, fillsize = 16):
    """Slow fill routine"""
    image = Image.new('1', (fillsize, _PAPER_HEIGHT), color)
    for x in range(0, _PAPER_WIDTH, fillsize):
        for fc in range(2):
            epd.set_frame_memory(image, x, 0)
            epd.display_frame()


def split(s, n):
    """Split a sequence into parts of size n"""
    return [s[begin:begin+n] for begin in range(0, len(s), n)]


def fold(text, width=None, filter=None):
    """Format a string to a specified width and/or filter it"""
    buff = text
    if width:
        buff = ''.join( [ r + '\n' for r in split(buff, int(width)) ] ).rstrip()
    if filter:
        buff = [ c for c in buff if filter(c) ]
    return buff


def img_diff(img1, img2):
    """Return the bounding box of differences between two images"""
    return ImageChops.difference(img1, img2).getbbox()


def replace_area(x, y, image):
    """Replace a particular area on the display with an image"""
    epd.set_frame_memory(image, x, y)
    epd.display_frame()
    epd.set_frame_memory(image, x, y)
    epd.display_frame()


@click.group()
@click.option('--model', default=None, help='Select display model')
def cli(model):
    """Display stdin or TTY on a Waveshare e-Paper display"""
    if not model:
        print("You must download the appropriate Python modules from Waveshare's site\nand place them in this directory.\n\nGrab the .7z package for your model and extract '/raspberrypi/python/*' here.\nThen, use '--model epdXinY', for example '--model epd2in13'.")
    else:
        init_display(model)
    pass


@click.command()
@click.option('--size', default=16, help='Chunk width', show_default=True)
def scrub(size):
    """Slowly fill with black, then white"""
    if not epd:
        exit("Display is not configured, use top-level option '--model', aborting.")
    fill(_BLACK, fillsize=size)
    fill(_WHITE, fillsize=size)


@click.command()
@click.option('--font', default=defaultfont, help='Path to a TrueType font', show_default=True)
@click.option('--size', default=8, help='Font size', show_default=True)
@click.option('--width', default=None, help='Fit to width [default: display width / font width]')
@click.option('--portrait', default=False, is_flag=True, help='Use portrait orientation', show_default=True)
@click.option('--nofold', default=False, is_flag=True, help="Don't fold the input", show_default=True)
@click.option('--spacing', default=0, help='Line spacing for the text', show_default=True)
def stdin(font, size, width, portrait, nofold, spacing):
    """Display standard input and leave it on screen"""
    if not epd:
        exit("Display is not configured, use top-level option '--model', aborting.")
    if os.path.isfile(font):
        ft = ImageFont.truetype(font, size)
    else:
        error("The font '{}' could not be found, aborting.".format(font))

    text = sys.stdin.read()
    if not nofold:
        if width:
            text = fold(text, width)
        else:
            font_width = ft.getsize('M')[0]
            max_width = int((_PAPER_WIDTH - 8) / font_width) if portrait else int(_PAPER_HEIGHT / font_width)
            text = fold(text, width=max_width)
    showtext(text, fill = _BLACK, font = ft, size = size, portrait = portrait, spacing = spacing)


def ttydev(vcsa):
    """Return associated tty for vcsa device, ie. /dev/vcsa1 -> /dev/tty1"""
    return vcsa.replace("vcsa", "tty")


def valid_vcsa(vcsa):
    """Check that the vcsa device and associated terminal seem sane"""
    VCSA_MAJOR = 7
    TTY_MAJOR = 4
    VCSA_RANGE = range(128,191)
    TTY_RANGE = range(1,63)

    tty = ttydev(vcsa)
    vs = os.stat(vcsa)
    ts = os.stat(tty)

    vcsa_major, vcsa_minor = os.major(vs.st_rdev), os.minor(vs.st_rdev)
    tty_major, tty_minor = os.major(ts.st_rdev), os.minor(ts.st_rdev)
    if not (vcsa_major == VCSA_MAJOR and vcsa_minor in VCSA_RANGE):
        print("Not a valid vcsa device node: {} ({}/{})".format(vcsa, vcsa_major, vcsa_minor))
        return False
    read_vcsa = os.access(vcsa, os.R_OK)
    write_tty = os.access(tty, os.W_OK)
    if not read_vcsa:
        print("No read access to {} - maybe run with sudo?".format(vcsa))
        return False
    if not (tty_major == TTY_MAJOR and tty_minor in TTY_RANGE):
        print("Not a valid TTY device node: {}".format(vcsa))
    if not write_tty:
        print("No write access to {} so cannot set terminal size, maybe run with sudo?".format(tty))
    return True


@click.command()
@click.option('--vcsa', default='/dev/vcsa1', help='Virtual console device (/dev/vcsa[1-63])', show_default=True)
@click.option('--font', default=defaultfont, help='Path to a TrueType font', show_default=True)
@click.option('--size', default=8, help='Font size', show_default=True)
@click.option('--noclear', default=False, is_flag=True, help='Leave display content on exit')
@click.option('--nocursor', default=False, is_flag=True, help="Don't draw the cursor")
@click.option('--sleep', default=0.1, help='Minimum sleep between refreshes', show_default=True)
@click.option('--rows', 'ttyrows', default=None, help='Set TTY rows (--cols required too)')
@click.option('--cols', 'ttycols', default=None, help='Set TTY columns (--rows required too)')
@click.option('--portrait', default=False, is_flag=True, help='Use portrait orientation', show_default=False)
@click.option('--flipx', default=False, is_flag=True, help='Flip X axis (EXPERIMENTAL/BROKEN)', show_default=False)
@click.option('--flipy', default=False, is_flag=True, help='Flip Y axis (EXPERIMENTAL/BROKEN)', show_default=False)
@click.option('--spacing', default=0, help='Line spacing for the text', show_default=True)
def terminal(vcsa, font, size, noclear, nocursor, sleep, ttyrows, ttycols, portrait, flipx, flipy, spacing):
    """Display virtual console on an e-Paper display, exit with Ctrl-C."""
    if not epd:
        exit("Display is not configured, use top-level option '--model', aborting.")

    oldbuff = ''
    oldimage = None
    oldcursor = None

    # handle SIGINT from `systemctl stop` and Ctrl-C
    def sigint_handler(sig, frame):
            print("Exiting by SIGINT...")
	    if not noclear:
		showtext(oldbuff, fill=_WHITE, **textargs)
	    sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)

    # load the font
    if os.path.isfile(font):
        ft = ImageFont.truetype(font, size)
    else:
        error("The font '{}' could not be found, aborting.".format(font))

    # group the various params for readability
    textargs = { 'font': ft, 'size': size, 'portrait': portrait, 'flipx': flipx, 'flipy': flipy, 'spacing': spacing }

    if any([ttyrows,ttycols]) and not all([ttyrows,ttycols]):
        error("You must define both --rows and --cols to change terminal size.")
    if valid_vcsa(vcsa):
        if all([ttyrows, ttycols]):
            set_tty_size(ttydev(vcsa), ttyrows, ttycols)
        print("Started displaying {}, minimum update interval {} s, exit with Ctrl-C".format(vcsa, sleep))
        while True:
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
		buff = ''.join( [ r + '\n' for r in split(buff, cols) ] )
		# do something only if content has changed or cursor was moved
		if buff != oldbuff or cursor != oldcursor:
		    # show new content
		    oldimage = showtext(buff, fill=_BLACK, cursor = cursor, oldimage = oldimage, **textargs)
		    oldbuff = buff
		    oldcursor = cursor
		else:
		    # delay before next update check
		    time.sleep(float(sleep))


if __name__ == '__main__':
    cli.add_command(scrub)
    cli.add_command(terminal)
    cli.add_command(stdin)
    cli()
