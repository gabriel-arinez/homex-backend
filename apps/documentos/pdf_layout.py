"""Measured, independently splittable zones for Letter product sheets."""

from reportlab.lib import colors
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
        if taken and taken[-1].getKeepWithNext():
            return taken[:-1], items[index - 1 :]
        return taken, items[index:]
    return taken, []


class RoundedPanel(Flowable):
    """A measured padded stack whose page fragments retain their rounded outline."""

    def __init__(self, items, *, padding=7, radius=4, background="#fdfdfd"):
        super().__init__()
        self.items, self.padding, self.radius = items, padding, radius
        self.background = background

    def wrap(self, width, height):
        self.width = width
        self.measured = measure(self.items, max(1, width - 2 * self.padding))
        self.height = sum(h + 4 for _, h in self.measured) + 2 * self.padding - 4
        return width, self.height

    def split(self, width, height):
        self.wrap(width, height)
        if self.height <= 150 or height < 45:
            return []
        head, tail = take(self.items, width - 2 * self.padding, height - 2 * self.padding)
        if not head or not tail:
            return []
        return [
            RoundedPanel(
                items, padding=self.padding, radius=self.radius, background=self.background
            )
            for items in (head, tail)
        ]

    def draw(self):
        self.canv.setLineWidth(0.45)
        self.canv.setStrokeColor(colors.HexColor("#dedede"))
        self.canv.setFillColor(colors.HexColor(self.background))
        self.canv.roundRect(0, 0, self.width, self.height, self.radius, stroke=1, fill=1)
        y = self.height - self.padding
        for item, height in self.measured:
            y -= height
            item.drawOn(self.canv, self.padding, y)
            y -= 4


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

    def __init__(self, header, image, content, footer, *, first=True, final=True, prefix=()):
        super().__init__()
        self.header, self.image, self.content, self.footer = header, image, content, footer
        self.first, self.final = first, final
        self.prefix = list(prefix)
        self.padding = 8
        self.spaceAfter = 9

    def wrap(self, width, height):
        self.width = width
        self.inner_width = width - 2 * self.padding
        self.prefix_measured = measure(self.prefix, width) if self.first else []
        self.prefix_height = sum(h + 4 for _, h in self.prefix_measured)
        self.header_height = self.header.wrap(self.inner_width, 1e9)[1] + 9 if self.first else 0
        self.footer_height = self.footer.wrap(self.inner_width, 1e9)[1] + 7 if self.final else 0
        self.measured = measure(self.content, self.inner_width)
        self.body_height = sum(h + 4 for _, h in self.measured)
        self.height = (
            self.prefix_height
            + self.header_height
            + self.body_height
            + self.footer_height
            + 2 * self.padding
        )
        return width, self.height

    def split(self, width, height):
        self.wrap(width, height)
        reserve = self.footer.wrap(self.inner_width, 1e9)[1] + 7 if self.final else 0
        available = height - self.prefix_height - self.header_height - reserve - 2 * self.padding
        if available < (35 * mm if self.first else 24):
            return []
        taken, remaining = take(self.content, self.inner_width, available)
        if not taken or not remaining:
            return []
        return [
            ProductCard(
                self.header,
                None,
                taken,
                self.footer,
                first=self.first,
                final=False,
                prefix=self.prefix,
            ),
            ProductCard(self.header, None, remaining, self.footer, first=False, final=self.final),
        ]

    def draw(self):
        top = self.height
        for item, height in self.prefix_measured:
            top -= height
            item.drawOn(self.canv, 0, top)
            top -= 4
        self.canv.setLineWidth(0.5)
        self.canv.setStrokeColor(colors.HexColor("#dedede"))
        self.canv.setFillColor(colors.white)
        self.canv.roundRect(0, 0, self.width, top, 8, stroke=1, fill=1)
        top -= self.padding
        if self.first:
            self.header.drawOn(self.canv, self.padding, top - self.header_height + 9)
            top -= self.header_height
        for item, height in self.measured:
            top -= height
            item.drawOn(self.canv, self.padding, top)
            top -= 4
        if self.final:
            self.footer.drawOn(self.canv, self.padding, self.padding)
