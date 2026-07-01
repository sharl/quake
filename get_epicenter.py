# -*- coding: utf-8 -*-
from urllib.parse import quote
import json
import math
import os

import requests


def get_mapbox_zoom(center_lat: float,
                    center_lng: float,
                    ref_lat: float,
                    ref_lng: float,
                    width: int = 480,
                    height: int = 480,
                    padding: int = 20,
                    ) -> float:
    # 利用可能な実画面サイズ（余白を引く）
    usable_w = width - (padding * 2)
    usable_h = height - (padding * 2)

    # Mapboxの標準タイルサイズ
    TILE_SIZE = 512

    # メルカトル投影法（ズーム0）での座標変換
    def lng_to_x(lng):
        return (lng + 180.0) * (TILE_SIZE / 360.0)

    def lat_to_y(lat):
        lat_rad = math.radians(lat)
        return (TILE_SIZE / 2.0) - (TILE_SIZE / (2.0 * math.pi)) * math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))

    cx, cy = lng_to_x(center_lng), lat_to_y(center_lat)
    rx, ry = lng_to_x(ref_lng), lat_to_y(ref_lat)

    # 中心固定のため、片側の最大差分の「2倍」の幅が必要
    dx_p0 = abs(cx - rx) * 2
    dy_p0 = abs(cy - ry) * 2

    # 512pxタイル基準でのズーム倍率計算
    zoom_w = math.log2(usable_w / dx_p0) if dx_p0 > 0 else 22
    zoom_h = math.log2(usable_h / dy_p0) if dy_p0 > 0 else 22

    # 確実に収めるために、より引いた（小さい）ズームレベルを採用
    return min(zoom_w, zoom_h)


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
    # 2026/07/02 近くのアメダス観測地点までの距離から拡大率を決定
    if not text:
        amedastable = {}

        url = 'https://www.jma.go.jp/bosai/amedas/const/amedastable.json'
        try:
            with requests.get(url, timeout=10) as r:
                amedastable = r.json()
        except Exception:
            pass

        def deg2dec(deg):
            degree, minute = deg
            return degree + minute / 60

        if amedastable:
            lines = []
            data = amedastable
            for key in data:
                name = data[key]['kjName']
                elem = data[key]['elems']
                _lat = deg2dec(data[key]['lat'])
                _lng = deg2dec(data[key]['lon'])
                dist = math.dist((lat, lon), (_lat, _lng))
                # 気温 降水量 風向 風速 日照時間 積雪深 湿度 気圧
                if elem.startswith('11111'):
                    lines.append([name, (_lat, _lng), dist])

            # 情報量を増やすため少し離れた観測地点をターゲットに
            d = sorted(lines, key=lambda x: x[2])[3]

            # 条件設定
            ref_lat, ref_lng = d[1]
            zoom = get_mapbox_zoom(lat, lon, ref_lat, ref_lng, width, height)
            # 有効桁数..
            zoom = int(100 * (zoom)) / 100
            print(d, zoom)

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
