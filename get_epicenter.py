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
    # ターゲットとの最大差分（中心固定なので2倍にする）
    d_lat = abs(center_lat - ref_lat) * 2
    d_lng = abs(center_lng - ref_lng) * 2

    if d_lat == 0 and d_lng == 0:
        return 22.0

    # 北緯35度近辺での、ズーム0における1度あたりのピクセル数
    # (360度で512px、かつ緯度方向はcos(35°)で反比例するのを考慮した実測係数)
    px_per_deg_lng = 512 / 360  # 約 1.422
    px_per_deg_lat = px_per_deg_lng / math.cos(math.radians(center_lat))

    # 各軸で必要なズームレベルを計算 (利用可能サイズ / (差分 * ズーム0でのpx数))
    zoom_w = math.log2((width - padding * 2) / (d_lng * px_per_deg_lng))
    zoom_h = math.log2((height - padding * 2) / (d_lat * px_per_deg_lat))

    # 確実に収めるために小さい方を採用
    return min(zoom_w, zoom_h)


def get_epicenter(lat: float,
                  lon: float,
                  zoom: float = 10,
                  bearing: float = 0,
                  pitch: float = 0,
                  width: int = 480,
                  height: int = 480,
                  amedastable: dict = {},
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
        if not amedastable:
            url = 'https://www.jma.go.jp/bosai/amedas/const/amedastable.json'
            try:
                with requests.get(url, timeout=10) as r:
                    amedastable.update(r.json())
            except Exception:
                pass

        def deg2dec(deg):
            degree, minute = deg
            return degree + minute / 60

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
        # URLを短くするために有効桁数調整
        zoom = round(zoom, 2)
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
