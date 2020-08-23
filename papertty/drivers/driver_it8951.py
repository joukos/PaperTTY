from PIL import Image
import array
import struct
import time

from papertty.drivers.drivers_base import DisplayDriver

try:
    import spidev
    import RPi.GPIO as GPIO
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

    def __init__(self):
        super().__init__()
        self.name = "IT8951"
        self.supports_partial = True

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
        self.SPI.max_speed_hz = 2000000
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

        if self.VCOM != self.get_vcom():
            self.set_vcom(self.VCOM)
            print("VCOM = -%.02fV" % (self.get_vcom() / 1000.0))

        # Initialize the display with a blank image.
        self.wait_for_ready()
        image = Image.new("L", (self.width, self.height), 0x255)
        self.draw(0, 0, image, self.DISPLAY_UPDATE_MODE_INIT)

    def display_area(self, x, y, w, h, display_mode):
        self.write_command(self.CMD_DISPLAY_AREA)
        self.write_data_half_word(x)
        self.write_data_half_word(y)
        self.write_data_half_word(w)
        self.write_data_half_word(h)
        self.write_data_half_word(display_mode)

    def draw(self, x, y, image, update_mode_override=None):
        width = image.size[0]
        height = image.size[1]

        self.wait_for_display_ready()

        self.write_register(
                self.REG_MEMORY_CONV_LISAR + 2, (self.img_addr >> 16) & 0xFFFF)
        self.write_register(self.REG_MEMORY_CONV_LISAR, self.img_addr & 0xFFFF)

        # Define the region being loaded.
        self.write_command(self.CMD_LOAD_IMAGE_AREA)
        self.write_data_half_word(
                (self.LOAD_IMAGE_L_ENDIAN << 8) |
                (self.BPP_4 << 4) |
                self.ROTATE_0)
        self.write_data_half_word(x)
        self.write_data_half_word(y)
        self.write_data_half_word(width)
        self.write_data_half_word(height)

        packed_image = self.pack_image(image)
        self.write_data_bytes(packed_image)
        self.write_command(self.CMD_LOAD_IMAGE_END);

        if update_mode_override is not None:
            update_mode = update_mode_override
        elif image.mode == "1":
            # Use a faster, non-flashy update mode for pure black and white
            # images.
            update_mode = self.DISPLAY_UPDATE_MODE_DU
        else:
            # Use a slower, flashy update mode for gray scale images.
            update_mode = self.DISPLAY_UPDATE_MODE_GC16
        # Blit the image to the display
        self.display_area(x, y, width, height, update_mode)

    def clear(self):
        image = Image.new('1', (self.width, self.height), self.white)
        self.draw(0, 0, image, self.DISPLAY_UPDATE_MODE_INIT)

    def pack_image(self, image):
        """Packs a PIL image for transfer over SPI to the driver board."""
        if image.mode == '1':
            # B/W pictured can be processed more quickly
            frame_buffer = list(image.getdata())

            # For now, only 4 bit packing is supported. Theoretically we could
            # achieve a transfer speed up by using 2 bit packing for black and white
            # images. However, 2bpp doesn't seem to play well with the DU rendering
            # mode.
            packed_buffer = []
            # The driver board assumes all data is read in as 16bit ints. To match
            # the endianness every pair of bytes must be swapped.
            # The image is always padded to a multiple of 8, so we can safely go in steps of 4.
            for i in range(0, len(frame_buffer), 4):
                if frame_buffer[i + 2] and frame_buffer[i + 3]:
                    packed_buffer += [0xFF]
                elif frame_buffer[i + 2]:
                    packed_buffer += [0x0F]
                elif frame_buffer[i + 3]:
                    packed_buffer += [0xF0]
                else:
                    packed_buffer += [0]

                if frame_buffer[i] and frame_buffer[i + 1]:
                    packed_buffer += [0xFF]
                elif frame_buffer[i]:
                    packed_buffer += [0x0F]
                elif frame_buffer[i + 1]:
                    packed_buffer += [0xF0]
                else:
                    packed_buffer += [0]
            return packed_buffer
        else:
            # old packing code for grayscale (VNC)
            image_grey = image.convert("L")
            frame_buffer = list(image_grey.getdata())

            # For now, only 4 bit packing is supported. Theoretically we could
            # achieve a transfer speed up by using 2 bit packing for black and white
            # images. However, 2bpp doesn't seem to play well with the DU rendering
            # mode.
            packed_buffer = []

            # The driver board assumes all data is read in as 16bit ints. To match
            # the endianness every pair of bytes must be swapped.
            # The image is always padded to a multiple of 8, so we can safely go in steps of 4.
            for i in range(0, len(frame_buffer), 4):
                # Values are in the range 0..255, so we don't need to "and" after we shift
                packed_buffer += [(frame_buffer[i + 2] >> 4) | (frame_buffer[i + 3] & 0xF0)]
                packed_buffer += [(frame_buffer[i] >> 4) | (frame_buffer[i + 1] & 0xF0)]

            return packed_buffer
