#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Colin Nolan, 2020
# Jouko Strömmer, 2018
# Copyright and related rights waived via CC0
# https://creativecommons.org/publicdomain/zero/1.0/legalcode

# As you would expect, use this at your own risk! This code was created
# so you (yes, YOU!) can make it better.
#
# Requires Python 3

# display drivers - note: they are GPL licensed, unlike this file
import papertty.drivers.drivers_base as drivers_base
import papertty.drivers.drivers_partial as drivers_partial
import papertty.drivers.drivers_full as drivers_full
import papertty.drivers.drivers_color as drivers_color
import papertty.drivers.drivers_colordraw as drivers_colordraw
import papertty.drivers.driver_it8951 as driver_it8951
import papertty.drivers.drivers_4in2 as driver_4in2

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

# resource path
RESOURCE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

class PaperTTY:
    """The main class - handles various settings and showing text on the display"""
    defaultfont = os.path.join(RESOURCE_PATH, "tom-thumb.pil")
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
    vcom = None
    cursor = None
    rows = None
    cols = None
    is_truetype = None
    fontfile = None
    enable_a2 = True
    enable_1bpp = True
    mhz = None

    def __init__(self, driver, font=defaultfont, fontsize=defaultsize, partial=None, encoding='utf-8', spacing=0, cursor=None, vcom=None, enable_a2=True, enable_1bpp=True, mhz=None):
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
        self.vcom = vcom
        self.enable_a2 = enable_a2
        self.enable_1bpp = enable_1bpp
        self.mhz = mhz

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
        self.rows = int(rows)
        self.cols = int(cols)
        with open(tty, 'w') as tty:
            size = struct.pack("HHHH", self.rows, self.cols, 0, 0)
            try:
                fcntl.ioctl(tty.fileno(), termios.TIOCSWINSZ, size)
            except OSError:
                print("TTY refused to resize (rows={}, cols={}), continuing anyway.".format(rows, cols))
                print("Try setting a sane size manually.")

    @staticmethod
    def band(bb, xdiv = 8, ydiv = 1):
        """Stretch a bounding box's X coordinates to be divisible by 8,
           otherwise weird artifacts occur as some bits are skipped."""
        #print("Before band: "+str(bb))
        return ( \
            int(bb[0] / xdiv) * xdiv, \
            int(bb[1] / ydiv) * ydiv, \
            int((bb[2] + xdiv - 1) / xdiv) * xdiv, \
            int((bb[3] + ydiv - 1) / ydiv) * ydiv \
        ) if bb else None

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
            self.recalculate_font(font)

        return font

    def recalculate_font(self, font):
        """Load the PIL or TrueType font"""
        # get physical dimensions of font. Take the average width of
        # 1000 M's because oblique fonts a complicated.
        self.font_width = font.getsize('M' * 1000)[0] // 1000
        if 'getmetrics' in dir(font):
            metrics_ascent, metrics_descent = font.getmetrics()
            self.spacing = int(self.spacing) if self.spacing != 'auto' else (metrics_descent - 2)
            print('Setting spacing to {}.'.format(self.spacing))
            # despite what the PIL docs say, ascent appears to be the
            # height of the font, while descent is not, in fact, negative.
            # Couuld use testing with more fonts.
            self.font_height = metrics_ascent + metrics_descent + self.spacing
        else:
            # No autospacing for pil fonts, but they usually don't need it.
            self.spacing = int(self.spacing) if self.spacing != 'auto' else 0
            # pil fonts don't seem to have metrics, but all
            # characters seem to have the same height
            self.font_height = font.getsize('a')[1] + self.spacing

    def init_display(self):
        """Initialize the display - call the driver's init method"""
        self.driver.init(partial=self.partial, vcom=self.vcom, enable_a2=self.enable_a2, enable_1bpp=self.enable_1bpp, mhz=self.mhz)
        self.initialized = True

    def fit(self, portrait=False):
        """Return the maximum columns and rows we can display with this font"""
        width = self.font_width
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

    def showfb(self, fb_num, rotate=None, invert=False, sleep=1, full_interval=100):
        """Render the framebuffer - basically a copy-paste of showvnc at this point"""
        def _get_fb_info(fb_num):
            config_dir = "/sys/class/graphics/fb%d/" % fb_num
            size = None
            bpp = None
            with open(config_dir + "/virtual_size", "r") as f:
                size = tuple([int(t) for t in f.read().strip().split(",")])
            with open(config_dir + "/bits_per_pixel", "r") as f:
                bpp = int(f.read().strip())
            return (size,bpp)

        def _get_fb_img(fb_num):
            size, bpp = _get_fb_info(fb_num)
            with open("/dev/fb%d" % fb_num, "rb") as f:
                mode = "BGRX" if bpp == 32 else "BGR;16"
                return Image.frombytes("RGB", size, f.read(), "raw", mode).convert("L")

        previous_fb_img = None
        diff_bbox = None
        # number of updates; when it's 0, do a full refresh
        updates = 0
        while True:
            new_fb_img = _get_fb_img(fb_num)
            # apply rotation if any
            if rotate:
                new_fb_img = new_fb_img.rotate(rotate, expand=True)
            # apply invert
            if invert:
                new_fb_img = ImageOps.invert(new_fb_img)
            # rescale image if needed
            if new_fb_img.size != (self.driver.width, self.driver.height):
                new_fb_img = new_fb_img.resize((self.driver.width, self.driver.height))
            # if at least two frames have been processed, get a bounding box of their difference region
            if new_fb_img and previous_fb_img:
                diff_bbox = self.band(self.img_diff(new_fb_img, previous_fb_img))
            # frames differ, so we should update the display
            if diff_bbox:
                # increment update counter
                updates = (updates + 1) % full_interval
                # if partial update is supported and it's not time for a full refresh,
                # draw just the different region
                if updates > 0 and (self.driver.supports_partial and self.partial):
                    print("partial ({}): {}".format(updates, diff_bbox))
                    self.driver.draw(diff_bbox[0], diff_bbox[1], new_fb_img.crop(diff_bbox))
                # if partial update is not possible or desired, do a full refresh
                else:
                    print("full ({}): {}".format(updates, new_fb_img.size))
                    old_partial = self.partial
                    self.partial = False
                    self.driver.draw(0, 0, new_fb_img)
                    self.partial = old_partial
            # otherwise this is the first frame, so run a full refresh to get things going
            else:
                if updates == 0:
                    updates = (updates + 1) % full_interval
                    print("initial ({}): {}".format(updates, new_fb_img.size))
                    self.driver.draw(0, 0, new_fb_img)
            previous_fb_img = new_fb_img.copy()
            time.sleep(float(sleep))



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

    def showtext(self, text, fill, cursor=None, portrait=False, flipx=False, flipy=False, oldimage=None, oldtext=None, oldcursor=None):
        """Draw a string on the screen"""
        if self.ready():
            
            #If partial updates are supported, run partialdraw_showtext() instead
            #as it should be more efficient.
            if self.driver.supports_partial and self.partial:
                
                if oldtext is None:
                    oldtext = ""

                return self.partialdraw_showtext(text=text, fill=fill, cursor=cursor, portrait=portrait, flipx=flipx, flipy=flipy, oldimage=oldimage, oldtext=oldtext, oldcursor=oldcursor)

            # set order of h, w according to orientation
            image = Image.new('1', (self.driver.width, self.driver.height) if portrait else (
                self.driver.height, self.driver.width),
                              self.white)
            # create the Draw object and draw the text
            draw = ImageDraw.Draw(image)

            # Split the text up by line and display each line individually.
            # This is a workaround for a font height bug in PIL
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if line:
                    y = i * self.font_height
                    draw.text((0, y), line, font=self.font, fill=fill, spacing=self.spacing)

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
                if self.driver.supports_1bpp and self.driver.enable_1bpp:
                    xdiv = self.driver.align_1bpp_width
                    ydiv = self.driver.align_1bpp_height
                else:
                    xdiv = 8
                    ydiv = 1
                diff_bbox = self.band(self.img_diff(image, oldimage), xdiv=xdiv, ydiv=ydiv)
                # crop the altered region and draw it on the display
                if diff_bbox:
                    self.driver.draw(diff_bbox[0], diff_bbox[1], image.crop(diff_bbox))
            else:
                # if no previous image, draw the entire display
                self.driver.draw(0, 0, image)
            return image
        else:
            self.error("Display not ready")



    def partialdraw_showtext(self, text, fill, cursor, portrait, flipx, flipy, oldimage, oldtext, oldcursor):

        """Draw a string on the screen one line at a time.
           This function serves as an alternative to showtext() and aims to be more efficient
           by comparing string values instead of diffing images.
           It is especially fast for any drivers with self.supports_multi_draw = True.
           (supports_multi_draw is currently only supported by the IT8951 driver)
        """

        #First, grab oldtext (the text from the previous render) and text (the text from
        #the current render), then split them up based on a newline delimiter.
        #This is so we can compare the previous state of the text to the current state
        #of the text line by line and only redraw the lines which have actually changed.
        oldlines = oldtext.split('\n')
        newlines = text.split('\n')


        #Use the font height as the height for other measurements, such as row height
        height = self.font_height

        #Figure out the width and height of the panel after rotation.
        #These values are used when determining the maximum allowed size of a row of text,
        #when figuring out coordinates, and so on.
        driverHeight = self.driver.height if portrait else self.driver.width
        driverWidth = self.driver.width if portrait else self.driver.height
        
        #First, run through each row and build a list of strings to potentially draw
        changedLines = self.partialdraw_get_changed_lines(cursor, oldcursor, oldlines, newlines)


        #If this panel doesn't support multiple draws in a single refresh, then we
        #are probably better off merging the individual lines of text into a single
        #block and drawing that instead.
        #This is because of the overhead involved with each individual write to the
        #GPIO pins, so it can be faster to do one big write instead of two small writes.
        #
        #There's no strict rule of which is faster.
        #It depends on the speed of the machine (eg. rpi zero vs rpi 4b) and the speed
        #of the panel refresh.
        #
        #The value of maxRedraw should probably always be either 1 or 2.
        if not self.driver.supports_multi_draw:
            maxRedraw = 1
            blocks = self.partialdraw_get_text_blocks(changedLines)
            self.partialdraw_merge_text_blocks(blocks, maxRedraw, changedLines)
        

        #For each line in `changedLines`, figure out its coordinates and other information
        #needed for drawing.
        linesToDraw = self.partialdraw_get_lines_to_draw(changedLines, height, flipy, driverHeight)
        

        #Take those lines and turn them into actual images, performing all necessary
        #rotation, coordinate adjustments, etc.
        imagesToDraw = self.partialdraw_get_images_to_draw(linesToDraw, cursor, oldcursor, height, fill, flipx, flipy, driverWidth)


        #If oldimage is defined, update it by drawing the new frames onto it.
        #If not, create a new full-screen image.
        #In either case, don't actually draw the fullscreen image.
        #We're building it to a) return a full-screen image as the return value for
        #compatibility with other papertty functions and b) perform cropping for
        #1bpp alignment.
        if not oldimage:
            oldimage = Image.new('1', (driverWidth, driverHeight), self.white)
        

        #Array of bounded images to pass through to draw_multi if the driver
        #supports it via driver.supports_multi_draw
        imageArray = []


        #For each image we want to draw, paste the image onto the fullscreen image (oldimage).
        #Then build a bbox and band the image coordinates we required by the board
        #and bpp setting.
        #Finally, either draw the image immediately, or put it in imageArray so it can be
        #drawn in bulk.
        for arr in imagesToDraw:
            oldimage.paste(arr["image"], (arr["x"], arr["y"])) #for the return data

            diff_bbox = ( \
                arr["x"], \
                arr["y"], \
                arr["x"] + arr["image"].width, \
                arr["y"] + arr["image"].height \
            )
            if self.driver.supports_1bpp and self.driver.enable_1bpp:
                xdiv = self.driver.align_1bpp_width
                ydiv = self.driver.align_1bpp_height
            else:
                xdiv = 8
                ydiv = 1

            #If the screen is rotated, then switch the bounds around.
            #This is because we crop BEFORE rotating, so doing it here
            #with switched values saves us from needing to crop a second
            #time.
            if not portrait:
                xdiv, ydiv = ydiv, xdiv

            bbox = self.band(diff_bbox, xdiv=xdiv, ydiv=ydiv)

            croppedImage = oldimage.crop(bbox)
            x, y = bbox[0], bbox[1]

            #Rotate the image and coordinates
            if not portrait:
                croppedImage = croppedImage.rotate(90, expand=True)
                x, y = y, driverWidth - x - croppedImage.height

            #If multi_draw is supported, add the image to an array so they can
            #all be sent through at once.
            #Otherwise, just draw the image immediately.
            if self.driver.supports_multi_draw:
                imageArray.append({"x":x, "y":y, "image":croppedImage})
            else:
                self.driver.draw(x, y, croppedImage)


        if self.driver.supports_multi_draw:
            self.driver.draw_multi(imageArray)


        return oldimage
    
    def partialdraw_get_changed_lines(self, cursor, oldcursor, oldlines, newlines):

        """This function compares two strings arrays, oldlines and newlines, and
            figures out which lines of text in those arrays are different.
            It also takes cursor position into consideration when figuring out if
            the text has "changed" or not."""

        #List of lines of text which have changed
        changedLines = []

        for i in range(self.rows):
            
            newval = newlines[i] if i < len(newlines) else ''
            oldval = oldlines[i] if i < len(oldlines) else ''

            #Use these variables to check if the cursor has moved
            cursorIsOnThisLine = False
            cursorWasOnThisLine = False
            cursorMovedHorizontally = False

            if cursor and self.cursor:
                cur_y = cursor[1]
                if cur_y == i:
                    cursorIsOnThisLine = True

            if oldcursor:
                cur_y = oldcursor[1]
                if cur_y == i:
                    cursorWasOnThisLine = True

            #If the cursor was on this line last render, and it's still on this line
            #this render, then we need to check the x axis (cursor[0]) and the text
            #to judge whether the cursor needs drawing or not.
            #If it doesn't need drawing, set both variables to false.
            if cursorIsOnThisLine and cursorWasOnThisLine:
                if oldcursor[0] != cursor[0]:
                    cursorMovedHorizontally = True
                elif oldval == newval:
                    cursorIsOnThisLine = False
                    cursorWasOnThisLine = False

            #Draw this line if either the cursor has moved, or the text has changed
            drawThisLine = cursorMovedHorizontally or cursorIsOnThisLine != cursorWasOnThisLine or oldval != newval

            lineToDraw = {
                "drawThisLine":drawThisLine,
                "newval":newval,
                "cursorIsOnThisLine":cursorIsOnThisLine,
                "oldval":oldval,
                "cursorWasOnThisLine":cursorWasOnThisLine
            }
            changedLines.append(lineToDraw)

        return changedLines

    def partialdraw_get_text_blocks(self, changedLines):

        """This function takes the result of partialdraw_get_changed_lines and
            groups consecutive lines together in order to create blocks of text."""

        #Array of grouped text blocks
        blocks = []

        #Used in the loop to keep track of whether the previous line was flagged for
        #drawing or not
        drawLastLine = False
        
        for i, arr in enumerate(changedLines):
            
            drawThisLine = arr["drawThisLine"]

            #If this line is to be drawn, and so was the previous line, group them
            #together in the same block.
            #If this line is to be drawn, but the previous one wasn't, then start a
            #new block instead.
            if drawThisLine:
                if drawLastLine:
                    blocks[-1]["end"] = i
                else:
                    blocks.append({"start":i, "end":i})

            drawLastLine = drawThisLine

        return blocks

    def partialdraw_merge_text_blocks(self, blocks, maxRedraw, changedLines):

        """This function takes the result of partialdraw_get_text_blocks
            and merges the text blocks together until the total number of block
            does not exceed `maxRedraw`."""

        #If the number of blocks to draw is more than we want to redraw separately
        #(`maxRedraw`), then batch them together.
        #We do this by setting `drawThisLine` to True for the lines in between separate
        #blocks.
        #This causes the "block" to be made bigger artificially by drawing lines we
        #don't need to, which in turn leverages the "append" behavior in the drawing loop.
        #
        #This sounds counter-productive, but it actually speeds things up in cases where
        #we can't perform multiple independent writes to the board in a single refresh.
        #This is because each individual write to SPI incurs overhead, and each individual
        #write also triggers a redraw by the e-ink panel which has its own delay.
        #So if we're looking to do multiple small writes, sometimes it's preferable to do one
        #bigger write instead.

        if len(blocks) > maxRedraw:

            #First, iterate through each block and figure out how big the gap is between
            #that block and the next block.
            #Then when we've found the smallest gap, merge those two blocks together.
            #Repeat this process until the number of blocks does not exceed `maxRedraw`.
            #The smallest gap is used as the criteria for merging because a "gap" between
            #blocks is a section of lines which otherwise don't need to be drawn.
            #Any of those lines we do draw is extra overhead.
            #So to minimize that extra overhead, we make a point of looking for the
            #smallest gaps.

            while len(blocks) > maxRedraw:
                smallestGap = -1
                smallestGapIndex = -1
                for i in range(len(blocks) - 1):
                    thisBlock = blocks[i]
                    nextBlock = blocks[i+1]
                    thisBlockEnd = thisBlock["end"]
                    nextBlockStart = nextBlock["start"]
                    gap = nextBlockStart - thisBlockEnd
                    if smallestGap == -1 or gap < smallestGap:
                        smallestGap = gap
                        smallestGapIndex = i
                blockToMerge = blocks.pop(smallestGapIndex+1)
                blocks[smallestGapIndex]["end"] = blockToMerge["end"]

            #Next, iterate through all of the lines of text we were going to draw
            #(or not draw) and reassess whether to draw them or not based on whether
            #they're in one of the calculated text blocks.
            #Setting drawThisLine to True means that line of text will be
            #flagged for merging in the drawing loop elsewhere in the code.

            for i, arr in enumerate(changedLines):
                for block in blocks:
                    if i >= block["start"] and i <= block["end"]:
                        changedLines[i]["drawThisLine"] = True
                        break

    def partialdraw_get_lines_to_draw(self, changedLines, height, flipy, driverHeight):

        """This function takes the result of partialdraw_get_changed_lines and
            figures out where and how to draw the line.
            This includes flagging the line of text as one which should be merged,
            figuring out which characters in the text line have actually changed,
            and other information useful for the text drawing loop."""
        
        #`append` is a flag to indicate that the current line should be merged with the
        #preceding line instead of being drawn separately.
        #This is part of a performance optimization; it's less expensive to draw a double-line
        #height image than it is to draw two single-line height images.
        append = False

        linesToDraw = []

        for i, arr in enumerate(changedLines):
            drawThisLine = arr["drawThisLine"]
            newval = arr["newval"]
            cursorIsOnThisLine = arr["cursorIsOnThisLine"]
            oldval = arr["oldval"]
            cursorWasOnThisLine = arr["cursorWasOnThisLine"]

            #Calculate the y coordinate based on the row number and font height.
            #If flipy is set, count the rows backwards, since we want to draw from
            #the "end" (which flipy moves to the start of the screen) instead.
            if flipy:

                #Calculate the gap between the last row and the edge of the screen,
                #then add it to y.
                #This is because we want the gap between the "last" row (which,
                #when flipped, becomes the first row) to be at the bottom of the screen,
                #not the top.
                offset_y = driverHeight % self.font_height
                
                #We want to count backwards from 1 row BEFORE self.rows, since that's
                #the maximum index we would actually draw at when counting forwards.
                maxRowIndex = self.rows - 1

                y = (maxRowIndex - i) * height
                y += offset_y
            else:
                y = i * height

            if not drawThisLine:

                #If the cursor hasn't moved to/from this line and the text hasn't changed,
                #then don't add this line to the `linesToDraw` array.
                #Just set append to false, since we aren't drawing this line and thus can't
                #append to it
                append = False

            else:
                firstChanged = -1
                lastChanged = 0
                oldlen = len(oldval)
                newlen = len(newval)
                smallerLen = min(oldlen, newlen)

                #Iterate through the old text value and the new text value char by char
                #in order to find the first non-matching character.
                #Or, if either string is empty, set firstChanged to 0.
                if oldlen == 0 or newlen == 0:
                    firstChanged = 0
                else:
                    for j in range(smallerLen):
                        oldChar = oldval[j]
                        newChar = newval[j]
                        if oldChar != newChar:
                            firstChanged = j
                            break

                #firstChanged might not be set if one line completely encapsulates the other.
                #eg. if the line changed from "test" to "testing" then they are identical
                #until the last char of the old string, so firstChanged would never be set.
                #In that case, set firstChanged to be the final character of whichever line
                #is shorter.
                if firstChanged == -1:
                    firstChanged = min(oldlen, newlen) - 1

                #Next, try to find the LAST non-matching character.
                #If the line length has changed, then the last char won't match, so just
                #set it to that. Otherwise, iterate char by char again.
                if newlen != oldlen:
                    lastChanged = max(oldlen, newlen) - 1
                else:
                    for j in range(newlen):
                        oldChar = oldval[j]
                        newChar = newval[j]
                        if oldChar != newChar:
                            lastChanged = j

                #Set the x coordinate to start at `firstChanged` since we won't draw
                #anything before that.
                x = firstChanged * self.font_width

                #`subsequentLines` is a list of lines which come after the current line,
                #but should be drawn in the same image as this line.
                #This is so we can draw consecutive altered lines into a single image and
                #minimize the number of SPI writes.
                subsequentLines = []

                lineToDraw = {
                    "x":x,
                    "y":y,
                    "newval":newval,
                    "cursorIsOnThisLine":cursorIsOnThisLine,
                    "subsequentLines":subsequentLines,
                    "firstChanged":firstChanged,
                    "lastChanged":lastChanged,
                    "cursorWasOnThisLine":cursorWasOnThisLine
                }

                #If append is true, that means this line and the previous line were both altered.
                #So we're going to take the current line and append it to the previous line and
                #draw them together.
                if append:

                    lastIndex = len(linesToDraw) - 1
                    linesToDraw[lastIndex]["subsequentLines"].append(lineToDraw)

                else:

                    linesToDraw.append(lineToDraw)
                    append = True

        return linesToDraw

    def partialdraw_get_images_to_draw(self, linesToDraw, cursor, oldcursor, height, fill, flipx, flipy, driverWidth):

        """This function takes the result of partialdraw_get_lines_to_draw and turns
            each line into an image. It takes care of rotation, adjusting the
            coordinates, and so on."""

        #List of images (lines of text) to draw
        imagesToDraw = []
        
        for i, arr in enumerate(linesToDraw):

            #Grab the current line and subsequent lines, then put them all in a list together
            chunks = [arr]
            for line in arr["subsequentLines"]:
                chunks.append(line)

            #Run the chunks of text through the partialdraw_get_indexes_from_chunks function.
            #This will tell us the first and last character indexes to draw.
            #TODO: if the font isn't monospace, this should just cover the entire line
            (smallestStartIndex, biggestEndIndex) = self.partialdraw_get_indexes_from_chunks(chunks, cursor, oldcursor)

            #Calculate the starting x coordinate (smallest_x) and the ending x coordinate
            #(biggest_x) of the block.
            smallest_x = smallestStartIndex * self.font_width
            biggest_x = biggestEndIndex * self.font_width

            #For each text chunk, reduce its length based on the chars we want to draw.
            for chunk in chunks:
                chunk["newval"] = chunk["newval"][smallestStartIndex:biggestEndIndex+1]

            #Calculate the image width based on how many chars have changed.
            #eg. If the text changed from "test" to "testing", then 3 chars have changed.
            #So the image width will be 3 x font_width.
            diffIndex = biggestEndIndex - smallestStartIndex
            diffRows = diffIndex + 1
            rowWidth = diffRows * self.font_width

            #Line height doesn't change based on orientation, since image.rotate will
            #resize as needed.
            lineHeight = height

            #Calculate the row height by multiplying the line height by the number of chunks
            rowHeight = lineHeight * len(chunks)

            #Draw the image
            image = self.partialdraw_build_image(rowWidth, rowHeight, chunks, height, fill, cursor, smallestStartIndex)

            #Flip the image, if needed.
            #But do NOT rotate it here.
            #Rotation is handled later in the process to simplify coordinate translation.
            if flipx:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            if flipy:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            
            #Figure out where to draw the image based on either the first or last
            #chunk's coordinates
            if flipy:
                chunk = chunks[-1]
            else:
                chunk = chunks[0]

            offset_x = 0 #driverWidth % self.font_width
            y = chunk["y"]

            #smallest_x is the x coordinate of the start of the changed area.
            #So set x to be smallest_x if flipx is turned off.
            #If flipx is turned on, then calculate the x coordinate based on
            #the panel width, image width, etc.
            if flipx:
                x = driverWidth - image.width + offset_x - smallest_x
            else:
                x = smallest_x

            #Add this image to the list of images to draw
            imagesToDraw.append({"x":x, "y":y, "image":image})

        return imagesToDraw

    def partialdraw_get_indexes_from_chunks(self, chunks, cursor, oldcursor):

        """Calculates the starting and ending character indexes of a text block.
            eg. If chunk[0] only changes from characters 0-4, but chunk[1] changed
            from characters 3-6, then we would want to know the first changed
            character (0) and last changed character (6)."""
        
        smallestStartIndex = -1
        biggestEndIndex = 0

        for chunk in chunks:
            startIndex = chunk["firstChanged"]
            endIndex = chunk["lastChanged"]

            #Don't bother checking lines where nothing has changed.
            #This could be because the line is part of a block update.
            #So it hasn't changed, but needs to be redrawn anyway.
            if startIndex == endIndex:
                pass
            if startIndex < smallestStartIndex or smallestStartIndex == -1:
                smallestStartIndex = startIndex
            if endIndex > biggestEndIndex:
                biggestEndIndex = endIndex

        #If the cursor has moved, make sure it is drawn
        for chunk in chunks:
            cursorIsOnThisLine = chunk["cursorIsOnThisLine"]
            cursorWasOnThisLine = chunk["cursorWasOnThisLine"]

            #If the cursor both was and still is on this line, it may have moved horizontally.
            #Check if x coordinates match.
            #If they don't match, then the cursor has moved and needs to be redrawn.
            #In which case we should adjust the smallest/biggest index of the text
            #redraw to include the cursor.
            if cursorIsOnThisLine and cursorWasOnThisLine:
                cur_x = cursor[0]
                old_x = oldcursor[0]
                if cur_x != old_x:
                    smaller_x = min(cur_x, old_x)
                    bigger_x = max(cur_x, old_x)
                    if smallestStartIndex == -1 or smaller_x < smallestStartIndex:
                        smallestStartIndex = smaller_x
                    if bigger_x > biggestEndIndex:
                        biggestEndIndex = bigger_x

            #If the cursor is now on a different line than it was before, and it is/was on this
            #particular line, then we need to make sure the draw includes the index where the
            #cursor is/was.
            if cursorIsOnThisLine != cursorWasOnThisLine:
                if cursorIsOnThisLine:
                    cur_x = cursor[0]
                else:
                    cur_x = oldcursor[0]
                if smallestStartIndex == -1 or cur_x < smallestStartIndex:
                    smallestStartIndex = cur_x
                if cur_x > biggestEndIndex:
                    biggestEndIndex = cur_x

        return (smallestStartIndex, biggestEndIndex)

    def partialdraw_build_image(self, rowWidth, rowHeight, chunks, height, fill, cursor, smallestStartIndex):

        """Builds an image based on the chunks of text and size parameters passed in.
            Also draws the cursor, if needed."""


        #First, create an image with the expected dimensions.
        image = Image.new('1', (rowWidth, rowHeight), self.white)


        #Then get the ImageDraw object so we can actually draw on the image.
        draw = ImageDraw.Draw(image)


        #For each chunk, draw the text and possibly the cursor
        for j, chunk in enumerate(chunks):
            x = 0
            y = j * height
            newval = chunk["newval"]
            cursorIsOnThisLine = chunk["cursorIsOnThisLine"]

            draw.text((x, y), newval, font=self.font, fill=fill, spacing=self.spacing)

            #Draw the cursor, if it's on this line
            if cursorIsOnThisLine:

                #Adjust cursor's coordinate so they're relative to the text chunk's position
                cursor_x = cursor[0] - smallestStartIndex
                cursor_y = j
                
                newcursor = (cursor_x, cursor_y, cursor[2])
                if self.cursor == 'block':
                    image = self.draw_block_cursor(newcursor, image)
                else:
                    self.draw_line_cursor(newcursor, draw)

        return image

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

                  drivers_full.EPD2in7, drivers_full.EPD3in7, drivers_full.EPD7in5,
                  drivers_color.EPD7in5b_V2, drivers_full.EPD7in5v2,

                  drivers_color.EPD4in2b, drivers_color.EPD7in5b,
                  drivers_color.EPD5in83, drivers_color.EPD5in83b,
                  drivers_color.EPD5in65f,

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


