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

from PIL import Image, ImageDraw

from papertty.drivers.drivers_color import WaveshareColor


class WaveshareColorDraw(WaveshareColor):
    """Class for displays that have (mostly shared) special implementations of some drawing methods. This includes:
    - 1.54" B
    - 1.54" C
    - 2.13" B
    - 2.7" B
    - 2.9" B
    
    """

    ACTIVE_PROGRAM = 0xA1
    DATA_START_TRANSMISSION_2 = 0x13
    PROGRAM_MODE = 0xA0
    READ_OTP_DATA = 0xA2
    VCOM_VALUE = 0x81

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.colors = 3
        self.rotate = self.ROTATE_0
        # the rotation aware algorithms refer to and swap the screen dimensions, so set them here
        self.EPD_WIDTH = kwargs['width']
        self.EPD_HEIGHT = kwargs['height']

    # EPD1in54b and EPD1in54c use 0x17
    # EPD2in13b and EPD2in9b use 0x37
    # EPD2in7b has a simpler sleep
    def sleep(self, sleepbyte=0x17):
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(sleepbyte)
        self.send_command(self.VCM_DC_SETTING)  # to solve Vcom drop
        self.send_data(0x00)
        self.send_command(self.POWER_SETTING)  # power setting
        self.send_data(0x02)  # gate switch to external
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_data(0x00)
        self.wait_until_idle()
        self.send_command(self.POWER_OFF)  # power off

    def set_rotate(self, rotate):
        if rotate == self.ROTATE_0:
            self.rotate = self.ROTATE_0
            self.width = self.EPD_WIDTH
            self.height = self.EPD_HEIGHT
        elif rotate == self.ROTATE_90:
            self.rotate = self.ROTATE_90
            self.width = self.EPD_HEIGHT
            self.height = self.EPD_WIDTH
        elif rotate == self.ROTATE_180:
            self.rotate = self.ROTATE_180
            self.width = self.EPD_WIDTH
            self.height = self.EPD_HEIGHT
        elif rotate == self.ROTATE_270:
            self.rotate = self.ROTATE_270
            self.width = self.EPD_HEIGHT
            self.height = self.EPD_WIDTH

    # this variant is for EPD1in54c, EPD2in13b and EPD2in9b - EPD1in54b and EPD2in7b override it
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

    # for EPD154* - override elsewhere
    def set_lut_bw(self):
        self.send_command(0x20)  # vcom
        for count in range(0, 15):
            self.send_data(self.lut_vcom0[count])
        self.send_command(0x21)  # ww --
        for count in range(0, 15):
            self.send_data(self.lut_w[count])
        self.send_command(0x22)  # bw r
        for count in range(0, 15):
            self.send_data(self.lut_b[count])
        self.send_command(0x23)  # wb w
        for count in range(0, 15):
            self.send_data(self.lut_g1[count])
        self.send_command(0x24)  # bb b
        for count in range(0, 15):
            self.send_data(self.lut_g2[count])

    # for EPD154* - override elsewhere
    def set_lut_red(self):
        self.send_command(0x25)
        for count in range(0, 15):
            self.send_data(self.lut_vcom1[count])
        self.send_command(0x26)
        for count in range(0, 15):
            self.send_data(self.lut_red0[count])
        self.send_command(0x27)
        for count in range(0, 15):
            self.send_data(self.lut_red1[count])

    # these LUTs are for EPD154* - override in 2.7"
    lut_vcom0 = [
        0x0E, 0x14, 0x01, 0x0A, 0x06, 0x04, 0x0A, 0x0A,
        0x0F, 0x03, 0x03, 0x0C, 0x06, 0x0A, 0x00
    ]

    lut_w = [
        0x0E, 0x14, 0x01, 0x0A, 0x46, 0x04, 0x8A, 0x4A,
        0x0F, 0x83, 0x43, 0x0C, 0x86, 0x0A, 0x04
    ]

    lut_b = [
        0x0E, 0x14, 0x01, 0x8A, 0x06, 0x04, 0x8A, 0x4A,
        0x0F, 0x83, 0x43, 0x0C, 0x06, 0x4A, 0x04
    ]

    lut_g1 = [
        0x8E, 0x94, 0x01, 0x8A, 0x06, 0x04, 0x8A, 0x4A,
        0x0F, 0x83, 0x43, 0x0C, 0x06, 0x0A, 0x04
    ]

    lut_g2 = [
        0x8E, 0x94, 0x01, 0x8A, 0x06, 0x04, 0x8A, 0x4A,
        0x0F, 0x83, 0x43, 0x0C, 0x06, 0x0A, 0x04
    ]

    lut_vcom1 = [
        0x03, 0x1D, 0x01, 0x01, 0x08, 0x23, 0x37, 0x37,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    lut_red0 = [
        0x83, 0x5D, 0x01, 0x81, 0x48, 0x23, 0x77, 0x77,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    lut_red1 = [
        0x03, 0x1D, 0x01, 0x01, 0x08, 0x23, 0x37, 0x37,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    def set_pixel(self, frame_buffer, x, y, colored):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        if self.rotate == self.ROTATE_0:
            self.set_absolute_pixel(frame_buffer, x, y, colored)
        elif self.rotate == self.ROTATE_90:
            point_temp = x
            x = self.EPD_WIDTH - y
            y = point_temp
            self.set_absolute_pixel(frame_buffer, x, y, colored)
        elif self.rotate == self.ROTATE_180:
            x = self.EPD_WIDTH - x
            y = self.EPD_HEIGHT - y
            self.set_absolute_pixel(frame_buffer, x, y, colored)
        elif self.rotate == self.ROTATE_270:
            point_temp = x
            x = y
            y = self.EPD_HEIGHT - point_temp
            self.set_absolute_pixel(frame_buffer, x, y, colored)

    # overridden in EPD2in7b
    def set_absolute_pixel(self, frame_buffer, x, y, colored, reverse=False):
        # To avoid display orientation effects
        # use EPD_WIDTH instead of self.width
        # use EPD_HEIGHT instead of self.height
        if x < 0 or x >= self.EPD_WIDTH or y < 0 or y >= self.EPD_HEIGHT:
            return
        if not colored if reverse else colored:
            frame_buffer[(x + y * self.EPD_WIDTH) / 8] &= ~(0x80 >> (x % 8))
        else:
            frame_buffer[(x + y * self.EPD_WIDTH) / 8] |= 0x80 >> (x % 8)

    def draw_circle(self, frame_buffer, x, y, radius, colored):
        # Bresenham algorithm
        x_pos = -radius
        y_pos = 0
        err = 2 - 2 * radius
        if x >= self.width or y >= self.height:
            return
        while True:
            self.set_pixel(frame_buffer, x - x_pos, y + y_pos, colored)
            self.set_pixel(frame_buffer, x + x_pos, y + y_pos, colored)
            self.set_pixel(frame_buffer, x + x_pos, y - y_pos, colored)
            self.set_pixel(frame_buffer, x - x_pos, y - y_pos, colored)
            e2 = err
            if e2 <= y_pos:
                y_pos += 1
                err += y_pos * 2 + 1
                if -x_pos == y_pos and e2 <= x_pos:
                    e2 = 0
            if e2 > x_pos:
                x_pos += 1
                err += x_pos * 2 + 1
            if x_pos > 0:
                break

    # this only appears in EPD1in54b and EPD1in54c source
    def display_string_at(self, frame_buffer, x, y, text, font, colored):
        image = Image.new('1', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        draw.text((x, y), text, font=font, fill=255)
        # Set buffer to value of Python Imaging Library image.
        # Image must be in mode 1.
        pixels = image.load()
        for y in range(self.height):
            for x in range(self.width):
                # Set the bits for the column of pixels at the current position.
                if pixels[x, y] != 0:
                    self.set_pixel(frame_buffer, x, y, colored)

    # this, on the other hand, appears in the EPD2in7b source - same method, different name
    def draw_string_at(self, frame_buffer, x, y, text, font, colored):
        self.display_string_at(frame_buffer, x, y, text, font, colored)

    def draw_line(self, frame_buffer, x0, y0, x1, y1, colored):
        # Bresenham algorithm
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while (x0 != x1) and (y0 != y1):
            self.set_pixel(frame_buffer, x0, y0, colored)
            if 2 * err >= dy:
                err += dy
                x0 += sx
            if 2 * err <= dx:
                err += dx
                y0 += sy

    def draw_horizontal_line(self, frame_buffer, x, y, width, colored):
        for i in range(x, x + width):
            self.set_pixel(frame_buffer, i, y, colored)

    def draw_vertical_line(self, frame_buffer, x, y, height, colored):
        for i in range(y, y + height):
            self.set_pixel(frame_buffer, x, i, colored)

    def draw_rectangle(self, frame_buffer, x0, y0, x1, y1, colored):
        min_x = x0 if x1 > x0 else x1
        max_x = x1 if x1 > x0 else x0
        min_y = y0 if y1 > y0 else y1
        max_y = y1 if y1 > y0 else y0
        self.draw_horizontal_line(frame_buffer, min_x, min_y, max_x - min_x + 1, colored)
        self.draw_horizontal_line(frame_buffer, min_x, max_y, max_x - min_x + 1, colored)
        self.draw_vertical_line(frame_buffer, min_x, min_y, max_y - min_y + 1, colored)
        self.draw_vertical_line(frame_buffer, max_x, min_y, max_y - min_y + 1, colored)

    def draw_filled_rectangle(self, frame_buffer, x0, y0, x1, y1, colored):
        min_x = x0 if x1 > x0 else x1
        max_x = x1 if x1 > x0 else x0
        min_y = y0 if y1 > y0 else y1
        max_y = y1 if y1 > y0 else y0
        for i in range(min_x, max_x + 1):
            self.draw_vertical_line(frame_buffer, i, min_y, max_y - min_y + 1, colored)

    def draw_filled_circle(self, frame_buffer, x, y, radius, colored):
        # Bresenham algorithm
        x_pos = -radius
        y_pos = 0
        err = 2 - 2 * radius
        if x >= self.width or y >= self.height:
            return
        while True:
            self.set_pixel(frame_buffer, x - x_pos, y + y_pos, colored)
            self.set_pixel(frame_buffer, x + x_pos, y + y_pos, colored)
            self.set_pixel(frame_buffer, x + x_pos, y - y_pos, colored)
            self.set_pixel(frame_buffer, x - x_pos, y - y_pos, colored)
            self.draw_horizontal_line(frame_buffer, x + x_pos, y + y_pos, 2 * (-x_pos) + 1, colored)
            self.draw_horizontal_line(frame_buffer, x + x_pos, y - y_pos, 2 * (-x_pos) + 1, colored)
            e2 = err
            if e2 <= y_pos:
                y_pos += 1
                err += y_pos * 2 + 1
                if -x_pos == y_pos and e2 <= x_pos:
                    e2 = 0
            if e2 > x_pos:
                x_pos += 1
                err += x_pos * 2 + 1
            if x_pos > 0:
                break


class EPD1in54b(WaveshareColorDraw):
    """Waveshare 1.54" B - black / white / red"""

    SOURCE_AND_GATE_START_SETTING = 0x62
    TCON_RESOLUTION = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x41

    def __init__(self):
        super().__init__(name='1.54" B', width=200, height=200)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.POWER_SETTING)
        self.send_data(0x07)
        self.send_data(0x00)
        self.send_data(0x08)
        self.send_data(0x00)
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0x07)
        self.send_data(0x07)
        self.send_data(0x07)
        self.send_command(self.POWER_ON)

        self.wait_until_idle()

        self.send_command(self.PANEL_SETTING)
        self.send_data(0xCF)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x17)
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x39)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0xC8)
        self.send_data(0x00)
        self.send_data(0xC8)
        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x0E)

        self.set_lut_bw()
        self.set_lut_red()
        return 0

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)

    def display_frame(self, frame_buffer_black, *args):
        frame_buffer_red = args[0] if args else None
        if frame_buffer_black:
            self.send_command(self.DATA_START_TRANSMISSION_1)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                temp = 0x00
                for bit in range(0, 4):
                    if frame_buffer_black[i] & (0x80 >> bit) != 0:
                        temp |= 0xC0 >> (bit * 2)
                self.send_data(temp)
                temp = 0x00
                for bit in range(4, 8):
                    if frame_buffer_black[i] & (0x80 >> bit) != 0:
                        temp |= 0xC0 >> ((bit - 4) * 2)
                self.send_data(temp)
            self.delay_ms(2)
        if frame_buffer_red:
            self.send_command(self.DATA_START_TRANSMISSION_2)
            self.delay_ms(2)
            for i in range(0, int(self.width * self.height / 8)):
                self.send_data(frame_buffer_red[i])
            self.delay_ms(2)

        self.send_command(self.DISPLAY_REFRESH)
        self.wait_until_idle()


