from db import get_cursor
from model import model
from geocoder import geocode

AGGREGATE_THRESHOLD = 300  # якщо результатів більше — агрегуємо замість повного списку


def search_pharmacies(
    query: str = None,
    city: str = None,
    address: str = None,
    radius: int = 1000,
    count_only: bool = False,
    group_by_city: bool = False,
    limit: int = None,
):
    cur = get_cursor()

    if query and address and not city:
        print(f"[SEARCH] ⚠️ query='{query}' + address одночасно — ігнорую query")
        query = None

    if group_by_city:
        if limit:
            cur.execute("""
                SELECT name_city, COUNT(*) as count
                FROM competitors_tabletki_firms
                GROUP BY name_city
                ORDER BY count DESC
                LIMIT %s
            """, (limit,))
        else:
            cur.execute("""
                SELECT name_city, COUNT(*) as count
                FROM competitors_tabletki_firms
                GROUP BY name_city
                ORDER BY count DESC
            """)
        rows = cur.fetchall()
        print(f"[SEARCH] group_by_city → {len(rows)} міст (limit={limit})")
        return [{"city": r[0], "count": r[1]} for r in rows]

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
            return 0 if count_only else []
        lat, lon = coords
        print(f"[SEARCH] Адреса '{address}' → lat={lat}, lon={lon}")

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

    if count_only:
        sql = f"SELECT COUNT(*) FROM competitors_tabletki_firms WHERE {where_sql}"
        print(f"[DEBUG SQL] {sql}")
        cur.execute(sql, params)
        result = cur.fetchone()[0]
        print(f"[SEARCH] COUNT → {result}")
        return result

    # ---- Спочатку рахуємо загальну кількість, щоб вирішити: список чи агрегація ----
    count_sql = f"SELECT COUNT(*) FROM competitors_tabletki_firms WHERE {where_sql}"
    cur.execute(count_sql, params)
    total_count = cur.fetchone()[0]

    order_sql = "ORDER BY embedding <=> %s::vector" if query else "ORDER BY name"
    order_params = [emb] if query else []

    # ---- Якщо користувач сам попросив limit — завжди повертаємо звичайний список ----
    if limit:
        sql = f"""
            SELECT name, address, name_city
            FROM competitors_tabletki_firms
            WHERE {where_sql}
            {order_sql}
            LIMIT %s
        """
        cur.execute(sql, params + order_params + [limit])
        rows = cur.fetchall()
        print(f"[SEARCH] LIST (limit={limit}) → {len(rows)} результатів")
        return [{"name": r[0], "address": r[1], "city": r[2]} for r in rows]

    # ---- Без limit і результатів МАЛО — повний список ----
    if total_count <= AGGREGATE_THRESHOLD:
        sql = f"""
            SELECT name, address, name_city
            FROM competitors_tabletki_firms
            WHERE {where_sql}
            {order_sql}
        """
        cur.execute(sql, params + order_params)
        rows = cur.fetchall()
        print(f"[SEARCH] LIST (full) → {len(rows)} результатів")
        return [{"name": r[0], "address": r[1], "city": r[2]} for r in rows]

    # ---- Без limit і результатів БАГАТО — агрегуємо по вулицях ----
    print(f"[SEARCH] ⚠️ {total_count} результатів > {AGGREGATE_THRESHOLD} — агрегую по вулицях")

    street_sql = f"""
        SELECT
            split_part(address, ',', 1) AS street,
            name_city,
            COUNT(*) AS count
        FROM competitors_tabletki_firms
        WHERE {where_sql}
        GROUP BY street, name_city
        ORDER BY count DESC
    """
    cur.execute(street_sql, params)
    street_rows = cur.fetchall()

    # Невелика вибірка конкретних прикладів (для перевірки/посилань моделлю)
    sample_sql = f"""
        SELECT name, address, name_city
        FROM competitors_tabletki_firms
        WHERE {where_sql}
        {order_sql}
        LIMIT 30
    """
    cur.execute(sample_sql, params + order_params)
    sample_rows = cur.fetchall()

    return {
        "total_count": total_count,
        "aggregated": True,
        "note": (
            f"Знайдено {total_count} аптек — повний список занадто великий, "
            f"тому дані згруповано по вулицях/районах."
        ),
        "by_street": [
            {"street": r[0].strip(), "city": r[1], "count": r[2]}
            for r in street_rows
        ],
        "sample_pharmacies": [
            {"name": r[0], "address": r[1], "city": r[2]}
            for r in sample_rows
        ],
    }