def display_image(driver, image, stretch=False, no_resize=False, fill_color="white", rotate=None, mirror=None, flip=None):
    """
    Display the given image using the given driver and options.
    :param driver: device driver (subclass of `WaveshareEPD`)
    :param image: image data to display
    :param stretch: whether to stretch the image so that it fills the screen in both dimentions
    :param no_resize: whether the image should not be resized if it does not fit the screen (will raise `RuntimeError`
    if image is too large)
    :param fill_color: colour to fill space when image is resized but one dimension does not fill the screen
    :param rotate: rotate the image by arbitrary degrees
    :param mirror: flip the image horizontally
    :param flip: flip the image vertically
    :return: the image that was rendered
    """
    if stretch and no_resize:
        raise ValueError('Cannot set "no-resize" with "stretch"')

    if mirror:
        image = ImageOps.mirror(image)
    if flip:
        image = ImageOps.flip(image)
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor=fill_color)
        
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
@click.option('--stretch', default=False, is_flag=True, show_default=True,
              help='Stretch image so that it fills the entire screen (may distort your image!)')
@click.option('--no-resize', default=False, is_flag=True, show_default=True,
              help='Do not resize image to fit the screen (an error will occur if the image is too large!)')
@click.option('--fill-color', default='white', help='Colour to pad image with', show_default=True)
@click.option('--mirror', default=False, is_flag=True, help='Mirror horizontally', show_default=True)
@click.option('--flip', default=False, is_flag=True, help='Mirror vertically', show_default=True)
@click.option('--rotate', default=0, help='Rotate the image by N degrees', show_default=True, type=float)
@click.pass_obj
def image(settings, image_location, stretch, no_resize, fill_color, mirror, flip, rotate):
    """ Display an image """
    if image_location is None or image_location == '-':
        # XXX: logging to stdout, in line with the rest of this project
        print('Reading image data from stdin... (set "--image" to load an image from a given file path)')
        image_data = BytesIO(sys.stdin.buffer.read())
        image = Image.open(image_data)
    else:
        image = Image.open(image_location)
    
    #Disable 1bpp and a2 by default if not using terminal mode
    settings.args['enable_a2'] = False
    settings.args['enable_1bpp'] = False

    ptty = settings.get_init_tty()
    display_image(ptty.driver, image, stretch=stretch, no_resize=no_resize, fill_color=fill_color, rotate=rotate, mirror=mirror, flip=flip)


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
    """Display a VNC desktop"""
    
    #Disable 1bpp and a2 by default if not using terminal mode
    settings.args['enable_a2'] = False
    settings.args['enable_1bpp'] = False

    ptty = settings.get_init_tty()
    ptty.showvnc(host, display, password, int(rotate) if rotate else None, invert, sleep, fullevery)


