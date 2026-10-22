"""A small QR code encoder: byte mode, error correction M, versions 1-10.

Enough for the link a phone scans to reach this computer (well under 200
characters). Written here rather than pulled in as a package so the
toolkit adds nothing to install: the updater ships code, not wheels.

The construction follows ISO/IEC 18004 in the same order as Project
Nayuki's reference implementation (MIT): encode, add Reed-Solomon blocks,
interleave, draw the fixed patterns, place the data, then keep the mask
with the lowest penalty.
"""

_ECC_PER_BLOCK = (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
_NUM_BLOCKS = (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
_MAX_VERSION = 10


def _raw_modules(ver):
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        result -= (25 * align - 10) * align - 55
        if ver >= 7:
            result -= 36
    return result


def _data_capacity(ver):
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _NUM_BLOCKS[ver]


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _codewords(text):
    data = text.encode("utf-8")
    for ver in range(1, _MAX_VERSION + 1):
        count_bits = 8 if ver < 10 else 16
        need = 4 + count_bits + 8 * len(data)
        if need <= _data_capacity(ver) * 8:
            break
    else:
        raise ValueError("text too long for a QR code here")
    bits = []

    def put(value, n):
        bits.extend((value >> i) & 1 for i in reversed(range(n)))

    put(0b0100, 4)
    put(len(data), count_bits)
    for b in data:
        put(b, 8)
    cap = _data_capacity(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2)
             for i in range(0, len(bits), 8)]

    # Split into blocks, add error correction, interleave.
    nblocks = _NUM_BLOCKS[ver]
    ecclen = _ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    nshort = nblocks - raw % nblocks
    shortlen = raw // nblocks
    divisor = _rs_divisor(ecclen)
    blocks, k = [], 0
    for i in range(nblocks):
        size = shortlen - ecclen + (0 if i < nshort else 1)
        dat = words[k:k + size]
        k += size
        ecc = _rs_remainder(dat, divisor)
        if i < nshort:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != shortlen - ecclen or j >= nshort:
                out.append(blk[i])
    return ver, out


class _Grid:
    def __init__(self, ver):
        self.ver = ver
        self.size = ver * 4 + 17
        self.mod = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x, y, dark):
        self.mod[y][x] = bool(dark)
        self.fixed[y][x] = True

    def draw_function_patterns(self):
        n = self.size
        for i in range(n):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self._alignment_positions()
        last = len(pos) - 1
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def _alignment_positions(self):
        if self.ver == 1:
            return []
        num = self.ver // 7 + 2
        step = (self.ver * 8 + num * 3 + 5) // (num * 4 - 4) * 2
        result = [self.size - 7 - i * step for i in range(num - 1)] + [6]
        return list(reversed(result))

    def draw_format(self, mask):
        data = (0 << 3) | mask          # level M has the bits 00
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        n = self.size

        def bit(i):
            return (bits >> i) & 1

        for i in range(0, 6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(0, 8):
            self.set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit(i))
        self.set(8, n - 8, True)

    def place(self, words):
        n = self.size
        i = 0
        total = len(words) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < total:
                        self.mod[y][x] = bool((words[i >> 3] >> (7 - (i & 7))) & 1)
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        tests = (
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        )
        test = tests[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and test(x, y):
                    self.mod[y][x] = not self.mod[y][x]

    def penalty(self):
        n, m = self.size, self.mod
        score = 0
        lines = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)]
                                             for x in range(n)]
        finder = [True, False, True, True, True, False, True]
        for line in lines:
            run, last = 0, None
            for v in line:
                if v == last:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + run - 5
                    run, last = 1, v
            if run >= 5:
                score += 3 + run - 5
            padded = [False] * 4 + list(line) + [False] * 4
            for i in range(len(padded) - 10):
                seg = padded[i:i + 11]
                if (seg[:7] == finder and not any(seg[7:])) or \
                        (seg[4:] == finder and not any(seg[:4])):
                    score += 40
        for y in range(n - 1):
            for x in range(n - 1):
                c = m[y][x]
                if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in m)
        total = n * n
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        return score + k * 10


def encode(text):
    """The QR code for `text` as rows of booleans (True = dark), without
    the quiet zone."""
    ver, words = _codewords(text)
    best, best_score = None, None
    for mask in range(8):
        grid = _Grid(ver)
        grid.draw_function_patterns()
        grid.place(words)
        grid.apply_mask(mask)
        grid.draw_format(mask)
        score = grid.penalty()
        if best_score is None or score < best_score:
            best, best_score = grid, score
    return best.mod


def draw(canvas, text, x, y, size, dark="#000000", light="#FFFFFF"):
    """Draw the code onto a Tk canvas, quiet zone included, filling a
    `size` by `size` square with its top left at (x, y)."""
    rows = encode(text)
    n = len(rows) + 8
    cell = size / float(n)
    canvas.create_rectangle(x, y, x + size, y + size, fill=light, width=0)
    for r, row in enumerate(rows):
        for c, on in enumerate(row):
            if on:
                x0 = x + (c + 4) * cell
                y0 = y + (r + 4) * cell
                canvas.create_rectangle(x0, y0, x0 + cell + 0.5,
                                        y0 + cell + 0.5, fill=dark, width=0)
