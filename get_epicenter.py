# -*- coding: utf-8 -*-
from urllib.parse import quote
import json
import os

import requests


def get_epicenter(lat: float,
                  lon: float,
                  zoom: float = 10,
                  bearing: float = 0,
                  pitch: float = 0,
                  width: int = 480,
                  height: int = 480
                  ) -> tuple[str, str]:
    text = str()
    url = str()

    # get epicenter address
    geocoding_url = f'https://geoapi.heartrails.com/api/json?method=searchByGeoLocation&x={lon}&y={lat}'
    try:
        with requests.get(geocoding_url, timeout=3) as r:
            loc = r.json()['response']['location'][0]
            text = f"{loc['prefecture']}{loc['city']}{loc['town']}"
    except Exception:
        pass

    # 住所が取得できない場合は海上とみなして拡大率を下げる
    # 拡大率は仮
    if not text:
        zoom = 4

    # get mapbox static image with point marker
    access_token = os.environ.get('MAPBOX_ACCESS_TOKEN')
    username = os.environ.get('MAPBOX_USERNAME')
    style_id = os.environ.get('MAPBOX_STYLE_ID')
    if access_token and username and style_id:
        geodict = {
            "type": "Point",
            "coordinates": [lon, lat],
        }
        geojson_str = json.dumps(geodict, separators=(',', ':'))
        overlay = quote(f'geojson({geojson_str})')

        attribution = 'false'
        logo = 'false'

        center_and_view = f'{lon},{lat},{zoom},{bearing},{pitch}'
        size = f'{width}x{height}'
        query_params = (
            f'access_token={access_token}'
            f'&logo={logo}'
            f'&attribution={attribution}'
        )

        url = (
            f'https://api.mapbox.com/styles/v1/{username}/{style_id}/'
            f'static/{overlay}/{center_and_view}/{size}?{query_params}'
        )

    return text, url
