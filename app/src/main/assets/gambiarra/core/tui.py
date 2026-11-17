import os
import re
import sys
import unicodedata

if os.name == "nt":
    import msvcrt
else:
    import termios
    import tty

ESC = "\x1b["
RESET = ESC + "0m"
BOLD = ESC + "1m"
ORANGE = ESC + "38;5;208m"
ORANGE_DK = ESC + "38;5;166m"
GREEN = ESC + "38;5;114m"
RED = ESC + "38;5;203m"
YELLOW = ESC + "38;5;221m"
WHITE = ESC + "38;5;255m"
GRAY = ESC + "38;5;250m"
DIM = ESC + "38;5;242m"
BG_ORANGE = ESC + "48;5;208m" + ESC + "38;5;232m"

KEY_UP = "\x00UP"
KEY_DOWN = "\x00DOWN"
KEY_LEFT = "\x00LEFT"
KEY_RIGHT = "\x00RIGHT"
KEY_ENTER = "\x00ENTER"
KEY_SPACE = "\x00SPACE"
KEY_BACKSPACE = "\x00BS"
KEY_ESC = "\x00ESC"
KEY_TAB = "\x00TAB"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
BOX = {
    "tl": "\u256d", "tr": "\u256e", "bl": "\u2570", "br": "\u256f",
    "h": "\u2500", "v": "\u2502", "ml": "\u251c", "mr": "\u2524",
    "lt": "\u251c", "rt": "\u2524", "tt": "\u252c", "bt": "\u2534",
}

def _ascii_box(edge_ok):
    h, v = ("-" if edge_ok else "-"), ("|" if edge_ok else "|")
    return {
        "tl": "+", "tr": "+", "bl": "+", "br": "+", "h": h, "v": v,
        "ml": "+", "mr": "+", "lt": "+", "rt": "+", "tt": "+", "bt": "+",
    }

class Glyphs:

    def __init__(self, ascii_mode=False):
        self.set_ascii(ascii_mode)

    @staticmethod
    def has_unicode():
        for stream in (sys.stdout,):
            enc = (getattr(stream, "encoding", "") or "").lower()
            if "utf" not in enc:
                return False
        try:
            "".join(BOX.values()) + "\u25cf\u2588"
            return True
        except Exception:
            return False

    def set_ascii(self, ascii_mode):
        if ascii_mode:
            self.box = _ascii_box(True)
            self.dot_on, self.dot_off = "*", "."
            self.cursor = "#"
            self.bar_on, self.bar_off = "#", "-"
        else:
            self.box = dict(BOX)
            self.dot_on, self.dot_off = "\u25cf", "\u25cb"
            self.cursor = "\u2588"
            self.bar_on, self.bar_off = "\u2588", "\u2591"

GLYPHS = Glyphs()

if not Glyphs.has_unicode():
    GLYPHS.set_ascii(True)

def strip(text):
    return ANSI_RE.sub("", text)

def width(text):
    plain = strip(text)
    total = 0
    for ch in plain:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total

def fit(text, cols):
    if cols <= 0:
        return ""
    plain = strip(text)
    w = width(plain)
    if w == cols:
        return text
    if w < cols:
        return text + " " * (cols - w)
    out = []
    used = 0
    i = 0
    n = len(text)
    while i < n and used < cols:
        m = ANSI_RE.match(text, i)
        if m:
            chunk = m.group(0)
            if len(out) < 4:
                out.insert(0, chunk)
            else:
                out.append(chunk)
            i = m.end()
            continue
        ch = text[i]
        if ch == "\x1b":
            i += 1
            continue
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + cw > cols:
            break
        out.append(ch)
        used += cw
        i += 1
    while out and out[-1].startswith("\x1b["):
        out.pop()
    if used < cols:
        out.append(" " * (cols - used))
    return "".join(out) + RESET

