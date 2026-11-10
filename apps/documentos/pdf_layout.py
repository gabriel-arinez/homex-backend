"""Measured, independently splittable zones for Letter product sheets."""

from reportlab.lib.units import mm
from reportlab.platypus import Flowable


def measure(items, width):
    return [(item, item.wrap(width, 1e9)[1]) for item in items]


def take(items, width, height):
    """Split a stack without leaving a heading separated from its first lines."""
    taken, used = [], 0
    measured = measure(items, width)
    for index, (item, size) in enumerate(measured):
        needed = size + 4
        if item.getKeepWithNext() and index + 1 < len(measured):
            following, following_height = measured[index + 1]
            needed += (
                min(following_height, getattr(getattr(following, "style", None), "leading", 12) * 2)
                + 4
            )
        if used + needed <= height:
            taken.append(item)
            used += size + 4
            continue
        pieces = [] if item.getKeepWithNext() else item.split(width, max(0, height - used - 4))
        if len(pieces) >= 2:
            return taken + pieces[:1], pieces[1:] + items[index + 1 :]
        return taken, items[index:]
    return taken, []


class Columns(Flowable):
    """Top-aligned dynamic grids; long cells split instead of clipping.

    A short row moves intact. Large rows split each column independently, so a
    single extensive set or paragraph cannot make an unbreakable page-sized box.
    """

    def __init__(self, columns, widths=None, *, center_first=False):
        super().__init__()
        self.columns, self.widths = columns, widths
        self.center_first = center_first

    def wrap(self, width, height):
        self.width = width
        self.column_widths = self.widths or [width / len(self.columns)] * len(self.columns)
        self.measured = [
            measure(items, w - 10)
            for items, w in zip(self.columns, self.column_widths, strict=True)
        ]
        self.height = max((sum(h + 4 for _, h in col) for col in self.measured), default=0)
        return width, self.height

    def split(self, width, height):
        self.wrap(width, height)
        if self.height <= 180 or height < 30:
            return []
        heads, tails = [], []
        for items, w in zip(self.columns, self.column_widths, strict=True):
            cell_height = sum(size + 4 for _, size in measure(items, w - 10))
            if height < cell_height <= 180:
                return []
            head, tail = take(items, w - 10, height)
            if items and not head:
                return []
            heads.append(head)
            tails.append(tail)
        if not any(tails):
            return []
        return [
            Columns(heads, self.widths, center_first=self.center_first),
            Columns(tails, self.widths),
        ]

    def draw(self):
        x = 0
        for index, (col, width) in enumerate(zip(self.measured, self.column_widths, strict=True)):
            y = self.height
            if index == 0 and self.center_first:
                y -= (self.height - sum(h + 4 for _, h in col)) / 2 + 2
            for item, height in col:
                y -= height
                item_width = item.wrap(width - 10, 1e9)[0]
                item.drawOn(
                    self.canv,
                    x
                    + 5
                    + (
                        max(0, width - 10 - item_width) / 2
                        if index == 0 and self.center_first
                        else 0
                    ),
                    y,
                )
                y -= 4
            x += width


class ProductCard(Flowable):
    """Full-width independent zones, with attached header and persisted economics."""

    def __init__(self, header, image, content, footer, *, first=True, final=True):
        super().__init__()
        self.header, self.image, self.content, self.footer = header, image, content, footer
        self.first, self.final = first, final
        self.spaceAfter = 9

    def wrap(self, width, height):
        self.width = width
        self.header_height = self.header.wrap(width, 1e9)[1] + 7 if self.first else 0
        self.footer_height = self.footer.wrap(width, 1e9)[1] + 7 if self.final else 0
        self.measured = measure(self.content, width)
        self.body_height = sum(h + 4 for _, h in self.measured)
        self.height = self.header_height + self.body_height + self.footer_height
        return width, self.height

    def split(self, width, height):
        self.wrap(width, height)
        reserve = self.footer.wrap(width, 1e9)[1] + 7 if self.final else 0
        available = height - self.header_height - reserve
        if available < (35 * mm if self.first else 24):
            return []
        taken, remaining = take(self.content, width, available)
        if not taken or not remaining:
            return []
        return [
            ProductCard(self.header, None, taken, self.footer, first=self.first, final=False),
            ProductCard(self.header, None, remaining, self.footer, first=False, final=self.final),
        ]

    def draw(self):
        top = self.height
        if self.first:
            self.header.drawOn(self.canv, 0, top - self.header_height + 7)
            top -= self.header_height
        for item, height in self.measured:
            top -= height
            item.drawOn(self.canv, 0, top)
            top -= 4
        if self.final:
            self.footer.drawOn(self.canv, 0, 0)
