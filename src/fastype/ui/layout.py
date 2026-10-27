"""The keyboard layout macOS is using right now, read through the Text Input Sources API.

For every physical key (by its virtual key code) this gives the character it types with no
modifier, Shift, Option and Shift+Option, so the on-screen keyboard can show the right
letters for German, US, Romanian or any other layout, and say which keys to press for a
given character. Also reports whether the keyboard is ANSI (US-style) or ISO (European,
with an extra key next to left Shift and a tall Return).

Falls back to a built-in US ANSI layout if the system API isn't available.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass, field

SHIFT, OPTION = 1, 2
# UCKeyTranslate wants the old Carbon modifier bits shifted right by 8.
_CARBON_MODS = {0: 0, SHIFT: 0x02, OPTION: 0x08, SHIFT | OPTION: 0x0A}

# Virtual key codes of the keys that type characters (they're the same on every layout;
# the names refer to the US positions).
CHAR_KEYS = [50, 10, 18, 19, 20, 21, 23, 22, 26, 28, 25, 29, 27, 24,
             12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 33, 30, 42,
             0, 1, 2, 3, 5, 4, 38, 40, 37, 41, 39,
             6, 7, 8, 9, 11, 45, 46, 43, 47, 44, 49, 36]
RETURN, SPACE = 36, 49

_US = {
    50: "`~", 18: "1!", 19: "2@", 20: "3#", 21: "4$", 23: "5%", 22: "6^", 26: "7&", 28: "8*",
    25: "9(", 29: "0)", 27: "-_", 24: "=+", 33: "[{", 30: "]}", 42: "\\|", 41: ";:", 39: "'\"",
    43: ",<", 47: ".>", 44: "/?", 10: "§±",
}
_US.update({k: c + c.upper() for k, c in zip(
    [12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 0, 1, 2, 3, 5, 4, 38, 40, 37, 6, 7, 8, 9, 11, 45, 46],
    "qwertyuiopasdfghjklzxcvbnm")})


@dataclass
class KeyLayout:
    source_id: str = "us"
    name: str = "U.S."
    iso: bool = False
    # key code -> {modifiers: character}
    chars: dict[int, dict[int, str]] = field(default_factory=dict)
    # character -> (key code, modifiers), the simplest way to type it
    lookup: dict[str, tuple[int, int]] = field(default_factory=dict)

    def label(self, code: int) -> tuple[str, str]:
        """(main, shifted) labels for a key, as printed on a keycap."""
        m = self.chars.get(code, {})
        base, shifted = m.get(0, ""), m.get(SHIFT, "")
        if base.isalpha() and shifted == base.upper():
            return base.upper(), ""  # letters show one capital, like real keycaps
        return base, shifted if shifted != base else ""

    def find(self, ch: str) -> tuple[int, int] | None:
        return self.lookup.get(ch)


def _build(source_id: str, name: str, iso: bool, chars: dict[int, dict[int, str]]) -> KeyLayout:
    lookup: dict[str, tuple[int, int]] = {" ": (SPACE, 0), "\n": (RETURN, 0)}
    for mods in (0, SHIFT, OPTION, SHIFT | OPTION):  # simplest combination wins
        for code in CHAR_KEYS:
            ch = chars.get(code, {}).get(mods, "")
            if len(ch) == 1 and ch.isprintable() and ch not in lookup:
                lookup[ch] = (code, mods)
    return KeyLayout(source_id, name, iso, chars, lookup)


def us_layout() -> KeyLayout:
    return _build("us", "U.S.", False, {k: {0: v[0], SHIFT: v[1]} for k, v in _US.items()})


class _Carbon:
    """ctypes bindings for the few Carbon/CoreFoundation calls needed."""

    def __init__(self):
        self.carbon = C.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        cb, cf = self.carbon, self.cf
        cb.TISCopyCurrentKeyboardLayoutInputSource.restype = C.c_void_p
        cb.TISGetInputSourceProperty.restype = C.c_void_p
        cb.TISGetInputSourceProperty.argtypes = [C.c_void_p, C.c_void_p]
        cb.LMGetKbdType.restype = C.c_uint8
        cb.KBGetLayoutType.restype = C.c_uint32
        cb.KBGetLayoutType.argtypes = [C.c_int16]
        cb.UCKeyTranslate.restype = C.c_int32
        cb.UCKeyTranslate.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16, C.c_uint32, C.c_uint32,
                                      C.c_uint32, C.POINTER(C.c_uint32), C.c_ulong,
                                      C.POINTER(C.c_ulong), C.POINTER(C.c_uint16)]
        cf.CFDataGetBytePtr.restype = C.c_void_p
        cf.CFDataGetBytePtr.argtypes = [C.c_void_p]
        cf.CFStringGetCString.argtypes = [C.c_void_p, C.c_char_p, C.c_long, C.c_uint32]
        cf.CFRelease.argtypes = [C.c_void_p]
        self.keys = {n: C.c_void_p.in_dll(cb, n).value for n in (
            "kTISPropertyInputSourceID", "kTISPropertyLocalizedName", "kTISPropertyUnicodeKeyLayoutData")}

    def _string(self, ref) -> str:
        buf = C.create_string_buffer(512)
        if ref and self.cf.CFStringGetCString(ref, buf, 512, 0x08000100):  # UTF-8
            return buf.value.decode()
        return ""

    def source_id(self) -> str:
        src = self.carbon.TISCopyCurrentKeyboardLayoutInputSource()
        try:
            return self._string(self.carbon.TISGetInputSourceProperty(src, self.keys["kTISPropertyInputSourceID"]))
        finally:
            self.cf.CFRelease(src)

    def layout(self) -> KeyLayout:
        cb = self.carbon
        src = cb.TISCopyCurrentKeyboardLayoutInputSource()
        try:
            prop = lambda k: cb.TISGetInputSourceProperty(src, self.keys[k])
            data = prop("kTISPropertyUnicodeKeyLayoutData")
            if not data:
                raise OSError("layout has no Unicode key data")
            ptr = self.cf.CFDataGetBytePtr(data)
            kbd = cb.LMGetKbdType()
            iso = cb.KBGetLayoutType(kbd) == int.from_bytes(b"ISO ", "big")
            chars: dict[int, dict[int, str]] = {}
            for code in CHAR_KEYS:
                chars[code] = {}
                for mods, carbon_mods in _CARBON_MODS.items():
                    dead, n, out = C.c_uint32(0), C.c_ulong(0), (C.c_uint16 * 8)()
                    # Display action, no dead-key processing: dead keys report their own accent.
                    cb.UCKeyTranslate(ptr, code, 3, carbon_mods, kbd, 1, C.byref(dead), 8, C.byref(n), out)
                    chars[code][mods] = "".join(map(chr, out[:n.value]))
            return _build(self._string(prop("kTISPropertyInputSourceID")),
                          self._string(prop("kTISPropertyLocalizedName")), iso, chars)
        finally:
            self.cf.CFRelease(src)


try:
    _carbon: _Carbon | None = _Carbon()
except (OSError, AttributeError, ValueError):
    _carbon = None


def current_source_id() -> str:
    """Cheap to call often: changes when the user switches layouts."""
    try:
        return _carbon.source_id() if _carbon else "us"
    except OSError:
        return "us"


def current_layout() -> KeyLayout:
    try:
        return _carbon.layout() if _carbon else us_layout()
    except OSError:
        return us_layout()
