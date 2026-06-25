import httpx
import re


def geocode(query: str) -> tuple[float, float] | None:
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "pharmacy-bot/1.0"}

    # Спроба 1 — структурований запит (найточніший)
    with httpx.Client() as client:
        r = client.get(url, params={
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": "ua",
            "addressdetails": 1
        }, headers=headers)
        data = r.json()

    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])

    # Спроба 2 — прибираємо скорочення через regex
    clean = re.sub(
        r'\b(м|вул|пр|пров|просп|смт|с|сел|обл|р-н|буд|корп|кв)\.',
        '', query, flags=re.IGNORECASE
    ).strip()
    clean = re.sub(r'\s+', ' ', clean)  # прибираємо подвійні пробіли

    print(f"[GEO] Спроба 2: '{clean}'")

    with httpx.Client() as client:
        r = client.get(url, params={
            "q": clean,
            "format": "json",
            "limit": 1,
            "countrycodes": "ua"
        }, headers=headers)
        data = r.json()

    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])

    # Спроба 3 — тільки останні два слова (місто + вулиця без номера)
    words = clean.split()
    if len(words) > 2:
        short = ' '.join(words[-2:])
        print(f"[GEO] Спроба 3: '{short}'")

        with httpx.Client() as client:
            r = client.get(url, params={
                "q": short,
                "format": "json",
                "limit": 1,
                "countrycodes": "ua"
            }, headers=headers)
            data = r.json()

        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])

    return None