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

from drivers import drivers_base


class WavesharePartial(drivers_base.WaveshareEPD):
    """Displays that support partial refresh (*monochrome*): 1.54", 2.13", 2.9". 
    The code is almost entirely identical with these, just small differences in the 2.13"."""

    BOOSTER_SOFT_START_CONTROL = 0x0C
    BORDER_WAVEFORM_CONTROL = 0x3C
    DATA_ENTRY_MODE_SETTING = 0x11
    DEEP_SLEEP_MODE = 0x10
    DISPLAY_UPDATE_CONTROL_1 = 0x21
    DISPLAY_UPDATE_CONTROL_2 = 0x22
    DRIVER_OUTPUT_CONTROL = 0x01
    GATE_SCAN_START_POSITION = 0x0F
    MASTER_ACTIVATION = 0x20
    SET_DUMMY_LINE_PERIOD = 0x3A
    SET_GATE_TIME = 0x3B
    SET_RAM_X_ADDRESS_COUNTER = 0x4E
    SET_RAM_X_ADDRESS_START_END_POSITION = 0x44
    SET_RAM_Y_ADDRESS_COUNTER = 0x4F
    SET_RAM_Y_ADDRESS_START_END_POSITION = 0x45
    SW_RESET = 0x12
    TEMPERATURE_SENSOR_CONTROL = 0x1A
    TERMINATE_FRAME_READ_WRITE = 0xFF
    WRITE_LUT_REGISTER = 0x32
    WRITE_RAM = 0x24
    WRITE_VCOM_REGISTER = 0x2C

    # these LUTs are used by 1.54" and 2.9" - 2.13" overrides them
    lut_full_update = [
        0x02, 0x02, 0x01, 0x11, 0x12, 0x12, 0x22, 0x22,
        0x66, 0x69, 0x69, 0x59, 0x58, 0x99, 0x99, 0x88,
        0x00, 0x00, 0x00, 0x00, 0xF8, 0xB4, 0x13, 0x51,
        0x35, 0x51, 0x51, 0x19, 0x01, 0x00
    ]

    lut_partial_update = [
        0x10, 0x18, 0x18, 0x08, 0x18, 0x18, 0x08, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x13, 0x14, 0x44, 0x12,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.supports_partial = True
        self.colors = 2
        self.lut = None

    def init(self, partial=True):
        self.partial_refresh = partial
        if self.epd_init() != 0:
            return -1
        # EPD hardware init start
        self.lut = self.lut_partial_update if partial else self.lut_full_update
        self.reset()
        self.send_command(self.DRIVER_OUTPUT_CONTROL)
        self.send_data((self.height - 1) & 0xFF)
        self.send_data(((self.height - 1) >> 8) & 0xFF)
        self.send_data(0x00)  # GD = 0 SM = 0 TB = 0
        self.send_command(self.BOOSTER_SOFT_START_CONTROL)
        self.send_data(0xD7)
        self.send_data(0xD6)
        self.send_data(0x9D)
        self.send_command(self.WRITE_VCOM_REGISTER)
        self.send_data(0xA8)  # VCOM 7C
        self.send_command(self.SET_DUMMY_LINE_PERIOD)
        self.send_data(0x1A)  # 4 dummy lines per gate
        self.send_command(self.SET_GATE_TIME)
        self.send_data(0x08)  # 2us per line
        self.send_command(self.DATA_ENTRY_MODE_SETTING)
        self.send_data(0x03)  # X increment Y increment
        self.set_lut(self.lut)
        # EPD hardware init end
        return 0

    def wait_until_idle(self):
        while self.digital_read(self.BUSY_PIN) == 1:  # 0: idle, 1: busy
            self.delay_ms(100)

    def set_lut(self, lut):
        self.lut = lut
        self.send_command(self.WRITE_LUT_REGISTER)
        # the length of look-up table is 30 bytes
        for i in range(0, len(lut)):
            self.send_data(self.lut[i])

    def get_frame_buffer(self, image):
        buf = [0x00] * int(self.width * self.height / 8)
        # Set buffer to value of Python Imaging Library image.
        # Image must be in mode 1.
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display \
                ({0}x{1}).'.format(self.width, self.height))

        pixels = image_monocolor.load()
        for y in range(self.height):
            for x in range(self.width):
                # Set the bits for the column of pixels at the current position.
                if pixels[x, y] != 0:
                    buf[int((x + y * self.width) / 8)] |= 0x80 >> (x % 8)
        return buf

    # this differs with 2.13" but is the same for 1.54" and 2.9"
    def set_frame_memory(self, image, x, y):
        if image is None or x < 0 or y < 0:
            return
        image_monocolor = image.convert('1')
        image_width, image_height = image_monocolor.size
        # x point must be the multiple of 8 or the last 3 bits will be ignored
        x = x & 0xF8
        image_width = image_width & 0xF8
        if x + image_width >= self.width:
            x_end = self.width - 1
        else:
            x_end = x + image_width - 1
        if y + image_height >= self.height:
            y_end = self.height - 1
        else:
            y_end = y + image_height - 1
        self.set_memory_area(x, y, x_end, y_end)
        self.set_memory_pointer(x, y)
        self.send_command(self.WRITE_RAM)
        # send the image data
        pixels = image_monocolor.load()
        byte_to_send = 0x00
        for j in range(0, y_end - y + 1):
            # 1 byte = 8 pixels, steps of i = 8
            for i in range(0, x_end - x + 1):
                # Set the bits for the column of pixels at the current position.
                if pixels[i, j] != 0:
                    byte_to_send |= 0x80 >> (i % 8)
                if i % 8 == 7:
                    self.send_data(byte_to_send)
                    byte_to_send = 0x00

    def clear_frame_memory(self, color):
        self.set_memory_area(0, 0, self.width - 1, self.height - 1)
        self.set_memory_pointer(0, 0)
        self.send_command(self.WRITE_RAM)
        # send the color data
        for i in range(0, int(self.width / 8 * self.height)):
            self.send_data(color)

    def display_frame(self):
        self.send_command(self.DISPLAY_UPDATE_CONTROL_2)
        self.send_data(0xC4)
        self.send_command(self.MASTER_ACTIVATION)
        self.send_command(self.TERMINATE_FRAME_READ_WRITE)
        self.wait_until_idle()

    def set_memory_area(self, x_start, y_start, x_end, y_end):
        self.send_command(self.SET_RAM_X_ADDRESS_START_END_POSITION)
        # x point must be the multiple of 8 or the last 3 bits will be ignored
        self.send_data((x_start >> 3) & 0xFF)
        self.send_data((x_end >> 3) & 0xFF)
        self.send_command(self.SET_RAM_Y_ADDRESS_START_END_POSITION)
        self.send_data(y_start & 0xFF)
        self.send_data((y_start >> 8) & 0xFF)
        self.send_data(y_end & 0xFF)
        self.send_data((y_end >> 8) & 0xFF)

    def set_memory_pointer(self, x, y):
        self.send_command(self.SET_RAM_X_ADDRESS_COUNTER)
        # x point must be the multiple of 8 or the last 3 bits will be ignored
        self.send_data((x >> 3) & 0xFF)
        self.send_command(self.SET_RAM_Y_ADDRESS_COUNTER)
        self.send_data(y & 0xFF)
        self.send_data((y >> 8) & 0xFF)
        self.wait_until_idle()

    def sleep(self):
        self.send_command(self.DEEP_SLEEP_MODE)
        self.wait_until_idle()

    def draw(self, x, y, image):
        """Replace a particular area on the display with an image"""
        self.set_frame_memory(image, x, y)
        self.display_frame()
        if self.partial_refresh:
            # set the memory again if partial refresh LUT is used
            self.set_frame_memory(image, x, y)
            self.display_frame()


class EPD1in54(WavesharePartial):
    """Waveshare 1.54" - monochrome"""

    def __init__(self):
        super().__init__(name='1.54" BW', width=200, height=200)


class EPD2in13(WavesharePartial):
    """Waveshare 2.13" - monochrome"""

    lut_full_update = [
        0x22, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x11,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x1E, 0x1E, 0x1E, 0x1E, 0x1E, 0x1E, 0x1E, 0x1E,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    lut_partial_update = [
        0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x0F, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    def __init__(self):
        # the actual pixel width is 122, but 128 is the 'logical' width
        super().__init__(name='2.13" BW', width=128, height=250)

    def set_frame_memory(self, image, x, y):
        if image is None or x < 0 or y < 0:
            return
        image_monocolor = image.convert('1')
        image_width, image_height = image_monocolor.size
        # x point must be the multiple of 8 or the last 3 bits will be ignored
        x = x & 0xF8
        image_width = image_width & 0xF8
        if x + image_width >= self.width:
            x_end = self.width - 1
        else:
            x_end = x + image_width - 1
        if y + image_height >= self.height:
            y_end = self.height - 1
        else:
            y_end = y + image_height - 1
        self.set_memory_area(x, y, x_end, y_end)
        # send the image data
        pixels = image_monocolor.load()
        byte_to_send = 0x00
        for j in range(y, y_end + 1):
            self.set_memory_pointer(x, j)
            self.send_command(self.WRITE_RAM)
            # 1 byte = 8 pixels, steps of i = 8
            for i in range(x, x_end + 1):
                # Set the bits for the column of pixels at the current position.
                if pixels[i - x, j - y] != 0:
                    byte_to_send |= 0x80 >> (i % 8)
                if i % 8 == 7:
                    self.send_data(byte_to_send)
                    byte_to_send = 0x00


class EPD2in13v2(WavesharePartial):
    """Waveshare 2.13" V2 - monochrome"""

    lut_full_update = [
        0x80,0x60,0x40,0x00,0x00,0x00,0x00,             #LUT0: BB:     VS 0 ~7
        0x10,0x60,0x20,0x00,0x00,0x00,0x00,             #LUT1: BW:     VS 0 ~7
        0x80,0x60,0x40,0x00,0x00,0x00,0x00,             #LUT2: WB:     VS 0 ~7
        0x10,0x60,0x20,0x00,0x00,0x00,0x00,             #LUT3: WW:     VS 0 ~7
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,             #LUT4: VCOM:   VS 0 ~7

        0x03,0x03,0x00,0x00,0x02,                       # TP0 A~D RP0
        0x09,0x09,0x00,0x00,0x02,                       # TP1 A~D RP1
        0x03,0x03,0x00,0x00,0x02,                       # TP2 A~D RP2
        0x00,0x00,0x00,0x00,0x00,                       # TP3 A~D RP3
        0x00,0x00,0x00,0x00,0x00,                       # TP4 A~D RP4
        0x00,0x00,0x00,0x00,0x00,                       # TP5 A~D RP5
        0x00,0x00,0x00,0x00,0x00,                       # TP6 A~D RP6

        0x15,0x41,0xA8,0x32,0x30,0x0A
    ]

    lut_partial_update = [
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,             #LUT0: BB:     VS 0 ~7
        0x80,0x00,0x00,0x00,0x00,0x00,0x00,             #LUT1: BW:     VS 0 ~7
        0x40,0x00,0x00,0x00,0x00,0x00,0x00,             #LUT2: WB:     VS 0 ~7
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,             #LUT3: WW:     VS 0 ~7
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,             #LUT4: VCOM:   VS 0 ~7

        0x0A,0x00,0x00,0x00,0x00,                       # TP0 A~D RP0
        0x00,0x00,0x00,0x00,0x00,                       # TP1 A~D RP1
        0x00,0x00,0x00,0x00,0x00,                       # TP2 A~D RP2
        0x00,0x00,0x00,0x00,0x00,                       # TP3 A~D RP3
        0x00,0x00,0x00,0x00,0x00,                       # TP4 A~D RP4
        0x00,0x00,0x00,0x00,0x00,                       # TP5 A~D RP5
        0x00,0x00,0x00,0x00,0x00,                       # TP6 A~D RP6

        0x15,0x41,0xA8,0x32,0x30,0x0A,
    ]

    def __init__(self):
        # the actual pixel width is 122, but 128 is the 'logical' width
        super().__init__(name='2.13" BW V2 (full refresh only)', width=128, height=250)


class EPD2in9(WavesharePartial):
    """Waveshare 2.9" - monochrome"""

    def __init__(self):
        super().__init__(name='2.9" BW', width=128, height=296)


class EPD2in13d(WavesharePartial):
    """Waveshare 2.13" D - monochrome (flexible)"""

    # Note: the original code for this display was pretty broken and seemed
    # to have been written by some other person than the rest of the drivers.

    def __init__(self):
        super().__init__(name='2.13" D', width=104, height=212)

    lut_vcomDC = [
        0x00, 0x08, 0x00, 0x00, 0x00, 0x02,
        0x60, 0x28, 0x28, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x12, 0x12, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
    ]

    lut_ww = [
        0x40, 0x08, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x28, 0x28, 0x00, 0x00, 0x01,
        0x40, 0x14, 0x00, 0x00, 0x00, 0x01,
        0xA0, 0x12, 0x12, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_bw = [
        0x40, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x0F, 0x0F, 0x00, 0x00, 0x03,
        0x40, 0x0A, 0x01, 0x00, 0x00, 0x01,
        0xA0, 0x0E, 0x0E, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_wb = [
        0x80, 0x08, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x28, 0x28, 0x00, 0x00, 0x01,
        0x80, 0x14, 0x00, 0x00, 0x00, 0x01,
        0x50, 0x12, 0x12, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_bb = [
        0x80, 0x08, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x28, 0x28, 0x00, 0x00, 0x01,
        0x80, 0x14, 0x00, 0x00, 0x00, 0x01,
        0x50, 0x12, 0x12, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_vcom1 = [
        0x00, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
    ]

    lut_ww1 = [
        0x00, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_bw1 = [
        0x80, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_wb1 = [
        0x40, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_bb1 = [
        0x00, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    def wait_until_idle(self):
        """This particular model's code sends the GET_STATUS command while waiting - dunno why."""
        while self.digital_read(self.BUSY_PIN) == 0:  # 0: idle, 1: busy
            self.send_command(self.GET_STATUS)
            self.delay_ms(100)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()

        self.send_command(0x01)  # POWER SETTING
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)
        self.send_data(0x03)

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)  # A
        self.send_data(0x17)  # B
        self.send_data(0x17)  # C

        self.send_command(0x04)
        self.wait_until_idle()

        self.send_command(0x00)  # panel setting
        self.send_data(0xbf)  # LUT from OTP,128x296
        self.send_data(0x0d)  # VCOM to 0V fast

        self.send_command(0x30)  # PLL setting
        self.send_data(0x3a)  # 3a 100HZ   29 150Hz 39 200HZ	31 171HZ

        self.send_command(0x61)  # resolution setting
        self.send_data(self.width)
        self.send_data((self.height >> 8) & 0xff)
        self.send_data(self.height & 0xff)

        self.send_command(0x82)  # vcom_DC setting
        self.send_data(0x28)

        # self.send_command(0X50)			#VCOM AND DATA INTERVAL SETTING
        # self.send_data(0xb7)		#WBmode:VBDF 17|D7 VBDW 97 VBDB 57		WBRmode:VBDF F7 VBDW 77 VBDB 37  VBDR B7
        return 0

    def set_full_reg(self):
        self.send_command(0x82)
        self.send_data(0x00)
        self.send_command(0X50)
        self.send_data(0xb7)

        self.send_command(0x20)  # vcom
        for count in range(0, 44):
            self.send_data(self.lut_vcomDC[count])
        self.send_command(0x21)  # ww --
        for count in range(0, 42):
            self.send_data(self.lut_ww[count])
        self.send_command(0x22)  # bw r
        for count in range(0, 42):
            self.send_data(self.lut_bw[count])
        self.send_command(0x23)  # wb w
        for count in range(0, 42):
            self.send_data(self.lut_wb[count])
        self.send_command(0x24)  # bb b
        for count in range(0, 42):
            self.send_data(self.lut_bb[count])

    def set_part_reg(self):
        self.send_command(0x82)
        self.send_data(0x03)
        self.send_command(0X50)
        self.send_data(0x47)

        self.send_command(0x20)  # vcom
        for count in range(0, 44):
            self.send_data(self.lut_vcom1[count])
        self.send_command(0x21)  # ww --
        for count in range(0, 42):
            self.send_data(self.lut_ww1[count])
        self.send_command(0x22)  # bw r
        for count in range(0, 42):
            self.send_data(self.lut_bw1[count])
        self.send_command(0x23)  # wb w
        for count in range(0, 42):
            self.send_data(self.lut_wb1[count])
        self.send_command(0x24)  # bb b
        for count in range(0, 42):
            self.send_data(self.lut_bb1[count])

    def turn_on_display(self):
        self.send_command(0x12)
        self.delay_ms(10)
        self.wait_until_idle()

    def clear(self):
        self.send_command(0x10)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(0x00)
        self.delay_ms(10)

        self.send_command(0x13)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(0xFF)
        self.delay_ms(10)

        self.set_full_reg()
        self.turn_on_display()

    def display_full(self, frame_buffer):
        if not frame_buffer:
            return

        self.send_command(0x10)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(0x00)
        self.delay_ms(10)

        self.send_command(0x13)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(frame_buffer[i])
        self.delay_ms(10)

        self.set_full_reg()
        self.turn_on_display()

    def display_partial(self, frame_buffer, x_start, y_start, x_end, y_end):
        if not frame_buffer:
            return

        self.set_part_reg()
        self.send_command(0x91)
        self.send_command(0x90)
        self.send_data(x_start)
        self.send_data(x_end - 1)

        self.send_data(y_start / 256)
        self.send_data(y_start % 256)
        self.send_data(y_end / 256)
        self.send_data(y_end % 256 - 1)
        self.send_data(0x28)

        self.send_command(0x10)
        for i in range(0, int(self.width * self.height / 8)):
            # print(frame_buffer[i],'%d','0x10')
            self.send_data(frame_buffer[i])
        self.delay_ms(10)

        self.send_command(0x13)
        for i in range(0, int(self.width * self.height / 8)):
            # print(~frame_buffer[i],'%d','0x13')
            self.send_data(~frame_buffer[i])
        self.delay_ms(10)

        # self.set_full_reg()
        self.turn_on_display()

    # after this, call epd.init() to awaken the module
    def sleep(self):
        self.send_command(0x50)
        self.send_data(0xf7)
        self.send_command(0x02)  # power off
        self.send_command(0x07)  # deep sleep
        self.send_data(0xA5)

    def draw(self, x, y, image):
        """Replace a particular area on the display with an image"""
        if self.partial_refresh:
            self.display_partial(self.get_frame_buffer(image), x, y, x + image.width, x + image.height)
        else:
            self.display_full(self.get_frame_buffer(image))


class EPD4in2(WavesharePartial):
    """Waveshare 4.2" """

    # code adapted from  EPD_4in2.c

    def __init__(self):
        super().__init__(name='4.2"', width=300, height=400)

    lut_vcom0 = [
        0x00, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x00, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x00, 0x0A, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x0E, 0x0E, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
    ];
    lut_ww = [
        0x40, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x40, 0x0A, 0x01, 0x00, 0x00, 0x01,
        0xA0, 0x0E, 0x0E, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    lut_bw = [
        0x40, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x40, 0x0A, 0x01, 0x00, 0x00, 0x01,
        0xA0, 0x0E, 0x0E, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    lut_wb = [
        0x80, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x80, 0x0A, 0x01, 0x00, 0x00, 0x01,
        0x50, 0x0E, 0x0E, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    lut_bb = [
        0x80, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x80, 0x0A, 0x01, 0x00, 0x00, 0x01,
        0x50, 0x0E, 0x0E, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # luts for partial screen updates

    partial_lut_vcom1 = [
        0x00, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00
    ]

    partial_lut_ww1 = [
        0x00, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    partial_lut_bw1 = [
        0x80, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    partial_lut_wb1 = [
        0x40, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    partial_lut_bb1 = [
        0x00, 0x19, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # gray

    # 0~3 gray
    gray_lut_vcom = [
        0x00, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x60, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x13, 0x0A, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    # R21
    gray_lut_ww = [
        0x40, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x10, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0xA0, 0x13, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # R22H	r
    gray_lut_bw = [
        0x40, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0x99, 0x0C, 0x01, 0x03, 0x04, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # R23H	w
    gray_lut_wb = [
        0x40, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0x99, 0x0B, 0x04, 0x04, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # R24H	b
    gray_lut_bb = [
        0x80, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x20, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0x50, 0x13, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    ############### all of these override existing methods, they are
    ############### implemented differently in the c file...

    def reset(self):
        self.digital_write(self.RST_PIN, 0x01)
        self.delay_ms(200)
        self.digital_write(self.RST_PIN, 0x00)
        self.delay_ms(200)
        self.digital_write(self.RST_PIN, 0x01)
        self.delay_ms(200)

    def send_command(self, command):
        self.digital_write(self.DC_PIN, 0x00)
        self.digital_write(self.CS_PIN, 0x00)
        self.spi_transfer([command])
        self.digital_write(self.CS_PIN, 0x01)

    def send_data(self, data):
        self.digital_write(self.DC_PIN, 0x01)
        self.digital_write(self.CS_PIN, 0x00)
        self.spi_transfer([data])
        self.digital_write(self.CS_PIN, 0x01)

    def wait_until_idle(self):
        self.send_command(0x71)
        while self.digital_read(self.BUSY_PIN) == 0:
            self.send_command(0x71)
            self.delay_ms(100)

    def turn_on_display(self):
        self.send_command(0x12)
        self.delay_ms(100)
        self.wait_until_idle()

    def full_set_lut(self):
        self.send_command(0x20)
        for i in range(0, len(self.lut_vcom0)):
            self.send_data(self.lut_vcom0[i])

        self.send_command(0x21)
        for i in range(0, len(self.lut_ww)):
            self.send_data(self.lut_ww[i])

        self.send_command(0x22)
        for i in range(0, len(self.lut_bw)):
            self.send_data(self.lut_bw[i])

        self.send_command(0x23)
        for i in range(0, len(self.lut_wb)):
            self.send_data(self.lut_wb[i])

        self.send_command(0x24)
        for i in range(0, len(self.lut_bb)):
            self.send_data(self.lut_bb[i])

    def partial_set_lut(self):
        self.send_command(0x20)
        for i in range(0, len(self.partial_lut_vcom1)):
            self.send_data(self.partial_lut_vcom1[i])

        self.send_command(0x21)
        for i in range(0, len(self.partial_lut_ww1)):
            self.send_data(self.partial_lut_ww1[i])

        self.send_command(0x22)
        for i in range(0, len(self.partial_lut_bw1)):
            self.send_data(self.partial_lut_bw1[i])

        self.send_command(0x23)
        for i in range(0, len(self.partial_lut_wb1)):
            self.send_data(self.partial_lut_wb1[i])

        self.send_command(0x24)
        for i in range(0, len(self.partial_lut_bb1)):
            self.send_data(self.partial_lut_bb1[i])

    def gray_set_lut(self):
        self.send_command(0x20)
        for i in range(0, len(self.gray_lut_vcom)):
            self.send_data(self.gray_lut_vcom[i])

        self.send_command(0x21)
        for i in range(0, len(self.gray_lut_ww)):
            self.send_data(self.gray_lut_ww[i])

        self.send_command(0x22)
        for i in range(0, len(self.gray_lut_bw)):
            self.send_data(self.gray_lut_bw[i])

        self.send_command(0x23)
        for i in range(0, len(self.gray_lut_wb)):
            self.send_data(self.gray_lut_wb[i])

        self.send_command(0x24)
        for i in range(0, len(self.gray_lut_bb)):
            self.send_data(self.gray_lut_bb[i])

    def init_full(self):
        self.reset()

        self.send_command(0x01)  # POWER SETTING
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)  # A
        self.send_data(0x17)  # B
        self.send_data(0x17)  # C

        self.send_command(0x04) # power on
        self.wait_until_idle()

        self.send_command(0x00)  # panel setting
        self.send_data(0xbf)  #  KW-BF   KWR-AF	BWROTP 0f	BWOTP 1f
        self.send_data(0x0d)

        self.send_command(0x30)  # PLL setting
        self.send_data(0x3c)  # 3a 100HZ   29 150Hz 39 200HZ	31 171HZ

        self.send_command(0x61)  # resolution setting
        self.send_data((self.width >> 8) & 0xff)
        self.send_data(self.width & 0xff)
        self.send_data((self.height >> 8) & 0xff)
        self.send_data(self.height & 0xff)

        self.send_command(0x82)  # vcom_DC setting
        self.send_data(0x28)

        self.send_command(0X50)			# VCOM AND DATA INTERVAL SETTING
        self.send_data(0x97) # WBmode:VBDF 17|D7 VBDW 97 VBDB 57		WBRmode:VBDF F7 VBDW 77 VBDB 37  VBDR B7

        self.full_set_lut()

    def init_gray(self):
        #### NOTE: This code is currently not being called.
        self.reset()

        self.send_command(0x01)  # POWER SETTING
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)
        self.send_data(0x13)

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)  # A
        self.send_data(0x17)  # B
        self.send_data(0x17)  # C

        self.send_command(0x04)
        self.wait_until_idle()

        self.send_command(0x00)  # panel setting
        self.send_data(0x3f)     # KW-3f   KWR-2F	BWROTP 0f	BWOTP 1f

        self.send_command(0x30)  # PLL setting
        self.send_data(0x3c)  # 3a 100HZ   29 150Hz 39 200HZ	31 171HZ

        self.send_command(0x61)  # resolution setting
        self.send_data((self.width >> 8) & 0xff)
        self.send_data(self.width & 0xff)
        self.send_data((self.height >> 8) & 0xff)
        self.send_data(self.height & 0xff)

        self.send_command(0x82)  # vcom_DC setting
        self.send_data(0x12)

        self.send_command(0X50)			#VCOM AND DATA INTERVAL SETTING
        self.send_data(0x97)		#WBmode:VBDF 17|D7 VBDW 97 VBDB 57		WBRmode:VBDF F7 VBDW 77 VBDB 37  VBDR B7

    def init(self, partial=True):
        self.partial_refresh = partial
        if self.epd_init() != 0:
            return -1
        self.init_full()

    def clear(self):
        width = int(self.width // 8 if self.width % 8 == 0 else self.width % 8 + 1)
        height = int(self.height)

        self.send_command(0x10)
        for j in range(height):
            for i in range(width):
                self.send_data(0xff)

        self.send_command(0x13)
        for j in range(height):
            for i in range(width):
                self.send_data(0xff)

        self.send_command(0x12) # Display refresh
        self.delay_ms(10)
        self.turn_on_display()

    def display_full(self, frame_buffer):
        if not frame_buffer:
            return

        width = int(self.width // 8 if self.width % 8 == 0 else self.width % 8 + 1)
        height = int(self.height)

        self.send_command(0x13)
        for j in range(height):
            for i in range(width):
                self.send_data(frame_buffer[i + j * width])

        self.turn_on_display()

    def display_partial(self, frame_buffer, x_start, y_start, x_end, y_end):
        if not frame_buffer:
            return

        width = int(self.width // 8 if self.width % 8 == 0 else self.width % 8 + 1)
        height = int(self.height)

        x_start = int(x_start if x_start % 8 == 0 else x_start // 8 * 8 + 8)
        x_end = int(x_end if x_end % 8 == 0 else x_end // 8 * 8 + 8)

        y_start = int(y_start)
        y_end = int(y_end)

        self.send_command(0x50)
        self.send_data(0xf7)
        self.delay_ms(100)

        self.send_command(0x82) #vcom_DC setting
        self.send_data(0x08)
        self.send_command(0X50)
        self.send_data(0x47)
        self.partial_set_lut()
        self.send_command(0x91)   # This command makes the display enter partial mode
        self.send_command(0x90)   # resolution setting
        self.send_data((x_start)//256)
        self.send_data((x_start) % 256)   # x-start

        self.send_data((x_end) // 256)
        self.send_data((x_end) % 256 - 1)   # x-end

        self.send_data(y_start // 256)
        self.send_data(y_start % 256)   # y-start

        self.send_data(y_end // 256)
        self.send_data(y_end % 256 - 1)   # y-end
        self.send_data(0x28)

        self.send_command(0x10)   # writes Old data to SRAM for programming
        for j in range(y_end - y_start):
            for i in range((x_end - x_start) // 8):
                self.send_data(frame_buffer[(y_start + j) * width + x_start // 8 + i])

        self.send_command(0x13)   # writes New data to SRAM.
        for j in range(y_end - y_start):
            for i in range((x_end - x_start) // 8):
                # there is an issue, because there are no unsigned values in
                # python, not sure if it matters though
                self.send_data(~frame_buffer[(y_start + j) * width + x_start // 8 + i])

        self.send_command(0x12)   # DISPLAY REFRESH
        self.delay_ms(10) # The delay here is necessary, 200uS at least!!!
        self.turn_on_display()

    def display_gray(self, frame_buffer):
        #### NOTE: This code is currently not being called.
        #### this is what the original source code says:
        # /****Color display description****
        #       white  gray1  gray2  black
        # 0x10|  01     01     00     00
        # 0x13|  01     00     01     00
        # *********************************/
        # 	EPD_4IN2_SendCommand(0x10);

        self.send_command(0x10)

        for m in range(self.height):
            for i in range(self.width // 8):
                temp3 = 0
                for j in range(2):
                    temp1 = frame_buffer[(m * (self.width // 8) + i) * 2 + j]
                    for k in range(2):
                        temp2 = temp1 & 0xC0
                        if temp2 == 0xC0:
                            temp3 |= 0x01 # white
                        elif temp2 == 0x00:
                            temp3 |= 0x00 # black
                        elif temp2 == 0x80:
                            temp3 |= 0x01 # gray1
                        else: # 0x40
                            temp3 |= 0x00 # gray2
                        temp3 <<= 1

                        temp1 <<= 2
                        temp2 = temp1 & 0xC0
                        if temp2 == 0xC0:  # white
                            temp3 |= 0x01
                        elif temp2 == 0x00: # black
                            temp3 |= 0x00
                        elif temp2 == 0x80:
                            temp3 |= 0x01 # gray1
                        else: # 0x40
                            temp3 |= 0x00 # gray2
                        if (j != 1) or (k != 1):
                            temp3 <<= 1

                        temp1 <<= 2
                    # end for k
                # end for j
                self.send_data(temp3)
            # end for i
        # end for m
        # new data
        self.send_command(0x13)

        for m in range(self.height):
            for i in range(self.width // 8):
                temp3 = 0
                for j in range(2):
                    temp1 = frame_buffer[(m * (self.width // 8) + i) * 2 + j]
                    for k in range(2):
                        temp2 = temp1 & 0xC0
                        if temp2 == 0xC0:
                            temp3 |= 0x01 # white
                        elif temp2 == 0x00:
                            temp3 |= 0x00 # black
                        elif temp2 == 0x80:
                            temp3 |= 0x00 # gray1
                        else: # 0x40
                            temp3 |= 0x01 # gray2
                        temp3 <<= 1

                        temp1 <<= 2
                        temp2 = temp1 & 0xC0
                        if temp2 == 0xC0:  # white
                            temp3 |= 0x01
                        elif temp2 == 0x00: # black
                            temp3 |= 0x00
                        elif temp2 == 0x80:
                            temp3 |= 0x00 # gray1
                        else:    # 0x40
                            temp3 |= 0x01	# gray2
                        if (j != 1) or (k != 1):
                            temp3 <<= 1

                        temp1 <<= 2
                    # end for k
                # end for j
                self.send_data(temp3)
            # end for i
        # end for m
        self.gray_set_lut()
        self.turn_on_display()

    def sleep(self):
        self.send_command(0x02) # power off
        self.wait_until_idle()
        self.send_command(0x07) # deep sleep
        self.send_data(0xa5)

    # the implementation in super() is probably buggy!!!
    def get_frame_buffer(self, image):
        buf = [0x00] * int(self.width * self.height / 8)
        # Set buffer to value of Python Imaging Library image.
        # Image must be in mode 1.
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        # if imwidth != self.width or imheight != self.height:
        #     raise ValueError('Image must be same dimensions as display \
        #         ({0}x{1}).'.format(self.width, self.height))

        pixels = image_monocolor.load()
        for y in range(imheight):
            for x in range(imwidth):
                # Set the bits for the column of pixels at the current position.
                if pixels[x, y] != 0:
                    buf[int((x + y * self.width) / 8)] |= 0x80 >> (x % 8)
        return buf

    def draw(self, x, y, image):
        """Replace a particular area on the display with an image"""
        if self.partial_refresh:
            self.display_partial(self.get_frame_buffer(image),
                                 x, y,
                                 x + image.width, x + image.height)
        else:
            self.display_full(self.get_frame_buffer(image))
