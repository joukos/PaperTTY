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

from abc import ABC, abstractmethod
from PIL import Image

import time

# if rpi libs are not found, don't care - hope that we don't end up
# using them
try:
    import spidev
    import RPi.GPIO as GPIO
except ImportError:
    pass


class DisplayDriver(ABC):
    """Abstract base class for a display driver - be it Waveshare e-Paper, PaPiRus, OLED..."""

    # override these if needed
    white = 255
    black = 0

    def __init__(self):
        super().__init__()
        self.name = None
        self.width = None
        self.height = None
        self.colors = None
        self.type = None
        self.supports_partial = None
        self.partial_refresh = None

    @abstractmethod
    def init(self, **kwargs):
        """Initialize the display"""
        pass

    @abstractmethod
    def draw(self, x, y, image):
        """Draw an image object on the display at (x,y)"""
        pass

    def scrub(self, fillsize=16):
        """Scrub display - only works properly with partial refresh"""
        if not self.supports_partial:
            raise RuntimeError("scrub only works properly with screens that have partial refresh support")
        self.fill(self.black, fillsize=fillsize)
        self.fill(self.white, fillsize=fillsize)

    def fill(self, color, fillsize):
        """Slow fill routine"""
        image = Image.new('1', (fillsize, self.height), color)
        for x in range(0, self.height, fillsize):
            self.draw(x, 0, image)

    def clear(self):
        """Clears the display"""
        image = Image.new('1', (self.height, self.width), self.black)
        self.draw(0, 0, image)
        image = Image.new('1', (self.height, self.width), self.white)
        self.draw(0, 0, image)

class SpecialDriver(DisplayDriver):
    """Drivers that don't control hardware"""
    default_width = 640
    default_height = 384

    def __init__(self, name, width, height):
        super().__init__()
        self.name = name
        self.width = width
        self.height = height
        self.type = 'Dummy display driver'

    @abstractmethod
    def init(self, **kwargs):
        pass

    @abstractmethod
    def draw(self, x, y, image):
        pass

    def scrub(self, fillsize=16):
        pass


class Dummy(SpecialDriver):
    """Dummy display driver - does not do anything"""

    def __init__(self):
        super().__init__(name='No-op driver', width=self.default_width, height=self.default_height)

    def init(self, **kwargs):
        pass

    def draw(self, x, y, image):
        pass


class Bitmap(SpecialDriver):
    """Output a bitmap for each frame - overwrite old ones"""

    def __init__(self, maxfiles=5, file_format="png"):
        super().__init__(name="Bitmap output driver", width=self.default_width, height=self.default_height, )
        self.maxfiles = maxfiles
        self.current_frame = 0
        self.frame_buffer = None
        self.file_format = file_format

    def init(self, **kwargs):
        self.frame_buffer = Image.new('1', (self.width, self.height), 255)
        self.current_frame = 0

    def draw(self, x, y, image):
        self.frame_buffer.paste(image, box=(x, y))
        self.frame_buffer.save("bitmap_frame_{}.{}".format(self.current_frame, self.file_format))
        self.current_frame = (self.current_frame + 1) % self.maxfiles


class WaveshareEPD(DisplayDriver):
    """Base class for Waveshare displays with common code for all - the 'epdif.py'
    - 1.54" , 1.54" B , 1.54" C
    - 2.13" , 2.13" B
    - 2.7"  , 2.7" B
    - 2.9"  , 2.9" B
    - 4.2"  , 4.2" B
    - 7.5"  , 7.5" B
    """

    # Common commands
    GET_STATUS = 0x71

    # These pins are common across all models
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24

    # Some models implement rotation in their code
    ROTATE_0 = 0x00
    ROTATE_90 = 0x01
    ROTATE_180 = 0x02
    ROTATE_270 = 0x03

    # SPI device, bus = 0, device = 0

    # SPI methods

    @staticmethod
    def epd_digital_write(pin, value):
        GPIO.output(pin, value)

    @staticmethod
    def epd_digital_read(pin):
        return GPIO.input(pin)

    @staticmethod
    def epd_delay_ms(delaytime):
        time.sleep(float(delaytime) / 1000.0)

    def spi_transfer(self, data):
        self.SPI.writebytes(data)

    def epd_init(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.RST_PIN, GPIO.OUT)
        GPIO.setup(self.DC_PIN, GPIO.OUT)
        GPIO.setup(self.CS_PIN, GPIO.OUT)
        GPIO.setup(self.BUSY_PIN, GPIO.IN)
        self.SPI = spidev.SpiDev(0, 0)
        self.SPI.max_speed_hz = 2000000
        self.SPI.mode = 0b00
        return 0

    # Basic functionality

    def __init__(self, name, width, height):
        super().__init__()
        self.name = name
        self.width = width
        self.height = height
        self.type = 'Waveshare e-Paper'

    def digital_write(self, pin, value):
        self.epd_digital_write(pin, value)

    def digital_read(self, pin):
        return self.epd_digital_read(pin)

    def delay_ms(self, delaytime):
        self.epd_delay_ms(delaytime)

    def send_command(self, command):
        self.digital_write(self.DC_PIN, GPIO.LOW)
        # the parameter type is list but not int
        # so use [command] instead of command
        self.spi_transfer([command])

    def send_data(self, data):
        self.digital_write(self.DC_PIN, GPIO.HIGH)
        # the parameter type is list but not int
        # so use [data] instead of data
        self.spi_transfer([data])

    def reset(self):
        self.digital_write(self.RST_PIN, GPIO.LOW)
        self.delay_ms(200)
        self.digital_write(self.RST_PIN, GPIO.HIGH)
        self.delay_ms(200)

    def init(self, **kwargs):
        pass

    def draw(self, x, y, image):
        pass