def center(text, cols):
    plain = strip(text)
    pad = max(0, (cols - width(plain)) // 2)
    return " " * pad + text

def box_top(cols, title="", color=DIM):
    b = GLYPHS.box
    if not title:
        return color + b["tl"] + b["h"] * cols + b["tr"] + RESET
    label = " " + title + " "
    fill = max(0, cols - width(label))
    left = fill // 2
    right = fill - left
    return (color + b["tl"] + b["h"] * left + label + b["h"] * right + b["tr"]
            + RESET)

def box_bottom(cols, color=DIM):
    b = GLYPHS.box
    return color + b["bl"] + b["h"] * cols + b["br"] + RESET

def box_row(content, cols, color=DIM, pad=2):
    b = GLYPHS.box
    room = max(0, cols - pad)
    body = fit(" " * pad + content, room) if content else " " * cols
    return color + b["v"] + RESET + fit(body, cols) + color + b["v"] + RESET

def pair(left, right, cols, color=DIM, pad=2):
    room = cols - pad - width(right)
    if room >= 1:
        body = (" " * pad + left + " " * max(0, room - width(left)) + right)
    else:
        body = " " * pad + left
    return color + GLYPHS.box["v"] + RESET + fit(body, cols) + color \
        + GLYPHS.box["v"] + RESET

def box_sep(cols, color=DIM):
    b = GLYPHS.box
    return color + b["ml"] + b["h"] * cols + b["mr"] + RESET

def bar(frac, cols):
    cols = max(4, cols)
    filled = int(round(max(0.0, min(1.0, frac)) * cols))
    return GLYPHS.bar_on * filled + GLYPHS.bar_off * (cols - filled)

def enter_alt():
    return ESC + "?1049h" + ESC + "?25l" + ESC + "2J" + ESC + "H"

def leave_alt():
    return ESC + "0m" + ESC + "?25h" + ESC + "?1049l"

class Term:
    def __init__(self):
        self._old = None
        self._win = os.name == "nt"
        self._buf = ""

    def init(self):
        if self._win:
            os.system("")
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            except Exception:
                pass
        else:
            fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(fd)

    def enter(self):
        self.init()
        if self._old is not None:
            tty.setraw(sys.stdin.fileno())
        self.write(enter_alt())
        self.flush()

    def leave(self):
        self.write(leave_alt())
        self.flush()
        if self._old is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)

    def write(self, text):
        self._buf += text

    def flush(self):
        if not self._buf:
            return
        text, self._buf = self._buf, ""
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass

    def size(self):
        try:
            s = os.get_terminal_size()
            cols, rows = s.columns, s.lines
        except OSError:
            cols, rows = 100, 35
        if self._win:
            cols, rows = cols - 1, rows - 1
        return max(40, cols), max(12, rows)

    def at(self, row, col):
        return ESC + "%d;%dH" % (row, col)

    def read_key_blocking(self):
        if self._win:
            while True:
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    code = msvcrt.getwch()
                    out = {"H": KEY_UP, "P": KEY_DOWN, "K": KEY_LEFT,
                           "M": KEY_RIGHT}.get(code)
                    if out:
                        return out
                    continue
                return self._translate(ch)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            nxt = sys.stdin.read(1)
            if nxt == "[":
                code = sys.stdin.read(1)
                return {"A": KEY_UP, "B": KEY_DOWN, "C": KEY_RIGHT,
                        "D": KEY_LEFT}.get(code) or KEY_ESC
            return KEY_ESC
        return self._translate(ch)

    def read_key(self):
        return self.read_key_blocking()

    @staticmethod
    def _translate(ch):
        if ch in ("\r", "\n"):
            return KEY_ENTER
        if ch == " ":
            return KEY_SPACE
        if ch in ("\x08", "\x7f"):
            return KEY_BACKSPACE
        if ch == "\t":
            return KEY_TAB
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x1b":
            return KEY_ESC
        return ch

def frame(rows):
    out = [ESC + "1;1H"]
    for i, row in enumerate(rows):
        out.append(ESC + "0m" + row)
        if i != len(rows) - 1:
            out.append("\r\n")
    out.append(ESC + "0m")
    return "".join(out)

def full_frame(rows):
    return ESC + "2J" + frame(rows)

def layout(width_px, height_px):
    outer = max(24, min(width_px - 1, 106))
    return outer - 2, outer - 4

def screen(rows, width_px):
    out = []
    for row in rows:
        row = row or ""
        out.append(row + " " * max(0, width_px - width(row)))
    return out
