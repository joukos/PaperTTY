#     Copyright (c) 2018 Jouko Strömmer
#     Copyright (c) 2017 Waveshare
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

from papertty.drivers.drivers_full import WaveshareFull

from PIL import Image



class WaveshareColor(WaveshareFull):
    """Base class for 'color' displays, the B/C variants: black-white-red and black-white-yellow. This includes:
    - 4.2" B (uses two separate frame buffers - one for B/W and one for red)
    - 7.5" B (uses one frame buffer - black < 64 < red < 192 < white)
    """

    VCM_DC_SETTING = 0x82

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.colors = 3

    def display_frame(self, frame_buffer, *args):
        pass

    def init(self, **kwargs):
        pass

    def draw(self, x, y, image):
        """Display an image - this module does not support partial refresh: x, y are ignored
        IMPORTANT NOTE: this method IGNORES the red buffer completely!"""
        self.display_frame(self.get_frame_buffer(image))


class EPD4in2b(WaveshareColor):
    """Waveshare 4.2" B - black / white / red"""

    ACTIVE_PROGRAM = 0xA1
    B2B_LUT = 0x24
    B2W_LUT = 0x22
    DATA_START_TRANSMISSION_2 = 0x13
    GSST_SETTING = 0x65
    PARTIAL_IN = 0x91
    PARTIAL_OUT = 0x92
    PARTIAL_WINDOW = 0x90
    POWER_SAVING = 0xE3
    PROGRAM_MODE = 0xA0
    READ_OTP_DATA = 0xA2
    RESOLUTION_SETTING = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x40
    TEMPERATURE_SENSOR_SELECTION = 0x41
    VCOM_LUT = 0x20
    VCOM_VALUE = 0x81
    W2B_LUT = 0x23
    W2W_LUT = 0x21

    def __init__(self):
        super().__init__(name='4.2" B', width=400, height=300)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x17)  # 07 0f 17 1f 27 2F 37 2f
        self.send_command(self.POWER_ON)
        self.wait_until_idle()
        self.send_command(self.PANEL_SETTING)
        self.send_data(0x0F)  # LUT from OTP

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)

    def display_frame(self, frame_buffer_black, *args):
        frame_buffer_red = args[0] if args else None
        if frame_buffer_black:
            self.send_command(self.DATA_START_TRANSMISSION_1)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(frame_buffer_black[i])
            self.delay_ms(2)
        if frame_buffer_red:
            self.send_command(self.DATA_START_TRANSMISSION_2)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(frame_buffer_red[i])
            self.delay_ms(2)

        self.send_command(self.DISPLAY_REFRESH)
        self.wait_until_idle()

    # after this, call epd.init() to awaken the module
    def sleep(self):
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0xF7)  # border floating
        self.send_command(self.POWER_OFF)
        self.wait_until_idle()
        self.send_command(self.DEEP_SLEEP)
        self.send_data(0xA5)  # check code


