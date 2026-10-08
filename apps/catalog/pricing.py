"""Prices for a basket, including wholesale packs. The single place that turns quantities into money:
the cart, the checkout quote and the final order all call price_lines(), so they can never disagree.

Wholesale rule (set per product by the owner): "pack" pieces cost "wholesale_price" together.
Count every piece of that product in the basket, whatever its size or colour:
  below one pack      -> every piece at the normal price
  each full pack      -> the wholesale price
  pieces left over    -> the normal price each
So with a pack of 12 at N100,000: 11 pieces are retail, 12 cost N100,000, 24 cost N200,000, 13 cost N100,000 + one at retail."""
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class PricedLine:
    line_total: int        # kobo
    retail_total: int      # what it would have cost without wholesale
    wholesale_units: int   # pieces on this line charged at the wholesale rate


def wholesale_terms(product) -> tuple[int, int] | None:
    pack, price = product.wholesale_pack, product.wholesale_price
    return (pack, price) if pack and price and pack >= 2 and price > 0 else None


def price_lines(lines: list[tuple[object, int]]) -> list[PricedLine]:
    """lines: (variant, quantity) pairs, in basket order. Returns one PricedLine per input line, same order."""
    priced = [PricedLine(v.unit_price * q, v.unit_price * q, 0) for v, q in lines]
    by_product: dict[int, list[int]] = defaultdict(list)
    for index, (variant, _) in enumerate(lines):
        by_product[variant.product_id].append(index)
    for indexes in by_product.values():
        product = lines[indexes[0]][0].product
        terms = wholesale_terms(product)
        pieces = sum(lines[i][1] for i in indexes)
        if not terms or pieces < terms[0]:
            continue
        pack, pack_price = terms
        covered = (pieces // pack) * pack           # pieces that fall inside full packs
        pool = (pieces // pack) * pack_price        # what those pieces cost together
        used = 0
        for i in indexes:
            variant, quantity = lines[i]
            take = min(quantity, covered - used)
            if take <= 0:
                continue
            # Share the pool by running total so the kobo always add up to exactly the pack price.
            share = pool * (used + take) // covered - pool * used // covered
            used += take
            priced[i] = PricedLine(share + (quantity - take) * variant.unit_price, variant.unit_price * quantity, take)
    return priced
