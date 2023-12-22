from PIL import Image
import array
import struct
import time

from papertty.drivers.drivers_base import DisplayDriver
from papertty.drivers.drivers_base import GPIO

try:
    import spidev
except ImportError:
    pass
except RuntimeError as e:
    print(str(e))


class IT8951(DisplayDriver):
    """A generic driver for displays that use a IT8951 controller board.

    This class will automatically infer the width and height by querying the
    controller."""

    RST_PIN = 17
    CS_PIN = 8
    BUSY_PIN = 24

    VCOM = 2000

    CMD_GET_DEVICE_INFO = [0x03, 0x02]
    CMD_WRITE_REGISTER = [0x00, 0x11]
    CMD_READ_REGISTER = [0x00, 0x10]
    CMD_DISPLAY_AREA = [0x00, 0x34]
    CMD_VCOM = [0x00, 0x39]
    CMD_LOAD_IMAGE_AREA = [0x00, 0x21]
    CMD_LOAD_IMAGE_END = [0x00, 0x22]

    REG_SYSTEM_BASE = 0
    REG_I80CPCR = REG_SYSTEM_BASE + 0x04

    REG_DISPLAY_BASE = 0x1000
    REG_LUTAFSR = REG_DISPLAY_BASE + 0x224 # LUT Status Reg (status of All LUT Engines)
    REG_UP1SR = REG_DISPLAY_BASE + 0x138 #Update Parameter1 Setting Reg
    REG_BGVR = REG_DISPLAY_BASE + 0x250 #Bitmap (1bpp) image color table

    REG_MEMORY_CONV_BASE_ADDR = 0x0200
    REG_MEMORY_CONV = REG_MEMORY_CONV_BASE_ADDR + 0x0000
    REG_MEMORY_CONV_LISAR = REG_MEMORY_CONV_BASE_ADDR + 0x0008

    ROTATE_0   = 0
    ROTATE_90  = 1
    ROTATE_180 = 2
    ROTATE_270 = 3

    BPP_2 = 0
    BPP_3 = 1
    BPP_4 = 2
    BPP_8 = 3

    LOAD_IMAGE_L_ENDIAN = 0
    LOAD_IMAGE_B_ENDIAN = 1

    # Erases the display and leaves it in a white state regardless of what image
    # data is currently in memory.
    DISPLAY_UPDATE_MODE_INIT = 0
    # A fast non-flashy update mode that can go from any gray scale color to
    # black or white.
    DISPLAY_UPDATE_MODE_DU   = 1
    # A flashy update mode that can go from any gray scale color to any other
    # gray scale color.
    DISPLAY_UPDATE_MODE_GC16 = 2
    # For more documentation on display update modes see the reference document:
    # http://www.waveshare.net/w/upload/c/c4/E-paper-mode-declaration.pdf

    #A2 mode is super fast, but only supports 1bpp, and leaves more
    #artifacts than other display modes.
    DISPLAY_UPDATE_MODE_A2 = 6

    #Colors for 1bpp mode register
    Back_Gray_Val = 0xF0
    Front_Gray_Val = 0x00

    def __init__(self):
        super().__init__()
        self.name = "IT8951"
        self.supports_partial = True
        self.supports_1bpp = True
        self.enable_1bpp = True
        self.align_1bpp_width = 32
        self.align_1bpp_height = 16
        self.supports_multi_draw = True

    def delay_ms(self, delaytime):
        time.sleep(float(delaytime) / 1000.0)

    def spi_write(self, data):
        """Write raw bytes over SPI."""
        self.SPI.writebytes(data)

    def spi_read(self, n):
        """Read n raw bytes over SPI."""
        return self.SPI.readbytes(n)

    def write_command(self, command):
        self.wait_for_ready()
        GPIO.output(self.CS_PIN, GPIO.LOW)
        self.spi_write([0x60, 0x00])
        self.wait_for_ready()
        self.spi_write(command)
        GPIO.output(self.CS_PIN, GPIO.HIGH)

    def write_data_bytes(self, data):
        max_transfer_size = 4096
        self.wait_for_ready()
        GPIO.output(self.CS_PIN, GPIO.LOW)
        self.spi_write([0x00, 0x00])
        self.wait_for_ready()
        for i in range(0, len(data), max_transfer_size):
            self.spi_write(data[i: i + max_transfer_size])
        GPIO.output(self.CS_PIN, GPIO.HIGH)

    def read_bytes(self, n):
        self.wait_for_ready()
        GPIO.output(self.CS_PIN, GPIO.LOW)
        self.spi_write([0x10, 0x00])
        self.wait_for_ready()
        self.spi_write([0x00, 0x00]) # Two bytes of dummy data.
        self.wait_for_ready()
        result = array.array("B", self.spi_read(n))
        GPIO.output(self.CS_PIN, GPIO.HIGH)
        return result

    def write_data_half_word(self, half_word):
        """Writes a half word of data to the controller.

        The standard integer format for passing data to and from the controller
        is little endian 16 bit words.
        """
        self.write_data_bytes([(half_word >> 8) & 0xFF, half_word & 0xFF])

    def read_half_word(self):
        """Reads a half word of from the controller."""
        return struct.unpack(">H", self.read_bytes(2))[0]

    def write_register(self, register_address, value):
        self.write_command(self.CMD_WRITE_REGISTER)
        self.write_data_half_word(register_address)
        self.write_data_half_word(value)

    def read_register(self, register_address):
        self.write_command(self.CMD_READ_REGISTER)
        self.write_data_half_word(register_address)
        return self.read_half_word()

    def wait_for_ready(self):
        """Waits for the busy pin to drop.

        When the busy pin is high the controller is busy and may drop any
        commands that are sent to it."""
        while GPIO.input(self.BUSY_PIN) == 0:
            self.delay_ms(100)

    def wait_for_display_ready(self):
        """Waits for the display to be finished updating.

        It is possible for the controller to be ready for more commands but the
        display to still be refreshing. This will wait for the display to be
        stable."""
        while self.read_register(self.REG_LUTAFSR) != 0:
            self.delay_ms(100)

    def get_vcom(self):
        self.wait_for_ready()
        self.write_command(self.CMD_VCOM)
        self.write_data_half_word(0)
        return self.read_half_word()

    def set_vcom(self, vcom):
        self.write_command(self.CMD_VCOM)
        self.write_data_half_word(1)
        self.write_data_half_word(vcom)

    def fixup_string(self, s):
        result = ""
        for i in range(0, len(s), 2):
            result += "%c%c" % (s[i + 1], s[i])
        null_index = result.find("\0")
        if null_index != -1:
            result = result[0:null_index]
        return result

    def init(self, **kwargs):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.RST_PIN, GPIO.OUT)
        GPIO.setup(self.CS_PIN, GPIO.OUT)
        GPIO.setup(self.BUSY_PIN, GPIO.IN)
        self.SPI = spidev.SpiDev(0, 0)

        mhz = kwargs.get('mhz', None)
        if mhz:
            self.SPI.max_speed_hz = int(mhz * 1000000)
        else:
            self.SPI.max_speed_hz = 2000000
        print("SPI Speed = %.02f Mhz" % (self.SPI.max_speed_hz / 1000.0 / 1000.0))
        
        self.SPI.mode = 0b00

        # It is unclear why this is necessary but it appears to be. The sample
        # code from WaveShare [1] manually controls the CS bin and has its state
        # span multiple SPI operations.
        #
        # [1] https://github.com/waveshare/IT8951
        self.SPI.no_cs = True

        GPIO.output(self.CS_PIN, GPIO.HIGH)

        # Reset the device to its initial state.
        GPIO.output(self.RST_PIN, GPIO.LOW)
        self.delay_ms(500)
        GPIO.output(self.RST_PIN, GPIO.HIGH)
        self.delay_ms(500)

        self.write_command(self.CMD_GET_DEVICE_INFO);

        (
                self.width,
                self.height,
                img_addr_l,
                img_addr_h,
                firmware_version,
                lut_version,
        ) = struct.unpack(">HHHH16s16s", self.read_bytes(40))
        firmware_version = self.fixup_string(firmware_version)
        lut_version = self.fixup_string(lut_version)
        self.img_addr = img_addr_h << 16 | img_addr_l

        self.in_bpp1_mode = False
        self.enable_1bpp = kwargs.get('enable_1bpp', self.enable_1bpp)
        self.supports_a2 = False
        self.enable_a2 = kwargs.get('enable_a2', True)

        #6inch e-Paper HAT(800,600), 6inch HD e-Paper HAT(1448,1072), 6inch HD touch e-Paper HAT(1448,1072)
        if len(lut_version) >= 4 and lut_version[:4] == "M641":

            #A2 mode is 4 instead of 6 for this model
            self.DISPLAY_UPDATE_MODE_A2 = 4

            #This model requires four-byte alignment.
            #Don't enable a2 support until that has been implemented.
            #self.supports_a2 = True

        #9.7inch e-Paper HAT(1200,825)
        elif len(lut_version) >= 4 and lut_version[:4] == "M841":
            self.supports_a2 = True

        #7.8inch e-Paper HAT(1872,1404)
        elif len(lut_version) >= 12 and lut_version[:12] == "M841_TFA2812":
            self.supports_a2 = True

        #10.3inch e-Paper HAT(1872,1404)
        elif len(lut_version) >= 12 and lut_version[:12] == "M841_TFA5210":
            self.supports_a2 = True

        #unknown model
        else:
            #It's PROBABLY safe to turn this to A2 instead of DU, but it would need a suitable test device.
            #ie. A model not listed above.
            #So for now, let's just leave it disabled
            pass

        print("width = %d" % self.width)
        print("height = %d" % self.height)
        print("img_addr = %08x" % self.img_addr)
        print("firmware = %s" % firmware_version)
        print("lut = %s" % lut_version)

        # Ensure that the returned device info looks sane. If it doesn't, then
        # there is little chance that any of the other operations are going to
        # do anything.
        assert self.img_addr != 0
        assert self.width != 0
        assert self.height != 0

        # Set to Enable I80 Packed mode.
        self.write_register(self.REG_I80CPCR, 0x0001)

        vcom = kwargs.get('vcom', None)
        if vcom:
            self.VCOM = vcom
            
        if self.VCOM != self.get_vcom():
            self.set_vcom(self.VCOM)
            print("VCOM = -%.02fV" % (self.get_vcom() / 1000.0))

        # Initialize the display with a blank image.
        self.wait_for_ready()
        self.clear()

        if self.enable_1bpp:
            #Adjust screen size to accommodate bounding in 1bpp mode
            #Do this AFTER clearing the screen
            self.width -= (self.width % self.align_1bpp_width)
            self.height -= (self.height % self.align_1bpp_height)

            print("1bpp support enabled")
            print("adjusted width = %d" % self.width)
            print("adjusted height = %d" % self.height)

    def display_area(self, x, y, w, h, display_mode):
        self.write_command(self.CMD_DISPLAY_AREA)
        self.write_data_half_word(x)
        self.write_data_half_word(y)
        self.write_data_half_word(w)
        self.write_data_half_word(h)
        self.write_data_half_word(display_mode)

    def draw_multi(self, imageArray):

        """This function performs multiple draws in a single panel refresh"""

        #First, calculate the bounds of the panel area which is being refreshed.
        #ie. a rectangle within which all of the images in imageArray would fit.
        smallest_x = -1
        biggest_x = -1
        smallest_y = -1
        biggest_y = -1
        for arrayItem in imageArray:
            left = arrayItem["x"]
            top = arrayItem["y"]
            image = arrayItem["image"]
            right = left + image.width
            bottom = top + image.height
            if left < smallest_x or smallest_x == -1:
                smallest_x = left
            if right > biggest_x or biggest_x == -1:
                biggest_x = right
            if top < smallest_y or smallest_y == -1:
                smallest_y = top
            if bottom > biggest_y or biggest_y == -1:
                biggest_y = bottom
        bbox = (smallest_x, smallest_y, biggest_x, biggest_y)

        #Next, draw each image.
        for i, arrayItem in enumerate(imageArray):
            x = arrayItem["x"]
            y = arrayItem["y"]
            image = arrayItem["image"]
            update_mode_override = None
            isFirst = i == 0
            isLast = i == len(imageArray) - 1
            self.draw(x, y, image, update_mode_override, isFirst, isLast, bbox)

    def draw(self, x, y, image, update_mode_override=None, isFirst=True, isLast=True, bbox=None):
        width = image.size[0]
        height = image.size[1]

        #If this is the first (or only) image to draw, prepare the display.
        if isFirst:
            self.wait_for_display_ready()

        #Set to 4bpp by default
        bpp = 4

        #However, if the right conditions are met, switch to 1bpp mode.
        #I'm not 100% sure that all of these are the exact conditions, but they appear
        #to work consistently during testing.
        #Conditions are:
        #-1bpp mode is enabled in papertty (self.enable_1bpp)
        #-image is black and white (image.mode == "1")
        #-x coordinate is on an expected boundary
        #-image is fullscreen OR width and height are divisible by the expected boundaries
        if self.enable_1bpp and image.mode == "1" and x % self.align_1bpp_width == 0:
            if width == self.width and height == self.height:
                bpp = 1
            elif width % self.align_1bpp_width == 0 and height % self.align_1bpp_height == 0:
                bpp = 1

        #Once we're sure that the panel can handle this image in 1bpp mode, it's time to
        #put the panel in 1bpp mode
        if bpp == 1:

            #Confusingly, 1bpp actually requires the use of the 8bpp flag
            bpp_mode = self.BPP_8

            #If this is the first (or only) image to draw, write the registers.
            if isFirst:

                #If the panel isn't already in 1bpp mode, write these specific commands to the
                #register to put it into 1bpp mode.
                #This is the important bit which actually puts it in 1bpp in spite of the 8bpp flag
                if not self.in_bpp1_mode:
                    self.write_register(self.REG_UP1SR+2, self.read_register(self.REG_UP1SR+2) | (1<<2) )
                    self.in_bpp1_mode = True
                
                #Also write the black and white color table for 1bpp mode
                self.write_register(self.REG_BGVR, (self.Front_Gray_Val<<8) | self.Back_Gray_Val)

        else:
            #If we're not in 1bpp mode, default to 4bpp.
            #In theory we could instead go with 8bpp or 2bpp.
            #But 8bpp would be a waste for a non-color panel.
            #And 2bpp's usefulness seems quite limited as it doesn't add enough levels of gray
            #to be worth the extra bit cost.
            #So 1bpp and 4bpp seem like the best options for now.

            bpp = 4
            bpp_mode = self.BPP_4

            #If this is the first (or only) image to draw, write the registers.
            if isFirst:

                #If the last write was in 1bpp mode, unset that register to take it out of 1bpp mode.
                if self.in_bpp1_mode:
                    self.write_register(self.REG_UP1SR+2, self.read_register(self.REG_UP1SR+2) & ~(1<<2) )
                    self.in_bpp1_mode = False

                #Then write the expected registers for 4bpp mode.
                self.write_register(
                        self.REG_MEMORY_CONV_LISAR + 2, (self.img_addr >> 16) & 0xFFFF)
                self.write_register(self.REG_MEMORY_CONV_LISAR, self.img_addr & 0xFFFF)

        # Define the region being loaded.
        self.write_command(self.CMD_LOAD_IMAGE_AREA)
        self.write_data_half_word(
                (self.LOAD_IMAGE_L_ENDIAN << 8) |
                (bpp_mode << 4) |
                self.ROTATE_0)

        # x and width are set to value//8 if using 1bpp mode.
        self.write_data_half_word((x//8) if bpp == 1 else x)
        self.write_data_half_word(y)
        self.write_data_half_word((width//8) if bpp == 1 else width)
        self.write_data_half_word(height)

        packed_image = self.pack_image(image, bpp)
        self.write_data_bytes(packed_image)
        self.write_command(self.CMD_LOAD_IMAGE_END);

        #If this is the last (or only) image to draw, refresh the panel.
        if isLast:

            if update_mode_override is not None:
                update_mode = update_mode_override
            elif image.mode == "1":
                # Use a faster, non-flashy update mode for pure black and white
                # images.
                if bpp == 1 and self.supports_a2 and self.enable_a2:
                    update_mode = self.DISPLAY_UPDATE_MODE_A2
                else:
                    update_mode = self.DISPLAY_UPDATE_MODE_DU
            else:
                # Use a slower, flashy update mode for gray scale images.
                update_mode = self.DISPLAY_UPDATE_MODE_GC16

            # Blit the image to the display.
            # If bbox has been passed in (eg. if performing multiple draws at once)
            # then we should update that area.
            # Otherwise, refresh the panel based on the image's bounds.
            if bbox:
                (left, top, right, bottom) = bbox
                self.display_area(left, top, right-left, bottom-top, update_mode)
            else:
                self.display_area(x, y, width, height, update_mode)

    def clear(self):
        image = Image.new('1', (self.width, self.height), self.white)
        self.draw(0, 0, image, self.DISPLAY_UPDATE_MODE_INIT)

    def pack_image(self, image, bpp):
        """Packs a PIL image for transfer over SPI to the driver board."""
        if image.mode == '1':
            # B/W pictured can be processed more quickly
            frame_buffer = list(image.getdata())
        else:
            # old packing code for grayscale (VNC)
            bpp = 4
            image_grey = image.convert("L")
            frame_buffer = list(image_grey.getdata())


        #Step is the number of bytes we need to read to create a word.
        #A word is 2 bytes (16 bits) in size.
        #However, the input data we use to create the word will vary
        #in length depending on the bpp.
        #eg. If bpp is 1, that means we only grab 1 bit from each
        #input byte. So we would need 16 bytes to get the needed
        #16 bits.
        #Whereas if bpp is 4, then we grab 4 bits from each byte.
        #So we'd only need to read 4 bytes to get 16 bits.
        step = 16 // bpp

        #A halfstep is how many input bytes we need to read from
        #frame_buffer in order to pack a single output byte
        #into packed_buffer.
        halfstep = step // 2

        #Set the size of packed_buffer to be the length of the
        #frame buffer (total input bytes) divided by a halfstep
        #(input bytes needed per packed byte).
        packed_buffer = [0x00] * (len(frame_buffer) // halfstep)

        #Select the packing function based on which bpp
        #mode we're using.
        if bpp == 1:
            packfn = self.pack_1bpp
        elif bpp == 2:
            packfn = self.pack_2bpp
        else:
            packfn = self.pack_4bpp

        #Step through the frame buffer and pack its bytes
        #into packed_buffer.
        for i in range(0, len(frame_buffer), step):
            packfn(packed_buffer, i // halfstep, frame_buffer[i:i+step])
        return packed_buffer

    def pack_1bpp(self, packed_buffer, i, sixteenBytes):
        """Pack an image in 1bpp format.

        This only works for black and white images.
        This code would look nicer with a loop, but using bitwise operators
        like this is significantly faster. So the ugly code stays ;)

        Bytes are read in reverse order because the driver board assumes all
        data is read in as 16bit ints. So in order to match the endianness,
        every pair of bytes must be swapped.
        """
        packed_buffer[i] = \
            (1 if sixteenBytes[8] else 0) | \
            (2 if sixteenBytes[9] else 0) | \
            (4 if sixteenBytes[10] else 0) | \
            (8 if sixteenBytes[11] else 0) | \
            (16 if sixteenBytes[12] else 0) | \
            (32 if sixteenBytes[13] else 0) | \
            (64 if sixteenBytes[14] else 0) | \
            (128 if sixteenBytes[15] else 0)
        packed_buffer[i+1] = \
            (1 if sixteenBytes[0] else 0) | \
            (2 if sixteenBytes[1] else 0) | \
            (4 if sixteenBytes[2] else 0) | \
            (8 if sixteenBytes[3] else 0) | \
            (16 if sixteenBytes[4] else 0) | \
            (32 if sixteenBytes[5] else 0) | \
            (64 if sixteenBytes[6] else 0) | \
            (128 if sixteenBytes[7] else 0)

    def pack_2bpp(self, packed_buffer, i, eightBytes):
        """Pack an image in 2bpp format.

        The utility of 2bpp format is questionable, as it only works properly
        with GC16 mode. DU mode causes artifacts to remain.
        It seems unlikely that this is a bug in driver_it8951.py given that
        GC16 mode works correctly.

        The waveshare reference code only ever uses GC16 mode with 2bpp, so
        perhaps it's a bug within the IT8951 controller? Regardless, 1bpp is
        faster, and 4bpp works with DU mode. So chances are you'd be better off
        using one of those.

        Bytes are read in reverse order because the driver board assumes all
        data is read in as 16bit ints. So in order to match the endianness,
        every pair of bytes must be swapped.
        """
        packed_buffer[i] = \
            (3 if eightBytes[4] else 0) | \
            (12 if eightBytes[5] else 0) | \
            (48 if eightBytes[6] else 0) | \
            (192 if eightBytes[7] else 0)
        packed_buffer[i+1] = \
            (3 if eightBytes[0] else 0) | \
            (12 if eightBytes[1] else 0) | \
            (48 if eightBytes[2] else 0) | \
            (192 if eightBytes[3] else 0)

    def pack_4bpp(self, packed_buffer, i, fourBytes):
        """Pack an image in 4bpp format.

        Bytes are read in reverse order because the driver board assumes all
        data is read in as 16bit ints. So in order to match the endianness,
        every pair of bytes must be swapped.
        """
        packed_buffer[i] = \
            (15 if fourBytes[2] else 0) | \
            (240 if fourBytes[3] else 0)
        packed_buffer[i+1] = \
            (15 if fourBytes[0] else 0) | \
            (240 if fourBytes[1] else 0)