class EPD7in5b(WaveshareColor):
    """Waveshare 7.5" B - black / white / red"""

    IMAGE_PROCESS = 0x13
    LUT_BLUE = 0x21
    LUT_GRAY_1 = 0x23
    LUT_GRAY_2 = 0x24
    LUT_RED_0 = 0x25
    LUT_RED_1 = 0x26
    LUT_RED_2 = 0x27
    LUT_RED_3 = 0x28
    LUT_WHITE = 0x22
    LUT_XON = 0x29
    READ_VCOM_VALUE = 0x81
    REVISION = 0x70
    SPI_FLASH_CONTROL = 0x65
    TCON_RESOLUTION = 0x61
    TEMPERATURE_CALIBRATION = 0x41

    def __init__(self):
        super().__init__(name='7.5" B', width=640, height=384)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.POWER_SETTING)
        self.send_data(0x37)
        self.send_data(0x00)
        self.send_command(self.PANEL_SETTING)
        self.send_data(0xCF)
        self.send_data(0x08)
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0xc7)
        self.send_data(0xcc)
        self.send_data(0x28)
        self.send_command(self.POWER_ON)
        self.wait_until_idle()
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x3c)
        self.send_command(self.TEMPERATURE_CALIBRATION)
        self.send_data(0x00)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x77)
        self.send_command(self.TCON_SETTING)
        self.send_data(0x22)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x02)  # source 640
        self.send_data(0x80)
        self.send_data(0x01)  # gate 384
        self.send_data(0x80)
        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x1E)  # decide by LUT file
        self.send_command(0xe5)  # FLASH MODE
        self.send_data(0x03)

    def get_frame_buffer(self, image, reverse=False):
        buf = [0x00] * int(self.width * self.height / 4)
        # Set buffer to value of Python Imaging Library image.
        # Image must be in mode L.
        image_grayscale = image.convert('L')
        imwidth, imheight = image_grayscale.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display \
                ({0}x{1}).'.format(self.width, self.height))

        pixels = image_grayscale.load()
        for y in range(self.height):
            for x in range(self.width):
                # Set the bits for the column of pixels at the current position.
                if pixels[x, y] < 64:  # black
                    buf[int((x + y * self.width) / 4)] &= ~(0xC0 >> (x % 4 * 2))
                elif pixels[x, y] < 192:  # convert gray to red
                    buf[int((x + y * self.width) / 4)] &= ~(0xC0 >> (x % 4 * 2))
                    buf[int((x + y * self.width) / 4)] |= 0x40 >> (x % 4 * 2)
                else:  # white
                    buf[int((x + y * self.width) / 4)] |= 0xC0 >> (x % 4 * 2)
        return buf

    def display_frame(self, frame_buffer, *args):
        self.send_command(self.DATA_START_TRANSMISSION_1)
        for i in range(0, int(self.width / 4 * self.height)):
            temp1 = frame_buffer[i]
            j = 0
            while j < 4:
                if (temp1 & 0xC0) == 0xC0:
                    temp2 = 0x03
                elif (temp1 & 0xC0) == 0x00:
                    temp2 = 0x00
                else:
                    temp2 = 0x04
                temp2 = (temp2 << 4) & 0xFF
                temp1 = (temp1 << 2) & 0xFF
                j += 1
                if (temp1 & 0xC0) == 0xC0:
                    temp2 |= 0x03
                elif (temp1 & 0xC0) == 0x00:
                    temp2 |= 0x00
                else:
                    temp2 |= 0x04
                temp1 = (temp1 << 2) & 0xFF
                self.send_data(temp2)
                j += 1
        self.send_command(self.DISPLAY_REFRESH)
        self.delay_ms(100)
        self.wait_until_idle()

    def sleep(self):
        self.send_command(self.POWER_OFF)
        self.wait_until_idle()
        self.send_command(self.DEEP_SLEEP)
        self.send_data(0xa5)


