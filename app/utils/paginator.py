def paginate(queryset: list, page: int = 1, page_size: int = 10):
    """
    Simple Python pagination utility.
    For DB-level pagination, use LIMIT/OFFSET in SQL queries.
    """
    start = (page - 1) * page_size
    end = start + page_size
    total = len(queryset)

    return {
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": (total + page_size - 1) // page_size,
        "items": queryset[start:end],
    }