class EPD1in54c(WaveshareColorDraw):
    """Waveshare 1.54" C - black / white / yellow"""

    SOURCE_AND_GATE_START_SETTING = 0x62
    TCON_RESOLUTION = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x41

    def __init__(self):
        super().__init__(name='1.54" C', width=152, height=152)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.POWER_SETTING)
        self.send_data(0x07)
        self.send_data(0x00)
        self.send_data(0x08)
        self.send_data(0x00)
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_command(self.POWER_ON)

        self.wait_until_idle()

        self.send_command(self.PANEL_SETTING)
        self.send_data(0x0F)
        self.send_data(0x0D)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x77)
        self.send_command(self.PLL_CONTROL)
        self.send_data(0x39)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x98)
        self.send_data(0x00)
        self.send_data(0x98)
        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x0E)

        self.set_lut_bw()
        self.set_lut_red()
        return 0

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)


class EPD2in13b(WaveshareColorDraw):
    """Waveshare 2.13" B - black / white / red"""

    B2B_LUT = 0x24
    B2W_LUT = 0x22
    PARTIAL_IN = 0x91
    PARTIAL_OUT = 0x92
    PARTIAL_WINDOW = 0x90
    POWER_SAVING = 0xE3
    RESOLUTION_SETTING = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x40
    TEMPERATURE_SENSOR_SELECTION = 0x41
    VCOM_LUT = 0x20
    W2B_LUT = 0x23
    W2W_LUT = 0x21

    def __init__(self):
        super().__init__(name='2.13" B', width=104, height=212)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_command(self.POWER_ON)
        self.wait_until_idle()
        self.send_command(self.PANEL_SETTING)
        self.send_data(0x8F)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x37)
        self.send_command(self.RESOLUTION_SETTING)
        self.send_data(0x68)
        self.send_data(0x00)
        self.send_data(0xD4)

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)

    def sleep(self, sleepbyte=0x37):
        super().sleep(sleepbyte=sleepbyte)