class EPD5in65f(WaveshareColor):
    """Waveshare 5.65" - 7 colors"""

    LUT_BLACK = 0x000000  # 0000  BGR
    LUT_WHITE = 0xffffff  # 0001
    LUT_GREEN = 0x00ff00  # 0010
    LUT_BLUE = 0xff0000  # 0011
    LUT_RED = 0x0000ff  # 0100
    LUT_YELLOW = 0x00ffff  # 0101
    LUT_ORANGE = 0x0080ff  # 0110
    POWER_SAVING = 0xE3
    TCON_RESOLUTION = 0x61
    TEMPERATURE_CALIBRATION = 0x41

    def __init__(self):
        super().__init__(name='5.65" F', width=600, height=448)

    def reset(self):
        self.digital_write(self.RST_PIN, 1)
        self.delay_ms(600)
        self.digital_write(self.RST_PIN, 0)
        self.delay_ms(2)
        self.digital_write(self.RST_PIN, 1)
        self.delay_ms(200)

    def send_command(self, command):
        self.digital_write(self.DC_PIN, 0)
        self.digital_write(self.CS_PIN, 0)
        self.spi_transfer([command])
        self.digital_write(self.CS_PIN, 1)

    def send_data(self, data):
        self.digital_write(self.DC_PIN, 1)
        self.digital_write(self.CS_PIN, 0)
        self.spi_transfer([data])
        self.digital_write(self.CS_PIN, 1)

    def wait_until_busy(self):
        while self.digital_read(self.BUSY_PIN) == 0:  # 0: idle, 1: busy
            self.delay_ms(100)

    def wait_until_idle(self):
        while self.digital_read(self.BUSY_PIN) == 1:  # 0: idle, 1: busy
            self.delay_ms(100)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1

        # EPD hardware init start
        self.reset()

        self.wait_until_busy()
        self.send_command(self.PANEL_SETTING)
        self.send_data(0xEF)
        self.send_data(0x08)
        self.send_command(self.POWER_SETTING)
        self.send_data(0x37)
        self.send_data(0x00)
        self.send_data(0x23)
        self.send_data(0x23)
        self.send_command(self.POWER_OFF_SEQUENCE_SETTING)
        self.send_data(0x00)
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0xC7)
        self.send_data(0xC7)
        self.send_data(0x1D)
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x3C)
        self.send_command(self.TEMPERATURE_SENSOR_COMMAND)
        self.send_data(0x00)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x37)
        self.send_command(self.TCON_SETTING)
        self.send_data(0x22)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x02)
        self.send_data(0x58)
        self.send_data(0x01)
        self.send_data(0xC0)
        self.send_command(self.POWER_SAVING)
        self.send_data(0xAA)

        self.delay_ms(100)
        self.send_command(0x50)
        self.send_data(0x37)

    def get_frame_buffer(self, image, reverse=False):
        buf = [0x00] * int(self.width * self.height / 2)

        # quantize image with palette of possible colors
        image_palette = Image.new('P', (1, 1))
        image_palette.putpalette(([0, 0, 0, 255, 255, 255, 0, 255, 0, 0, 0, 255, 255, 0, 0, 255, 255, 0, 255, 128, 0]
                                  + [0, 0, 0]) * 32) # multiply by 32 to pad palette to reach required length of 768
        image_rgb = image.quantize(palette=image_palette).convert('RGB')

        imwidth, imheight = image_rgb.size

        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display \
                ({0}x{1}).'.format(self.width, self.height))

        pixels = image_rgb.load()

        for y in range(self.height):
            for x in range(self.width):
                pos = int((x + y * self.width) / 2)
                color = 0

                if pixels[x, y][0] == 0 and pixels[x, y][1] == 0 and pixels[x, y][2] == 0:
                    color = 0
                elif pixels[x, y][0] == 255 and pixels[x, y][1] == 255 and pixels[x, y][2] == 255:
                    color = 1
                elif pixels[x, y][0] == 0 and pixels[x, y][1] == 255 and pixels[x, y][2] == 0:
                    color = 2
                elif pixels[x, y][0] == 0 and pixels[x, y][1] == 0 and pixels[x, y][2] == 255:
                    color = 3
                elif pixels[x, y][0] == 255 and pixels[x, y][1] == 0 and pixels[x, y][2] == 0:
                    color = 4
                elif pixels[x, y][0] == 255 and pixels[x, y][1] == 255 and pixels[x, y][2] == 0:
                    color = 5
                elif pixels[x, y][0] == 255 and pixels[x, y][1] == 128 and pixels[x, y][2] == 0:
                    color = 6

                data_t = buf[pos] & (~(0xF0 >> ((x % 2) * 4)))
                buf[pos] = data_t | ((color << 4) >> ((x % 2) * 4))

        return buf

    def display_frame(self, frame_buffer, *args):
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x02)
        self.send_data(0x58)
        self.send_data(0x01)
        self.send_data(0xC0)
        self.send_command(self.DATA_START_TRANSMISSION_1)
        for i in range(0, int(self.height)):
            for j in range(0, int(self.width / 2)):
                self.send_data((frame_buffer[j + (int(self.width / 2) * i)]))
        self.send_command(self.POWER_ON)
        self.wait_until_busy()
        self.send_command(self.DISPLAY_REFRESH)
        self.wait_until_busy()
        self.send_command(self.POWER_OFF)
        self.wait_until_idle()
        self.delay_ms(500)

    def sleep(self):
        self.delay_ms(500)
        self.send_command(self.DEEP_SLEEP)
        self.send_data(0XA5)
        self.digital_write(self.RST_PIN, 0)


