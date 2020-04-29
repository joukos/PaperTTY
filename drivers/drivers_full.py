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

from abc import abstractmethod
from drivers.drivers_base import WaveshareEPD


class WaveshareFull(WaveshareEPD):
    """Base class for displays that don't support partial refresh."""

    AUTO_MEASUREMENT_VCOM = 0x80
    BOOSTER_SOFT_START = 0x06
    DATA_START_TRANSMISSION_1 = 0x10
    DATA_STOP = 0x11
    DEEP_SLEEP = 0x07
    DISPLAY_REFRESH = 0x12
    LOW_POWER_DETECTION = 0x51
    LUT_FOR_VCOM = 0x20
    PANEL_SETTING = 0x00
    PLL_CONTROL = 0x30
    POWER_OFF = 0x02
    POWER_OFF_SEQUENCE_SETTING = 0x03
    POWER_ON = 0x04
    POWER_ON_MEASURE = 0x05
    POWER_SETTING = 0x01
    TCON_SETTING = 0x60
    TEMPERATURE_SENSOR_COMMAND = 0x40
    TEMPERATURE_SENSOR_READ = 0x43
    TEMPERATURE_SENSOR_WRITE = 0x42
    VCOM_AND_DATA_INTERVAL_SETTING = 0x50

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.supports_partial = False
        self.colors = 2
        self.lut = None

    def wait_until_idle(self):
        while self.digital_read(self.BUSY_PIN) == 0:  # 0: busy, 1: idle
            self.delay_ms(100)

    @abstractmethod
    def display_frame(self, frame_buffer, *args):
        """Accept more than one frame buffer since some displays use two"""
        pass

    @abstractmethod
    def init(self, **kwargs):
        pass

    def draw(self, x, y, image):
        """Display an image - this module does not support partial refresh: x, y are ignored"""
        self.display_frame(self.get_frame_buffer(image))

    def get_frame_buffer(self, image, reverse=False):
        buf = [0xFF if reverse else 0x00] * int(self.width * self.height / 8)
        # Set buffer to value of Python Imaging Library image.
        # Image must be in mode 1.
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display: required ({0}x{1}), got ({2}x{3})'
                             .format(self.width, self.height, imwidth, imheight))

        pixels = image_monocolor.load()
        for y in range(self.height):
            for x in range(self.width):
                # Set the bits for the column of pixels at the current position.
                if reverse:
                    if pixels[x, y] == 0:
                        buf[int((x + y * self.width) / 8)] &= ~(0x80 >> (x % 8))
                else:
                    if pixels[x, y] != 0:
                        buf[int((x + y * self.width) / 8)] |= (0x80 >> (x % 8))
        return buf


