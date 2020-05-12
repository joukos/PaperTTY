# Display drivers for PaperTTY

**Important note**: **while the PaperTTY program itself is in the public domain (CC0)**, these drivers are based on Waveshare's reference drivers (https://github.com/soonuse/epd-library-python) which are licensed under GPL 3.0 (*the files in the repo also contain MIT and BSD license notices, but I verified with Waveshare that GPL is intended*).

**Thus, the files in this `drivers` directory respect Waveshare's license and are also GPL 3.0 licensed.**

### Supported SPI displays

All of the SPI displays listed on the Waveshare Wiki at the time of writing are supported.

**Nothing is guaranteed - I don't own the hardware to test all of these. Use at your own risk!**

- **Supported models (SPI)**
  - **EPD 1.54" (monochrome) - [probably works, with partial refresh]**
  - **EPD 1.54" B (black/white/red)**
  - **EPD 1.54" C (black/white/yellow)**
  - **EPD 2.13" (monochrome) - [TESTED, with partial refresh]** 
  - **EPD 2.13" B (black/white/red)**
  - **EPD 2.13" C (black/white/yellow)** - should work with `EPD2in13b`
  - **EPD 2.13" D (monochrome, flexible)**
  - **EPD 2.13" v2 (only full refresh)**
  - **EPD 2.7" (monochrome)**
  - **EPD 2.7" B (black/white/red)**
  - **EPD 2.9" (monochrome) - [probably works, with partial refresh]**
  - **EPD 2.9" B (black/white/red)**
  - **EPD 2.9" C (black/white/yellow)** - should work with `EPD2in9b`
  - **EPD 4.2" (monochrome)** [TESTED, with partial refresh]
  - **EPD 4.2" B (black/white/red)**
  - **EPD 4.2" C (black/white/yellow)** - should work with `EPD4in2b`
  - **EPD 5.83" (monochrome)**
  - **EPD 5.83" B (black/white/red)**
  - **EPD 5.83" C (black/white/yellow)**
  - **EPD 7.5" (monochrome)**
  - **EPD 7.5" (monochrome, GDEW075T7, only full refresh)**
  - **EPD 7.5" B (black/white/red)**
  - **EPD 7.5" C (black/white/yellow)** - should work with `EPD7in5b`
  - **Displays using the IT8951 controller (6", 7.8", 9.7", 10.3")**
- **Special drivers**
  - **Dummy - no-op driver**
  - **Bitmap - output frames as bitmap files (for debugging)**

Should this code mess up your display, disconnecting it from power ought to fix it if nothing else helps.

### Overview

This is a restructuring of Waveshare's code for the purposes of using all the displays with a common interface from the PaperTTY program. Note that these are **SPI** displays - the UART ones are not supported at the moment.

The original code between different models contained **lots** of overlap and this is an attempt to identify the common code and create classes based on that. The original code was analyzed first with a (crude) program that would:

- Collect all the class methods and variables from each source file
- Normalize the source by removing all comments and extra whitespace for each method separately
- Calculate intersections of sets of source code strings (entire methods) to find common code
- Find common class variables with identical values between groups of displays

