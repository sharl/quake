import asyncio

import requests
import winsdk.windows.devices.geolocation as wdg


def getLocation():
    async def getCoords():
        locator = wdg.Geolocator()
        pos = await locator.get_geoposition_async()
        return [pos.coordinate.latitude, pos.coordinate.longitude]

    try:
        return asyncio.run(getCoords())
    except Exception as e:
        print(e)
        return [None, None]


def getNearWard(pos):
    lat, lng = pos
    url = f'https://geoapi.heartrails.com/api/json?method=searchByGeoLocation&x={lng}&y={lat}'
    with requests.get(url) as r:
        loc = r.json()['response']['location'][0]
        return loc['city']
    return ''