class EPD2in7b(WaveshareColorDraw):
    """Waveshare 2.7" B - black / white / red"""

    LUT_BLACK_TO_BLACK = 0x24
    LUT_BLACK_TO_WHITE = 0x22
    LUT_WHITE_TO_BLACK = 0x23
    LUT_WHITE_TO_WHITE = 0x21
    PARTIAL_DATA_START_TRANSMISSION_1 = 0x14
    PARTIAL_DATA_START_TRANSMISSION_2 = 0x15
    PARTIAL_DISPLAY_REFRESH = 0x16
    SOURCE_AND_GATE_START_SETTING = 0x62
    TCON_RESOLUTION = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x41

    lut_vcom_dc = [
        0x00, 0x00,
        0x00, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x00, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x00, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    # R21H
    lut_ww = [
        0x90, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x40, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x80, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    # R22H    r
    lut_bw = [
        0xA0, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x00, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x90, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0xB0, 0x04, 0x10, 0x00, 0x00, 0x05,
        0xB0, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0xC0, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    # R23H    w
    lut_bb = [
        0x90, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x40, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x80, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    # R24H    b
    lut_wb = [
        0x90, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x20, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x10, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    def __init__(self):
        super().__init__(name='2.7" B', width=176, height=264)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()

        self.send_command(self.POWER_ON)
        self.wait_until_idle()

        self.send_command(self.PANEL_SETTING)
        self.send_data(0xaf)  # KW-BF   KWR-AF    BWROTP 0f

        self.send_command(self.PLL_CONTROL)
        self.send_data(0x3a)  # 3A 100HZ   29 150Hz 39 200HZ    31 171HZ

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
        self.send_data(0x73)
        self.send_data(0x41)

        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x12)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x87)  # define by OTP

        self.set_lut()

        self.send_command(self.PARTIAL_DISPLAY_REFRESH)
        self.send_data(0x00)

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

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)

    def display_frame(self, frame_buffer_black, *args):
        frame_buffer_red = args[0] if args else None
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(self.EPD_WIDTH >> 8)
        self.send_data(self.EPD_WIDTH & 0xff)  # 176
        self.send_data(self.EPD_HEIGHT >> 8)
        self.send_data(self.EPD_HEIGHT & 0xff)  # 264

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

    def set_absolute_pixel(self, frame_buffer, x, y, colored, reverse=True):
        super().set_absolute_pixel(frame_buffer, x, y, colored, reverse=reverse)

    # After this command is transmitted, the chip would enter the deep-sleep
    # mode to save power. The deep sleep mode would return to standby by
    # hardware reset. The only one parameter is a check code, the command would
    # be executed if check code = 0xA5.
    # Use EPD::Reset() to awaken and use EPD::Init() to initialize.
    def sleep(self, sleepbyte=None):
        self.send_command(self.DEEP_SLEEP)
        self.send_data(0xa5)


class EPD2in9b(WaveshareColorDraw):
    """Waveshare 2.9" B - black / white / red"""

    PARTIAL_IN = 0x91
    PARTIAL_OUT = 0x92
    PARTIAL_WINDOW = 0x90
    POWER_SAVING = 0xE3
    TCON_RESOLUTION = 0x61
    TEMPERATURE_SENSOR_CALIBRATION = 0x41

    def __init__(self):
        super().__init__(name='2.9" B', width=128, height=296)

    def init(self, **kwargs):
        if self.epd_init() != 0:
            return -1
        self.reset()
        self.send_command(self.BOOSTER_SOFT_START)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_command(self.POWER_ON)
        self.wait_until_idle()
        self.send_command(self.PANEL_SETTING)
        self.send_data(0x8F)
        self.send_command(self.VCOM_AND_DATA_INTERVAL_SETTING)
        self.send_data(0x77)
        self.send_command(self.TCON_RESOLUTION)
        self.send_data(0x80)
        self.send_data(0x01)
        self.send_data(0x28)
        self.send_command(self.VCM_DC_SETTING)
        self.send_data(0x0A)

    def get_frame_buffer(self, image, reverse=True):
        super().get_frame_buffer(image, reverse=reverse)

    def sleep(self, sleepbyte=0x37):
        super().sleep(sleepbyte=sleepbyte)
