# -*- coding: utf-8 -*-
from datetime import datetime as dt

import requests

LIST_URL: str = 'https://www.jma.go.jp/bosai/quake/data/list.json'


class getList:
    """
    https://www.jma.go.jp/bosai/quake/data/list.json から各種データを取得
    """
    def __init__(self, session: requests.Session):
        self.session: requests.Session = session
        with self.session.get(LIST_URL, timeout=3) as r:
            self.data: dict = r.json()

    def find(self, eid: str | None) -> dict:
        """
        eid から一致するデータを返す
        eid: None の場合は最新のデータを返す
        """
        for j in self.data:
            if (j['eid'] == eid or eid is None) and j['ttl'] == '震源・震度情報':
                return j
        return {}

    def get_maxi_cities(self, eid: str | None) -> str:
        # cities: dict[str, list[str]] = {}
        data: dict = self.find(eid)

        if data:
            maxi: str = data['maxi']
            bases: list[str] = LIST_URL.split('/')[:-1]
            bases.append(data['json'])
            url: str = '/'.join(bases)
            with self.session.get(url, timeout=1) as r:
                for pref in r.json()['Body']['Intensity']['Observation']['Pref']:
                    if pref['MaxInt'] == maxi:
                        for area in pref['Area']:
                            for city in area['City']:
                                if city['MaxInt'] == maxi:
                                    # pname: str = pref['Name']
                                    # cname: str = city['Name']
                                    # if pname not in cities:
                                    #     cities[pname] = []
                                    # cities[pname].append(cname)
                                    return f"{pref['Name']} {city['Name']}"

        # lines: list[str] = []
        # for pref in cities:
        #     lines.append(f'{pref} {" ".join(cities[pref])}')
        #     break
        # return ' '.join(lines)
        return ''

    def get_title(self, eid: str | None) -> str:
        data = self.find(eid)

        if not eid:
            eid = data['eid']
        # 発表時点の震源地
        region_name = data['anm']
        # 発表時点のマグニチュード
        magunitude = data['mag']
        # 発表時点の震源深さ
        depth = self.get_depth(data['cod'])
        # 発表時点の最大震度
        intensity = data['maxi'].replace('+', '強').replace('-', '弱')
        loc = self.get_maxi_cities(None)

        lines = [
            dt.strptime(eid, '%Y%m%d%H%M%S').strftime('%Y/%m/%d %H:%M:%S'),
            region_name,
            f"M{magunitude} 深さ {depth}",
            f"最大震度 {intensity}",
            loc,
        ]
        return '\n'.join(lines).strip()

    def get_depth(self, cod: str) -> str:
        # '+28.6+129.7+0/',      # ごく浅い
        # '+38.4+141.9-60000/',  # 60km
        # '+37.5+138.6/',        # 不明
        # '',                    # 不明
        # [+-]lat[+-]lng[+-]depth/   ISO6709
        parts = cod.removesuffix('/').replace('-', '+').split('+')
        if len(parts) < 4:
            return '不明'

        km = int(parts[3]) // 1000
        return f'{km}km' if km > 0 else 'ごく浅い'
