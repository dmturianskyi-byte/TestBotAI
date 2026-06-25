from db import get_cursor
from model import model
from geocoder import geocode


def search_pharmacies(
    query: str = None,
    city: str = None,
    address: str = None,
    radius: int = 1000,
    count_only: bool = False,
    group_by_city: bool = False,
    limit: int = 20,
):
    """
    Універсальний пошук аптек.

    query        — назва/опис для семантичного пошуку (опціонально)
    city         — назва міста для фільтрації (опціонально)
    address      — конкретна адреса для geo-пошуку (опціонально, геокодиться)
    radius       — радіус у метрах, використовується тільки якщо передано address
    count_only   — якщо True, повертає тільки кількість
    group_by_city— якщо True, повертає статистику по містах (топ міст)
    limit        — максимум результатів
    """

    cur = get_cursor()

    # ---- Статистика по містах ----
    if group_by_city:
        cur.execute("""
            SELECT name_city, COUNT(*) as count
            FROM competitors_tabletki_firms
            GROUP BY name_city
            ORDER BY count DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        print(f"[SEARCH] group_by_city → {len(rows)} міст")
        return rows

    where_clauses = []
    params = []

    emb = None
    if query:
        emb = model.encode(query)

    lat = lon = None
    if address:
        coords = geocode(address)
        if not coords:
            print(f"[SEARCH] ❌ Координати не знайдено для адреси: {address}")
            return [] if not count_only else 0
        lat, lon = coords
        print(f"[SEARCH] Адреса '{address}' → lat={lat}, lon={lon}")

    # ---- Будуємо WHERE динамічно ----
    if city:
        where_clauses.append("LOWER(name_city) LIKE LOWER(%s)")
        params.append(f"%{city}%")

    if lat is not None and lon is not None:
        where_clauses.append("""
            ST_DWithin(
                geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
        """)
        params.extend([lon, lat, radius])

    if query:
        word_count = len(query.split())
        threshold = 0.45 if word_count <= 2 else 0.6

        # ДЕБАГ — подивимось топ-5 схожості незалежно від порогу
        cur.execute("""
            SELECT name, 1 - (embedding <=> %s::vector) AS sim
            FROM competitors_tabletki_firms
            ORDER BY embedding <=> %s::vector
            LIMIT 5
        """, (emb, emb))
        for row in cur.fetchall():
            print(f"[DEBUG SIM] {row[0]} → {row[1]:.4f}")

        where_clauses.append("""
            (
                1 - (embedding <=> %s::vector) > %s
                OR LOWER(REPLACE(name, '-', '')) LIKE LOWER(REPLACE(%s, '-', ''))
            )
        """)
        params.extend([emb, threshold, f"%{query}%"])

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

    # ---- COUNT ----
    if count_only:
        sql = f"""
            SELECT COUNT(*) FROM competitors_tabletki_firms
            WHERE {where_sql}
        """
        print(f"[DEBUG SQL] {sql}")
        print(f"[DEBUG PARAMS] {params}")
        cur.execute(sql, params)
        result = cur.fetchone()[0]
        print(f"[SEARCH] COUNT query='{query}' city='{city}' address='{address}' → {result}")
        return result

    # ---- LIST (з сортуванням по similarity якщо є query, інакше по distance) ----
    order_sql = "ORDER BY embedding <=> %s::vector" if query else "ORDER BY name"
    order_params = [emb] if query else []

    sql = f"""
        SELECT name, address, name_city
        FROM competitors_tabletki_firms
        WHERE {where_sql}
        {order_sql}
        LIMIT %s
    """
    cur.execute(sql, params + order_params + [limit])
    rows = cur.fetchall()
    print(f"[SEARCH] LIST query='{query}' city='{city}' address='{address}' → {len(rows)} результатів")
    return rows