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
        self.set_frame_memory(image, x, y)
        self.display_frame()


class EPD1in54(WavesharePartial):
    """Waveshare 1.54" monochrome"""

    def __init__(self):
        super().__init__(name='1.54" BW', width=200, height=200)


class EPD2in13(WavesharePartial):
    """Waveshare 2.13" monochrome"""

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


class EPD2in9(WavesharePartial):
    """Waveshare 2.9" monochrome"""

    def __init__(self):
        super().__init__(name='2.9" BW', width=128, height=296)
