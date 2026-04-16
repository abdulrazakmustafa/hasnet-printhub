def compute_total_cost(
    pages: int,
    copies: int,
    color: str,
    bw_price_per_page: float,
    color_price_per_page: float,
) -> float:
    unit_price = color_price_per_page if color.lower() == "color" else bw_price_per_page
    return round(pages * copies * unit_price, 2)

