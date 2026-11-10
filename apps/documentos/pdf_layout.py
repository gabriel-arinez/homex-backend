"""Splittable two-column cards with one image and an attached economic strip."""

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Flowable


class ProductCard(Flowable):
    """Split only the right column; the left never receives technical text.

    Each fragment is independently measured. The image occurs once, centered
    against its accompanying specification fragment. Reserving footer height
    while splitting keeps the final technical lines with the economic strip.
    """

    def __init__(self, header, image, content, footer, *, first=True, final=True):
        super().__init__()
        self.header, self.image, self.content, self.footer = header, image, content, footer
        self.first, self.final = first, final
        self.spaceAfter = 9

    def wrap(self, width, height):
        self.width = width
        self.left_width = 50 * mm
        self.gap = 5 * mm
        self.right_width = width - self.left_width - self.gap
        self.header_height = self.header.wrap(width, 1e9)[1] + 7 if self.first else 0
        self.footer_height = self.footer.wrap(width, 1e9)[1] + 7 if self.final else 0
        self.measured = [(item, item.wrap(self.right_width, 1e9)[1]) for item in self.content]
        self.text_height = sum(h + 4 for _, h in self.measured)
        self.image_height = self.image.wrap(self.left_width, 1e9)[1] if self.image else 0
        self.body_height = max(self.text_height, self.image_height)
        self.height = self.header_height + self.body_height + self.footer_height
        return width, self.height

    def split(self, width, height):
        self.wrap(width, height)
        # Never orphan an item header, image, or section heading at a page foot.
        footer_reserve = self.footer.wrap(width, 1e9)[1] + 7 if self.final else 0
        available = height - self.header_height - footer_reserve
        if available < max(35 * mm if self.first else 24, self.image_height):
            return []
        taken, remaining, used = [], [], 0
        for index, (item, item_height) in enumerate(self.measured):
            needed = item_height + 4
            if item.getKeepWithNext() and index + 1 < len(self.measured):
                next_item, next_height = self.measured[index + 1]
                # Require the start, not the entirety, of an arbitrarily long paragraph.
                needed += (
                    min(
                        next_height,
                        getattr(next_item, "style", None).leading * 2
                        if hasattr(next_item, "style")
                        else next_height,
                    )
                    + 4
                )
            if used + needed <= available:
                taken.append(item)
                used += item_height + 4
                continue
            pieces = (
                [] if item.getKeepWithNext() else item.split(self.right_width, available - used - 4)
            )
            if len(pieces) >= 2:
                taken.append(pieces[0])
                remaining = pieces[1:] + self.content[index + 1 :]
            else:
                remaining = self.content[index:]
            break
        if not taken or not remaining:
            return []
        return [
            ProductCard(self.header, self.image, taken, self.footer, first=self.first, final=False),
            ProductCard(self.header, None, remaining, self.footer, first=False, final=self.final),
        ]

    def draw(self):
        top = self.height
        if self.first:
            self.header.drawOn(self.canv, 0, top - self.header_height + 7)
            top -= self.header_height
        if self.image:
            image_width, image_height = self.image.wrap(self.left_width, self.body_height)
            self.image.drawOn(
                self.canv,
                (self.left_width - image_width) / 2,
                top - (self.body_height + image_height) / 2,
            )
        y = top
        for item, height in self.measured:
            y -= height
            item.drawOn(self.canv, self.left_width + self.gap, y)
            y -= 4
        if self.final:
            self.footer.drawOn(self.canv, 0, 0)


class ProductPlaceholder(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = 42 * mm, 32 * mm

    def draw(self):
        c = self.canv
        c.setFillColor(colors.HexColor("#f8fafc"))
        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#b91c1c"))
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(self.width / 2, self.height / 2 + 3, "HOMEX")
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica", 7)
        c.drawCentredString(self.width / 2, self.height / 2 - 10, "Sin imagen disponible")
