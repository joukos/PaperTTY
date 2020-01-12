#     Copyright (c) 2020 Guido Kraemer
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

from drivers import drivers_partial

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

class EPD4in2(drivers_partial.WavesharePartial):
    """WaveShare 4.2" """

    # code adapted from  epd_4in2.c
    # https://github.com/waveshare/e-paper/blob/8973995e53cb78bac6d1f8a66c2d398c18392f71/raspberrypi%26jetsonnano/c/lib/e-paper/epd_4in2.c

    # note: this works differently (at least in the c code): there is a memory
    # buffer, the same size as the display. we partially refresh the memory
    # buffer with the image at a position and the do self.partial_refresh with
    # the entire memory buffer and the area to be refreshed.

    # note: this code is outside of drivers_partial.py because the class has to
    # override many methdos and therefore is way to long

    def __init__(self):
        super().__init__(name='4.2"', width=300, height=400)

        # this is the memory buffer that will be updated!
        self.frame_buffer = [0x00] * (self.width * self.height // 8)

    # constants
    lut_vcom0 = [
        0x00, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x00, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x00, 0x0a, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x0e, 0x0e, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
    ]

    lut_ww = [
        0x40, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x40, 0x0a, 0x01, 0x00, 0x00, 0x01,
        0xa0, 0x0e, 0x0e, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_bw = [
        0x40, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x40, 0x0a, 0x01, 0x00, 0x00, 0x01,
        0xa0, 0x0e, 0x0e, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_wb = [
        0x80, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x80, 0x0a, 0x01, 0x00, 0x00, 0x01,
        0x50, 0x0e, 0x0e, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_bb = [
        0x80, 0x17, 0x00, 0x00, 0x00, 0x02,
        0x90, 0x17, 0x17, 0x00, 0x00, 0x02,
        0x80, 0x0a, 0x01, 0x00, 0x00, 0x01,
        0x50, 0x0e, 0x0e, 0x00, 0x00, 0x02,
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
        0x00, 0x0a, 0x00, 0x00, 0x00, 0x01,
        0x60, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x13, 0x0a, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    # r21
    gray_lut_ww = [
        0x40, 0x0a, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x10, 0x14, 0x0a, 0x00, 0x00, 0x01,
        0xa0, 0x13, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # r22h	r
    gray_lut_bw = [
        0x40, 0x0a, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x0a, 0x00, 0x00, 0x01,
        0x99, 0x0c, 0x01, 0x03, 0x04, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # r23h	w
    gray_lut_wb = [
        0x40, 0x0a, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x0a, 0x00, 0x00, 0x01,
        0x99, 0x0b, 0x04, 0x04, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # r24h	b
    gray_lut_bb = [
        0x80, 0x0a, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x20, 0x14, 0x0a, 0x00, 0x00, 0x01,
        0x50, 0x13, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # all of these override existing methods, they are
    # implemented differently in the c file...

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

        self.send_command(0x01)  # power setting
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)  # a
        self.send_data(0x17)  # b
        self.send_data(0x17)  # c

        self.send_command(0x04)  # power on
        self.wait_until_idle()

        self.send_command(0x00)  # panel setting
        self.send_data(0xbf)  # kw-bf kwr-af bwrotp 0f bwotp 1f
        self.send_data(0x0d)

        self.send_command(0x30)  # pll setting
        self.send_data(0x3c)  # 3a 100hz   29 150hz 39 200hz	31 171hz

        self.send_command(0x61)  # resolution setting
        self.send_data((self.width >> 8) & 0xff)
        self.send_data(self.width & 0xff)
        self.send_data((self.height >> 8) & 0xff)
        self.send_data(self.height & 0xff)

        self.send_command(0x82)  # vcom_dc setting
        self.send_data(0x28)

        self.send_command(0x50)			# vcom and data interval setting
        # wbmode:vbdf 17|d7 vbdw 97 vbdb 57 wbrmode:vbdf f7 vbdw 77 vbdb 37
        # vbdr b7
        self.send_data(0x97)

        self.full_set_lut()

    def init_gray(self):
        # note: this code is currently not being called.
        self.reset()

        self.send_command(0x01)  # power setting
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)
        self.send_data(0x13)

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)  # a
        self.send_data(0x17)  # b
        self.send_data(0x17)  # c

        self.send_command(0x04)
        self.wait_until_idle()

        self.send_command(0x00)  # panel setting
        self.send_data(0x3f)     # kw-3f   kwr-2f	bwrotp 0f	bwotp 1f

        self.send_command(0x30)  # pll setting
        self.send_data(0x3c)  # 3a 100hz   29 150hz 39 200hz	31 171hz

        self.send_command(0x61)  # resolution setting
        self.send_data((self.width >> 8) & 0xff)
        self.send_data(self.width & 0xff)
        self.send_data((self.height >> 8) & 0xff)
        self.send_data(self.height & 0xff)

        self.send_command(0x82)  # vcom_dc setting
        self.send_data(0x12)

        self.send_command(0x50)			# vcom and data interval setting
        # wbmode:vbdf 17|d7 vbdw 97 vbdb 57 wbrmode:vbdf f7 vbdw 77 vbdb 37
        # vbdr b7
        self.send_data(0x97)

    def init(self, partial=True):
        self.partial_refresh = partial
        if self.epd_init() != 0:
            return -1
        self.init_full()

    def clear(self):
        width = int(self.width // 8
                    if self.width % 8 == 0
                    else self.width % 8 + 1)
        height = int(self.height)

        self.send_command(0x10)
        for j in range(height):
            for i in range(width):
                self.send_data(0xff)

        self.send_command(0x13)
        for j in range(height):
            for i in range(width):
                self.send_data(0xff)

        self.send_command(0x12)  # display refresh
        self.delay_ms(10)
        self.turn_on_display()

    def display_full(self, frame_buffer):
        if not frame_buffer:
            return

        width = int(self.width // 8
                    if self.width % 8 == 0
                    else self.width % 8 + 1)
        height = int(self.height)

        self.send_command(0x13)
        for j in range(height):
            for i in range(width):
                self.send_data(frame_buffer[i + j * width])

        self.turn_on_display()

    # def display_partial(self, x_start, y_start, x_end, y_end):

    #     width = int(self.width // 8
    #                 if self.width % 8 == 0
    #                 else self.width % 8 + 1)
    #     # height = int(self.height)

    #     x_start = int(x_start if x_start % 8 == 0 else x_start // 8 * 8 + 8)
    #     x_end = int(x_end if x_end % 8 == 0 else x_end // 8 * 8 + 8)

    #     y_start = int(y_start)
    #     y_end = int(y_end)

    #     self.send_command(0x50)
    #     self.send_data(0xf7)
    #     self.delay_ms(100)

    #     self.send_command(0x82)  # vcom_dc setting
    #     self.send_data(0x08)
    #     self.send_command(0x50)
    #     self.send_data(0x47)
    #     self.partial_set_lut()
    #     # this command makes the display enter partial mode
    #     self.send_command(0x91)
    #     self.send_command(0x90)   # resolution setting
    #     self.send_data((x_start)//256)
    #     self.send_data((x_start) % 256)   # x-start

    #     self.send_data((x_end) // 256)
    #     self.send_data((x_end) % 256 - 1)   # x-end

    #     self.send_data(y_start // 256)
    #     self.send_data(y_start % 256)   # y-start

    #     self.send_data(y_end // 256)
    #     self.send_data(y_end % 256 - 1)   # y-end
    #     self.send_data(0x28)

    #     self.send_command(0x10)   # writes old data to sram for programming
    #     for j in range(y_end - y_start):
    #         for i in range((x_end - x_start) // 8):
    #             self.send_data(self.frame_buffer[
    #                 (y_start + j) * width + x_start // 8 + i
    #             ])

    #     self.send_command(0x13)   # writes new data to sram.
    #     for j in range(y_end - y_start):
    #         for i in range((x_end - x_start) // 8):
    #             # there is an issue, because there are no unsigned values in
    #             # python, not sure if it matters though
    #             self.send_data(~self.frame_buffer[
    #                 (y_start + j) * width + x_start // 8 + i
    #             ])

    #     self.send_command(0x12)   # display refresh
    #     self.delay_ms(10)  # the delay here is necessary, 200us at least!!!
    #     self.turn_on_display()

    def display_partial(self, x_start, y_start, x_end, y_end):

        # width = int(self.width)
        height = int(self.height // 8
                     if self.height % 8 == 0
                     else self.height % 8 + 1)

        x_start = int(x_start if x_start % 8 == 0 else x_start // 8 * 8 + 8)
        x_end = int(x_end if x_end % 8 == 0 else x_end // 8 * 8 + 8)

        y_start = int(y_start)
        y_end = int(y_end)

        self.send_command(0x50)
        self.send_data(0xf7)
        self.delay_ms(100)

        self.send_command(0x82)  # vcom_dc setting
        self.send_data(0x08)
        self.send_command(0x50)
        self.send_data(0x47)
        self.partial_set_lut()
        # this command makes the display enter partial mode
        self.send_command(0x91)
        self.send_command(0x90)   # resolution setting
        self.send_data(x_start//256)
        self.send_data(x_start % 256)   # x-start

        self.send_data(x_end // 256)
        self.send_data(x_end % 256 - 1)   # x-end

        self.send_data(y_start // 256)
        self.send_data(y_start % 256)   # y-start

        self.send_data(y_end // 256)
        self.send_data(y_end % 256 - 1)   # y-end
        self.send_data(0x28)

        self.send_command(0x10)   # writes old data to sram for programming
        for j in range(y_end - y_start):
            idx = (y_start + j) * height + x_start // 8
            for i in range((x_end - x_start) // 8):
                self.send_data(self.frame_buffer[idx + i])

        self.send_command(0x13)   # writes new data to sram.
        for j in range(y_end - y_start):
            idx = (y_start + j) * height + x_start // 8
            for i in range((x_end - x_start) // 8):
                self.send_data(~self.frame_buffer[idx + i])

        self.send_command(0x12)   # display refresh
        self.delay_ms(10)  # the delay here is necessary, 200us at least!!!
        self.turn_on_display()

    # def display_gray(self, frame_buffer):
    #     # note: this code is currently not being called.
    #     # this is what the original source code says:

    #     # /****color display description****
    #     #       white  gray1  gray2  black
    #     # 0x10|  01     01     00     00
    #     # 0x13|  01     00     01     00
    #     # *********************************/
    #     # 	epd_4in2_sendcommand(0x10);

    #     self.send_command(0x10)

    #     for m in range(self.height):
    #         for i in range(self.width // 8):
    #             temp3 = 0
    #             for j in range(2):
    #                 temp1 = frame_buffer[(m * (self.width // 8) + i) * 2 + j]
    #                 for k in range(2):
    #                     temp2 = temp1 & 0xc0
    #                     if temp2 == 0xc0:
    #                         temp3 |= 0x01  # white
    #                     elif temp2 == 0x00:
    #                         temp3 |= 0x00  # black
    #                     elif temp2 == 0x80:
    #                         temp3 |= 0x01  # gray1
    #                     else:  # 0x40
    #                         temp3 |= 0x00  # gray2
    #                     temp3 <<= 1

    #                     temp1 <<= 2
    #                     temp2 = temp1 & 0xc0
    #                     if temp2 == 0xc0:  # white
    #                         temp3 |= 0x01
    #                     elif temp2 == 0x00:  # black
    #                         temp3 |= 0x00
    #                     elif temp2 == 0x80:
    #                         temp3 |= 0x01  # gray1
    #                     else:  # 0x40
    #                         temp3 |= 0x00  # gray2
    #                     if (j != 1) or (k != 1):
    #                         temp3 <<= 1

    #                     temp1 <<= 2
    #                 # end for k
    #             # end for j
    #             self.send_data(temp3)
    #         # end for i
    #     # end for m
    #     # new data
    #     self.send_command(0x13)

    #     for m in range(self.height):
    #         for i in range(self.width // 8):
    #             temp3 = 0
    #             for j in range(2):
    #                 temp1 = frame_buffer[(m * (self.width // 8) + i) * 2 + j]
    #                 for k in range(2):
    #                     temp2 = temp1 & 0xc0
    #                     if temp2 == 0xc0:
    #                         temp3 |= 0x01  # white
    #                     elif temp2 == 0x00:
    #                         temp3 |= 0x00  # black
    #                     elif temp2 == 0x80:
    #                         temp3 |= 0x00  # gray1
    #                     else:  # 0x40
    #                         temp3 |= 0x01  # gray2
    #                     temp3 <<= 1

    #                     temp1 <<= 2
    #                     temp2 = temp1 & 0xc0
    #                     if temp2 == 0xc0:  # white
    #                         temp3 |= 0x01
    #                     elif temp2 == 0x00:  # black
    #                         temp3 |= 0x00
    #                     elif temp2 == 0x80:
    #                         temp3 |= 0x00  # gray1
    #                     else:  # 0x40
    #                         temp3 |= 0x01  # gray2
    #                     if (j != 1) or (k != 1):
    #                         temp3 <<= 1

    #                     temp1 <<= 2
    #                 # end for k
    #             # end for j
    #             self.send_data(temp3)
    #         # end for i
    #     # end for m
    #     self.gray_set_lut()
    #     self.turn_on_display()

    def sleep(self):
        self.send_command(0x02)  # power off
        self.wait_until_idle()
        self.send_command(0x07)  # deep sleep
        self.send_data(0xa5)

    def set_frame_buffer(self, x, y, image):

        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()

        for j in range(y, y + imwidth):
            idxj = j * self.height // 8
            for i in range(x, x + imheight):
                idiv = i // 8
                irem = i % 8
                mask = 0x01 << (7 - irem)
                if pixels[j - y, i - x] != 0:
                    self.frame_buffer[idiv + idxj] |= mask
                else:
                    self.frame_buffer[idiv + idxj] &= ~mask

    def fill(self, color, fillsize):
        """slow fill routine"""
        image = Image.new('1', (fillsize, self.height), color)
        for y in range(0, self.width, fillsize):
            self.draw(0, y, image)

    ### The original fill method:
    # def fill(self, color, fillsize):
    #     """Slow fill routine"""
    #     image = Image.new('1', (fillsize, self.height), color)
    #     for x in range(0, self.height, fillsize):
    #         self.draw(x, 0, image)

    def draw(self, x, y, image):
        """replace a particular area on the display with an image"""

        # print("=====================================")
        # print("x: ", x)
        # print("y: ", y)
        # print("image.width:", image.width)
        # print("image.height:", image.height)
        # print("self.width: ", self.width)
        # print("self.height:", self.height)

        if self.partial_refresh:
            # self.set_frame_buffer(x, y, image)
            # self.display_partial(x, y, x + image.height, y + image.width)
            self.set_frame_buffer(y, x, image)
            self.display_partial(y, x, y + image.height, x + image.width)
        else:
            self.set_frame_buffer(0, 0, image)
            self.display_full()
