# -*- coding: utf-8 -*-
import math


def getDepth(_cod):
    # '+28.6+129.7+0/',      # ごく浅い
    # '+38.4+141.9-60000/',  # 60km
    # '+37.5+138.6/',        # 不明
    # '',                    # 不明
    # [+-]lat[+-]lng[+-]depth/   ISO6709
    dep = ''
    cod = _cod.removesuffix('/').split('+')
    if len(cod) == 4:
        _, _, _, dep = cod
    elif len(cod) == 3:
        _, _, ld = cod
        if '-' in ld:
            _, dep = ld.split('-')
    if not dep:
        dep = '不明'
    else:
        t = int(dep) // 1000
        if t:
            dep = f'{t}km'
        else:
            dep = 'ごく浅い'

    return dep


def calc(my_pos, eq_pos):
    """
    my_pos: (lat, lon)
    eq_pos: (lat, lon, depth_km, magunitude)
    """
    # 2地点間の水平距離 (km) を計算
    r = 6371.0
    lat1, lon1 = map(math.radians, my_pos)
    lat2, lon2 = map(math.radians, eq_pos[:2])
    depth = eq_pos[2]
    magunitude = eq_pos[3]

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (math.sin(dlat / 2)**2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2)
    horizontal_dist = 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    # 震源距離 (km) を算出
    dist = math.sqrt(horizontal_dist**2 + depth**2)
    # S波 3.5km/sと仮定
    arrivalTime = dist / 3.5
    # 司・翠川式簡略版で現在地の予想震度を算出
    calcIntensity = 0.67 * magunitude - 1.83 * math.log10(max(dist, 1)) + 1.5

    return dist, arrivalTime, calcIntensity
