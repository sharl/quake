# -*- coding: utf-8 -*-
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

    def find(self, eid: str) -> dict:
        """eid から一致するデータを返す"""
        for j in self.data:
            if j['eid'] == eid and j['ttl'] == '震源・震度情報':
                return j
        return {}

    def get_maxi_cities(self, eid: str) -> str:
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