class EPD2in7(WaveshareFull):
    """Waveshare 2.7" - monochrome"""

    # EPD2IN7 commands
    ACTIVE_PROGRAM = 0xA1
    DATA_START_TRANSMISSION_2 = 0x13
    LUT_BLACK_TO_BLACK = 0x24
    LUT_BLACK_TO_WHITE = 0x22
    LUT_WHITE_TO_BLACK = 0x23
    LUT_WHITE_TO_WHITE = 0x21
    PARTIAL_DATA_START_TRANSMISSION_1 = 0x14
    PARTIAL_DATA_START_TRANSMISSION_2 = 0x15
    PARTIAL_DISPLAY_REFRESH = 0x16
    PROGRAM_MODE = 0xA0
    READ_OTP_DATA = 0xA2
    SOURCE_AND_GATE_START_SETTING = 0x62
    TCON_RESOLUTION = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x41
    VCM_DC_SETTING_REGISTER = 0x82
    VCOM_VALUE = 0x81

    def __init__(self):
        super().__init__(name='2.7" BW', width=176, height=264)

    lut_vcom_dc = [
        0x00, 0x00,
        0x00, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x00, 0x32, 0x32, 0x00, 0x00, 0x02,
        0x00, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # R21H
    lut_ww = [
        0x50, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x60, 0x32, 0x32, 0x00, 0x00, 0x02,
        0xA0, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # R22H    r
    lut_bw = [
        0x50, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x60, 0x32, 0x32, 0x00, 0x00, 0x02,
        0xA0, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # R24H    b
    lut_bb = [
        0xA0, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x60, 0x32, 0x32, 0x00, 0x00, 0x02,
        0x50, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # R23H    w
    lut_wb = [
        0xA0, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x60, 0x32, 0x32, 0x00, 0x00, 0x02,
        0x50, 0x0F, 0x0F, 0x00, 0x00, 0x05,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        # EPD hardware init start
        self.reset()
        self.send_command(self.POWER_SETTING)
        self.send_data(0x03)  # VDS_EN, VDG_EN
        self.send_data(0x00)  # VCOM_HV, VGHL_LV[1], VGHL_LV[0]
        self.send_data(0x2b)  # VDH
        self.send_data(0x2b)  # VDL
        self.send_data(0x09)  # VDHR
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0x07)
        self.send_data(0x07)
        self.send_data(0x17)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x60)
        self.send_data(0xA5)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x89)
        self.send_data(0xA5)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x90)
        self.send_data(0x00)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x93)
        self.send_data(0x2A)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0xA0)
        self.send_data(0xA5)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0xA1)
        self.send_data(0x00)
        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x73)
        self.send_data(0x41)
        self.send_command(self.PARTIAL_DISPLAY_REFRESH)
        self.send_data(0x00)
        self.send_command(self.POWER_ON)
        self.wait_until_idle()

        self.send_command(self.PANEL_SETTING)
        self.send_data(0xAF)  # KW-BF   KWR-AF    BWROTP 0f
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x3A)  # 3A 100HZ   29 150Hz 39 200HZ    31 171HZ
        self.send_command(self.VCM_DC_SETTING_REGISTER)
        self.send_data(0x12)
        self.delay_ms(2)
        self.set_lut()
        # EPD hardware init end
        return 0

    def set_lut(self):
        self.send_command(self.LUT_FOR_VCOM)  # vcom
        for count in range(0, 44):
            self.send_data(self.lut_vcom_dc[count])
        self.send_command(self.LUT_WHITE_TO_WHITE)  # ww --
        for count in range(0, 42):
            self.send_data(self.lut_ww[count])
        self.send_command(self.LUT_BLACK_TO_WHITE)  # bw r
        for count in range(0, 42):
            self.send_data(self.lut_bw[count])
        self.send_command(self.LUT_WHITE_TO_BLACK)  # wb w
        for count in range(0, 42):
            self.send_data(self.lut_bb[count])
        self.send_command(self.LUT_BLACK_TO_BLACK)  # bb b
        for count in range(0, 42):
            self.send_data(self.lut_wb[count])

    def display_frame(self, frame_buffer, *args):
        if frame_buffer:
            self.send_command(self.DATA_START_TRANSMISSION_1)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(0xFF)
            self.delay_ms(2)
            self.send_command(self.DATA_START_TRANSMISSION_2)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(frame_buffer[i])
            self.delay_ms(2)
            self.send_command(self.DISPLAY_REFRESH)
            self.wait_until_idle()

    # After this command is transmitted, the chip would enter the deep-sleep
    # mode to save power. The deep sleep mode would return to standby by
    # hardware reset. The only one parameter is a check code, the command would
    # be executed if check code = 0xA5.
    # Use EPD::Reset() to awaken and use EPD::Init() to initialize.
    def sleep(self):
        self.send_command(self.DEEP_SLEEP)
        self.delay_ms(2)
        self.send_data(0xa5)


class EPD7in5(WaveshareFull):
    """Waveshare 7.5" - monochrome"""

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
    VCM_DC_SETTING = 0x82

    def __init__(self):
        super().__init__(name='7.5" BW', width=640, height=384)

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

    def display_frame(self, frame_buffer, *args):
        self.send_command(self.DATA_START_TRANSMISSION_1)
        for i in range(0, 30720):
            temp1 = frame_buffer[i]
            j = 0
            while j < 8:
                if temp1 & 0x80:
                    temp2 = 0x03
                else:
                    temp2 = 0x00
                temp2 = (temp2 << 4) & 0xFF
                temp1 = (temp1 << 1) & 0xFF
                j += 1
                if temp1 & 0x80:
                    temp2 |= 0x03
                else:
                    temp2 |= 0x00
                temp1 = (temp1 << 1) & 0xFF
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