@click.command()
@click.option('--fb-num', default="0", help="Framebuffer to display (/dev/fbX)", show_default=True)
@click.option('--rotate', default=None, help="Rotate screen (90 / 180 / 270)")
@click.option('--invert', default=False, is_flag=True, help="Invert colors")
@click.option('--sleep', default=1, show_default=True, help="Refresh interval (s)", type=float)
@click.option('--fullevery', default=50, show_default=True, help="# of partial updates between full updates")
@click.pass_obj
def fb(settings, fb_num, rotate, invert, sleep, fullevery):
    """Display the framebuffer"""
    ptty = settings.get_init_tty()
    ptty.showfb(int(fb_num), int(rotate) if rotate else None, invert, sleep, fullevery)


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
@click.option('--vcom', default=None, help='VCOM as positive value x 1000. eg. 1460 = -1.46V')
@click.option('--disable_a2', is_flag=True, default=False, help='Disable fast A2 panel refresh for black and white images')
@click.option('--disable_1bpp', is_flag=True, default=False, help='Disable fast 1bpp mode')
@click.option('--mhz', default=None, help='Set SPI speed in MHz')
@click.pass_obj
def terminal(settings, vcsa, font, fontsize, noclear, nocursor, cursor, sleep, ttyrows, ttycols, portrait, flipx, flipy,
             spacing, apply_scrub, autofit, attributes, interactive, vcom, disable_a2, disable_1bpp, mhz):
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

    if vcom:
        vcom = int(vcom)
        if vcom <= 0:
            print("VCOM should be a positive number. It will be converted automatically. eg. For a value of -1.46V, set VCOM to 1460")
        settings.args['vcom'] = vcom
    
    settings.args['enable_a2'] = not disable_a2
    settings.args['enable_1bpp'] = not disable_1bpp
    
    if mhz:
        mhz = float(mhz)
        if mhz < 0:
            print("SPI speed must be greater than 0")
            sys.exit(1)
        elif mhz > 1000:
            print("SPI speed is measured in MHz. It should be much lower than the value entered. Did you enter the speed in Hz by mistake?")
            sys.exit(1)
        else:
            settings.args['mhz'] = mhz

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
                        ptty.recalculate_font(ptty.font)
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
                        ptty.driver.init(partial=False, vcom=self.vcom, enable_a2=self.enable_a2, enable_1bpp=self.enable_1bpp, mhz=self.mhz)
                        ptty.driver.draw(0, 0, oldimage)
                        ptty.driver.reset()
                        ptty.driver.init(partial=ptty.partial, vcom=self.vcom, enable_a2=self.enable_a2, enable_1bpp=self.enable_1bpp, mhz=self.mhz)

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
                                                oldtext=oldbuff,
                                                oldcursor=oldcursor,
                                                **textargs)
                        oldbuff = buff
                        oldcursor = cursor
                    else:
                        # delay before next update check
                        time.sleep(float(sleep))


# add all the CLI commands
cli.add_command(scrub)
cli.add_command(terminal)
cli.add_command(stdin)
cli.add_command(image)
cli.add_command(vnc)
cli.add_command(fb)
cli.add_command(list_drivers)


if __name__ == '__main__':
    cli()
