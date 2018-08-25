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

from drivers.drivers_full import WaveshareFull


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
        lookup = {0xC0: 0x03, 0x00: 0x00}
        self.send_command(self.DATA_START_TRANSMISSION_1)
        for i in range(0, int(self.width / 4 * self.height)):
            temp1 = frame_buffer[i]
            j = 0
            while j < 4:
                temp2 = lookup.get(temp1 & 0xC0, 0x04)
                temp2 = (temp2 << 4) & 0xFF
                temp1 = (temp1 << 2) & 0xFF
                j += 1
                temp2 |= lookup.get(temp1 & 0xC0, 0x04)
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