class EPD7in5v2(WaveshareFull):
    """WaveShare 7.5" GDEW075T7 - monochrome"""

    DATA_START_TRANSMISSION_2 = 0x13
    LUT_WHITE_TO_WHITE = 0x21
    LUT_BLACK_TO_WHITE = 0x22
    LUT_WHITE_TO_BLACK = 0x23
    LUT_BLACK_TO_BLACK = 0x24
    READ_VCOM_VALUE = 0x81
    # REVISION = 0x70
    # SPI_FLASH_CONTROL = 0x65
    # TCON_RESOLUTION = 0x61
    TEMPERATURE_CALIBRATION = 0x41 # Assuming TEMPERATURE_SENSOR_SELECTION
    VCM_DC_SETTING = 0x82

    def __init__(self):
        super().__init__(name='7.5" v2 (GDEW075T7) BW', width=800, height=480)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()

        self.send_command(self.POWER_SETTING)
        self.send_data(0x07) # VDS_EN, VDG_EN
        self.send_data(0x07) # VCOM_HV, VGHL_LV[1], VGHL_LV[0]
        self.send_data(0x3f) # VDH
        self.send_data(0x3f) # VDL

        self.send_command(self.POWER_ON)
        self.wait_until_idle()

        self.send_command(self.PANEL_SETTING)
        self.send_data(0x1f) # KW-3f   KWR-2F        BWROTP 0f       BWOTP 1f

        self.send_command(0x15)
        self.send_data(0x00)

        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x10)
        self.send_data(0x07)

        self.send_command(self.TCON_SETTING)
        self.send_data(0x22)

        print('Init finished.')

    def display_frame(self, frame_buffer, *args):
        if frame_buffer:
            self.send_command(self.DATA_START_TRANSMISSION_1)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(0xFF)
            self.delay_ms(2)
            self.send_command(self.DATA_START_TRANSMISSION_2)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(~frame_buffer[i])
            self.delay_ms(2)

            self.send_command(self.DISPLAY_REFRESH)
            self.delay_ms(100)
            self.wait_until_idle()

    def sleep(self):
        '''
        After this command is transmitted, the chip would enter the
        deep-sleep mode to save power.
        The deep sleep mode would return to standby by hardware reset.
        The only one parameter is a check code, the command would be
        executed if check code = 0xA5.
        You can use Epd::Reset() to awaken or Epd::Init() to initialize
        '''

        self.send_command(self.POWER_OFF)
        self.wait_until_idle()
        self.send_command(self.DEEP_SLEEP)
        self.send_data(0xA5)

    def reset(self):
        """
        Mirroring behaviour in reference implementation:
        https://github.com/waveshare/e-Paper/blob/702def06bcb75983c98b0f9d25d43c552c248eb0/RaspberryPi%26JetsonNano/python/lib/waveshare_epd/epd7in5_V2.py#L48-L54

        The `reset` inherited from `WaveshareFull` did not work (`init` hanged at `wait_until_idle` after the `POWER_ON`
        command was sent.

        A quick scan of the other implementations indicates that the reset varies across devices (it's unclear
        whether there is good reason for device specific differences or if the developer was just being inconsistent...)
        e.g. significantly different delay times:
        https://github.com/waveshare/e-Paper/blob/702def06bcb75983c98b0f9d25d43c552c248eb0/RaspberryPi%26JetsonNano/python/lib/waveshare_epd/epd1in54c.py#L46-L52
        """
        # Deliberately importing here to achieve same fail-on-use import behaviour as in `drivers_base.py`
        import RPi.GPIO as GPIO

        self.digital_write(self.RST_PIN, GPIO.HIGH)
        self.delay_ms(200)
        self.digital_write(self.RST_PIN, GPIO.LOW)
        self.delay_ms(2)
        self.digital_write(self.RST_PIN, GPIO.HIGH)
        self.delay_ms(200)

    def wait_until_idle(self):
        """
        Mirroring behaviour in reference implementation (i.e. differently to other implementations, we send command 0x71
        and poll without sleep):
        https://github.com/waveshare/e-Paper/blob/702def06bcb75983c98b0f9d25d43c552c248eb0/RaspberryPi%26JetsonNano/python/lib/waveshare_epd/epd7in5_V2.py#L68-L75
        """
        self.send_command(0x71)
        while self.digital_read(self.BUSY_PIN) == 0:  # 0: busy, 1: idle
            self.send_command(0x71)