# This is a 'monochrome' display but surprisingly, the only difference to EPD7in5b is
# setting a different resolution in init() (after TCON_RESOLUTION command),
# thus, it is here and a subclass of EPD7in5b (for now).
class EPD5in83(EPD7in5b):
    """Waveshare 5.83" - monochrome"""

    def __init__(self, **kwargs):
        super().__init__()
        self.name = '5.83" BW'
        self.width = 600
        self.height = 448

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.POWER_SETTING)
        self.send_data(0x37)
        self.send_data(0x00)
        self.send_command(self.PANEL_SETTING)
        self.send_data(0xCF)
        self.send_data(0x08)
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0xc7)
        self.send_data(0xcc)
        self.send_data(0x28)
        self.send_command(self.POWER_ON)
        self.wait_until_idle()
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x3c)
        self.send_command(self.TEMPERATURE_CALIBRATION)
        self.send_data(0x00)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x77)
        self.send_command(self.TCON_SETTING)
        self.send_data(0x22)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x02)  # source 600
        self.send_data(0x58)
        self.send_data(0x01)  # gate 448
        self.send_data(0xC0)
        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x1E)  # decide by LUT file
        self.send_command(0xe5)  # FLASH MODE
        self.send_data(0x03)


class EPD5in83b(EPD5in83):
    """Waveshare 5.83" B - black / white / red"""

    def __init__(self, **kwargs):
        super().__init__()
        self.name = '5.83" B'

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.POWER_SETTING)
        self.send_data(0x37)
        self.send_data(0x00)
        self.send_command(self.PANEL_SETTING)
        self.send_data(0xCF)
        self.send_data(0x08)
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0xc7)
        self.send_data(0xcc)
        self.send_data(0x28)
        self.send_command(self.POWER_ON)
        self.wait_until_idle()
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x3c)
        self.send_command(self.TEMPERATURE_CALIBRATION)
        self.send_data(0x00)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x77)
        self.send_command(self.TCON_SETTING)
        self.send_data(0x22)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x02)  # source 600
        self.send_data(0x58)
        self.send_data(0x01)  # gate 448
        self.send_data(0xc0)
        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x20)  # decide by LUT file
        self.send_command(0xe5)  # FLASH MODE
        self.send_data(0x03)

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)

    def display_frame(self, frame_buffer_black, *args):
        frame_buffer_red = args[0] if args else None
        self.send_command(self.DATA_START_TRANSMISSION_1)
        for i in range(0, int(self.width / 8 * self.height)):
            temp1 = frame_buffer_black[i]
            temp2 = frame_buffer_red[i]
            j = 0
            while j < 8:
                if (temp2 & 0x80) == 0x00:
                    temp3 = 0x04  # red
                elif (temp1 & 0x80) == 0x00:
                    temp3 = 0x00  # black
                else:
                    temp3 = 0x03  # white

                temp3 = (temp3 << 4) & 0xFF
                temp1 = (temp1 << 1) & 0xFF
                temp2 = (temp2 << 1) & 0xFF
                j += 1
                if (temp2 & 0x80) == 0x00:
                    temp3 |= 0x04  # red
                elif (temp1 & 0x80) == 0x00:
                    temp3 |= 0x00  # black
                else:
                    temp3 |= 0x03  # white
                temp1 = (temp1 << 1) & 0xFF
                temp2 = (temp2 << 1) & 0xFF
                self.send_data(temp3)
                j += 1
        self.send_command(self.DISPLAY_REFRESH)
        self.delay_ms(100)
        self.wait_until_idle()