(I wonder if there exists some nice tool to visually analyze, compare and cluster a codebase based on similarity instead of writing it myself, but I didn't find one...)

Afterwards, the results were used to group the individual display models' code so that subclasses override and build on the base methods and variables. Grouping could have been based on more concrete factors such as chips used in the products but I didn't find such information, so the grouping is based on code similarity and the features of the displays.

Manual adjustments were made to unify methods that only differed very slightly (such as using a single different value somewhere).

Also some bugs were fixed and overall style formatted to be a bit more pythonic (the reference code appears to be translated from C), although most code was left verbatim, including the original comments. This eventually resulted in *hopefully* the same functionality but ~3000 lines shorter.

The actual driver code could be refactored a lot, but only small tweaks have been done for now.

**Since I have no way of actually testing if the code works properly without the hardware, it's very likely I have introduced some new bugs and/or the code needs some fixing.**

### Usage

PaperTTY itself doesn't use much of the drivers' features - also colors are ignored. The only important driver methods it calls are `initialize` and `draw` (and `scrub`).

Functionality has not (intentionally) been removed from the drivers so you should be able to instantiate and use them quite similarly to the Waveshare's demo code:

```python
# This will draw a black rectangle to the corner of the display (2.13" B/W)

# Import the required driver/group
from papertty import drivers as drivers_partial
from PIL import Image, ImageDraw

# Instantiate
epd = drivers_partial.EPD2in13()
# Remember to initialize: by default uses partial refresh if available
epd.init()
# Create an image and draw a black rectangle on it
img = Image.new('1', (epd.width, epd.height), epd.white)
draw = ImageDraw.Draw(img)
draw.rectangle((0,0,50,50), fill=epd.black)
# Set memory twice because of partial refresh
epd.set_frame_memory(img, 0, 0)
epd.display_frame()
epd.set_frame_memory(img, 0, 0)
epd.display_frame()
```

**However**, now each display has a new `draw` method, so you don't need to bother with the specifics of how a particular display is updated, and the above code can be simplified slightly:

```python
# This will draw a black rectangle to the corner of the display (2.13" B/W),
# using the new 'draw' method

# Import the required driver/group
import drivers.drivers_partial as drivers_partial
from PIL import Image, ImageDraw

# Instantiate
epd = drivers_partial.EPD2in13()
# Remember to initialize: by default uses partial refresh if available
epd.init()
# Create an image and draw a black rectangle on it
img = Image.new('1', (epd.width, epd.height), epd.white)
draw = ImageDraw.Draw(img)
draw.rectangle((0,0,50,50), fill=epd.black)
# Just draw it on the screen
epd.draw(0, 0, img)
```

### Class structure

The **B** and **C** variants differ by just their color (EPD 1.54" C is an exception - its resolution is lower) so you *should* be able to use the **C** displays with the **B** driver.

- **`DisplayDriver`** - base class with abstract `init` and `draw` methods

  - **`SpecialDriver`** - base class for "dummy" drivers - ie. not actual display hardware
    - **`Dummy`** - **dummy, no-op driver**
    - **`Bitmap`** - **bitmap driver - renders the content into files**
  - **`WaveshareEPD`** - base class for Waveshare EPDs
    - **`WavesharePartial`** - base class for variants that (officially) support partial refresh
      - **`EPD1in54`** - **EPD 1.54" (monochrome)**
      - **`EPD2in13`** - **EPD 2.13" (monochrome)**
      - **`EPD2in13d` - EPD 2.13" D (monochrome, flexible)**
      - **`EPD2in9`** - **EPD 2.9" (monochrome)**
    - **`WaveshareFull`** - base class for variants that **don't** (officially) support partial refresh
      - **`EPD2in7`** - **EPD 2.7" (monochrome)**
      - **`EPD4in2`** - **EPD 4.2" (monochrome)**
      - **`EPD7in5`** - **EPD 7.5" (monochrome)**
      - **`WaveshareColor`** - base class for variants that have an extra color (B/C variants)
        - **`EPD4in2b`** - **EPD 4.2" B (black/white/red)**
        - **`EPD7in5b`** - **EPD 7.5" B (black/white/red)**
          - **`EPD5in83` - EPD 5.83" (monochrome)** - oddly enough, this "monochrome" display seems code-wise identical to `EPD7in5b` except that it initializes with a different resolution setting
            - **`EPD5in83b` - EPD 5.83" B (black/white/red)**
        - **`WaveshareColorDraw`** - base class for color variants that implement "rotation aware" drawing methods
          - **`EPD1in54b`** - **EPD 1.54" B (black/white/red)**
          - **`EPD1in54c`** - **EPD 1.54" C (black/white/yellow)**
          - **`EPD2in13b`** - **EPD 2.13" B (black/white/red)**
          - **`EPD2in7b`** - **EPD 2.7" B (black/white/red)**
          - **`EPD2in9b`** - **EPD 2.9" B (black/white/red)**

  ​

### Bitmap driver

This is mostly for debugging purposes (and to configure it you'll need to edit the source), but by default it will store the frames in a round-robin fashion as PNG images (`bitmap_frame_[0-4].png`) to the working directory, overwriting the old ones as new frames are drawn. By default just the last 5 frames are stored.
