# -*- coding: utf-8 -*-
from dataclasses import asdict, dataclass
from datetime import datetime as dt, timedelta as td
from enum import Enum
import ctypes
import logging
import logging.handlers
import queue
import threading
import time
import webbrowser
import winsound

from PIL import Image, ImageEnhance
from bottle import Bottle, request, response, HTTP_CODES
from bs4 import BeautifulSoup as bs
try:
    from post import post
except ModuleNotFoundError as e:
    print(f'\033[33;1m{e}: post_template.py を参考に post.py を作成してください\033[m')
    exit(1)
from pystray import Icon, Menu, MenuItem
from tenacity import RetryError
import darkdetect as dd
import requests

from calc import calc
from config import Config
from getList import getList
from getLocation import getLocation, getNearWard
from getLog import getLog
from get_epicenter import get_epicenter
from utils import resource_path
from vvox import vvox

TITLE = 'quake'
INTERVAL = 1
TIMEOUT = 2
CHECK_INTERVAL = 5
CHECK_SPAN = 10 * 60
CALC_INTENSITY = 0.5
KMONI = 'http://www.kmoni.bosai.go.jp'
LMONI = 'https://www.lmoni.bosai.go.jp/monitor/'
YAHOO_LIST = 'https://typhoon.yahoo.co.jp/weather/jp/earthquake/list/'
# https://www.jma.go.jp/jma/kishou/know/shindo/index.html
QUAKE_CLASS = '1 2 3 4 5弱 5強 6弱 6強 7'.split()
PreferredAppMode = {
    'Light': 0,
    'Dark': 1,
}
# https://github.com/moses-palmer/pystray/issues/130
ctypes.windll['uxtheme.dll'][135](PreferredAppMode[dd.theme()])

# logger settings
logname = getLog(TITLE, 'log.log')
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(logname, encoding='utf-8', maxBytes=1000000, backupCount=0),
        logging.StreamHandler(),
    ],
    datefmt='%Y/%m/%d %X'
)
logger = logging.getLogger(TITLE)
logger.setLevel(logging.DEBUG)


class Sound(Enum):
    ALERT = 1
    WARNING = 2


# 保存する設定の型定義
@dataclass
class Setting:
    check: dict
    sound: bool
    wsound: bool
    epicenter: bool
    delay: int
    mapboxes: dict


class taskTray:
    def __init__(self):
        self.stop_event = threading.Event()
        self.progress = False
        self.config = Config(TITLE)
        self.api_server = Bottle()
        self.setup_routes()
        self.sound_queue = queue.Queue()
        # 待機スレッド
        self.threads = {}
        # レポート初期化
        self.reports = {}
        # 位置情報取得
        self.location = getLocation()
        self.ward = getNearWard(self.location)

        # quake class check: 1, 2 is False
        self.quake_check = {i: (i not in ['1', '2']) for i in QUAKE_CLASS}
        self.sound = True
        self.wsound = True
        self.epicenter = False
        # epicenter use MAPBOX API keys
        self.mapboxes = {}

        self.r_icon = Image.open(resource_path('Assets/catfish.ico'))
        self.n_icon = ImageEnhance.Brightness(self.r_icon).enhance(0.5)
        # 遅延受信サブメニュー設定
        self.delay = 3
        self.delay_menu = []
        for t in range(6):
            self.delay_menu.append(
                MenuItem(str(t), self.setDelay, checked=lambda item: str(self.delay) == str(item))
            )
        # 検知震度サブメニュー設定
        self.intensity_menu = []
        for i in self.quake_check:
            self.intensity_menu.append(MenuItem(i, self.setIntensity, checked=lambda x: self.quake_check[str(x)]))
        # 設定読み込み
        self.load_config()
        # メニュー設定
        menu = self.update_menu()
        title = getList(requests.Session()).get_title(None)
        self.app = Icon(name=f'PYTHON.win32.{TITLE}', title=title, icon=self.n_icon, menu=menu)

    def load_config(self):
        try:
            setting = Setting(**self.config.load())
            self.quake_check = setting.check
            self.sound = setting.sound
            self.wsound = setting.wsound
            self.delay = setting.delay
            self.epicenter = setting.epicenter
            self.mapboxes = setting.mapboxes
        except TypeError:
            pass

        # environments check
        if not self.mapboxes:
            import os

            access_token = os.environ.get('MAPBOX_ACCESS_TOKEN')
            username = os.environ.get('MAPBOX_USERNAME')
            style_id = os.environ.get('MAPBOX_STYLE_ID')
            if access_token and username and style_id:
                # import from environments
                self.mapboxes.update({
                    'MAPBOX_ACCESS_TOKEN': access_token,
                    'MAPBOX_USERNAME': username,
                    'MAPBOX_STYLE_ID': style_id,
                })

        self.save_config()

    def save_config(self):
        setting = Setting(
            check=self.quake_check,
            sound=self.sound,
            wsound=self.wsound,
            epicenter=self.epicenter,
            delay=self.delay,
            mapboxes=self.mapboxes,
        )
        self.config.save(asdict(setting))

    def update_menu(self):
        for i in self.quake_check:
            if self.quake_check[i]:
                break
        item = [
            MenuItem('default', self.doIt, default=True, visible=False),

            MenuItem(self.ward, self.reposition),
            Menu.SEPARATOR,
            MenuItem('長周期地震動モニタ', self.openLMONI),
            MenuItem('地震の履歴一覧', self.openYahoo),
            Menu.SEPARATOR,
            MenuItem('Alert Sound', self.toggleSound, checked=lambda _: self.sound),
            MenuItem('Warn Sound', self.toggleWSound, checked=lambda _: self.wsound),
            MenuItem('Report Epicenter', self.toggleEpicenter, checked=lambda _: self.epicenter),
            MenuItem('Delay', Menu(*self.delay_menu)),
            MenuItem(f'Intensity {i}',  Menu(*self.intensity_menu)),
            Menu.SEPARATOR,
            MenuItem('Exit', self.stopApp),
        ]
        return Menu(*item)

    def doIt(self):
        if self.progress:
            url = LMONI
        else:
            url = YAHOO_LIST
        webbrowser.open(url)

    def reposition(self, _, __):
        loc = getLocation()
        if self.location != loc:
            logger.info(f'repositioned {self.location} to {loc}')
            self.location = loc
            self.ward = getNearWard(self.location)
            self.app.menu = self.update_menu()

    def openLMONI(self):
        webbrowser.open(LMONI)

    def openYahoo(self):
        webbrowser.open(YAHOO_LIST)

    def toggleSound(self, _, __):
        self.sound = not self.sound
        self.save_config()

    def toggleWSound(self, _, __):
        self.wsound = not self.wsound
        self.save_config()

    def toggleEpicenter(self, _, __):
        self.epicenter = not self.epicenter
        self.save_config()

    def setDelay(self, _, item):
        self.delay = int(str(item))
        self.save_config()

    def setIntensity(self, _, item):
        item = str(item)
        flag = False
        for i in self.quake_check:
            if i == item:
                flag = True
            self.quake_check[i] = flag
        self.app.menu = self.update_menu()

        self.save_config()

    def sound_worker(self):
        while not self.stop_event.is_set():
            try:
                sound = self.sound_queue.get(timeout=0.1)
                match sound:
                    case Sound.ALERT:
                        self.doAlert()
                    case Sound.WARNING:
                        self.doWarn()
            except Exception:
                pass

    def doAlert(self):
        if not self.sound:
            return

        winsound.PlaySound(
            resource_path('Assets/nc124106m.wav'),
            winsound.SND_FILENAME | winsound.SND_ASYNC
        )

    def doWarn(self):
        if not self.wsound:
            return

        winsound.PlaySound(
            resource_path('Assets/warning.wav'),
            winsound.SND_FILENAME | winsound.SND_ASYNC
        )

    def doMonitor(self):
        """
        待機スレッド
        """
        # session for KMONI
        session = requests.Session()

        pre_result = None
        while not self.stop_event.is_set():
            # 受信開始
            now = (dt.now() - td(seconds=self.delay)).strftime('%Y%m%d%H%M%S')
            url = f'{KMONI}/webservice/hypo/eew/{now}.json'
            begin = time.perf_counter()

            try:
                with session.get(url, timeout=TIMEOUT) as r:
                    data = r.json()

                    progress = not not data.get('report_id')
                    if progress is not self.progress:
                        logger.debug(f'progress changed from {self.progress} to {progress}')
                        self.progress = progress
                        self.app.icon = self.r_icon if self.progress else self.n_icon

                    if self.progress:
                        self.sound_queue.put(Sound.WARNING)

                    if data.get('report_time'):
                        # logger.debug(data)
                        # 使えそうなパラメータ
                        # {
                        #     'report_time': '2025/11/25 18:01:27',
                        #     'report_id': '20251125180119',
                        #     'origin_time': '20251125180116',
                        #     'is_training': False,
                        #     'report_num': '5',
                        #     'is_final': False,
                        #     'region_name': '熊本県阿蘇地方',
                        #     'latitude': '33',
                        #     'longitude': '131.1',
                        #     'depth': '10km',
                        #     'magunitude': '5.7',
                        #     'calcintensity': '5強',
                        # }
                        report_id = data.get('report_id')
                        region_name = data.get('region_name')
                        calcintensity = data.get('calcintensity')
                        latitude = data.get('latitude')
                        longitude = data.get('longitude')
                        depth = data.get('depth')
                        magunitude = data.get('magunitude')
                        lines = [
                            '【訓練】' if data.get('is_training') else '',
                            data.get('report_time') + (' 最終報' if data.get('is_final') else f' 第{data.get("report_num")}報'),
                            region_name,
                            f'M{magunitude} 深さ {depth}',
                            f'最大予測震度 {calcintensity}',
                        ]
                        self.app.title = '\n'.join(lines).strip()
                        result = ' '.join(lines).strip()

                        eq_pos = (
                            float(latitude),
                            float(longitude),
                            int(depth.removesuffix('km')),
                            float(magunitude),
                        )
                        dist, delta, intensity = calc(report_id, self.location, eq_pos)
                        if intensity > CALC_INTENSITY:
                            if delta >= 0 and (delta < 5 or int(delta) % 5 == 0):
                                message = f'{report_id} 到達まであと {int(delta)} 秒'
                                self.app.title = message
                                logger.debug(message)

                        if pre_result != result:
                            logger.debug(result)
                            pre_result = result

                        # 指定された震度または有感の可能性がある場合監視開始
                        if (self.quake_check[calcintensity] or (intensity > CALC_INTENSITY)) and (
                                self.reports.get(report_id, {}).get('region_name') != region_name
                                or
                                self.reports.get(report_id, {}).get('calcintensity') != calcintensity
                                or
                                self.reports.get(report_id, {}).get('depth') != depth
                                or
                                self.reports.get(report_id, {}).get('magunitude') != magunitude
                        ):
                            self.reports[report_id] = {
                                'region_name': region_name,
                                'calcintensity': calcintensity,
                                'latitude': latitude,
                                'longitude': longitude,
                                'depth': depth,
                                'magunitude': magunitude,
                            }
                            if report_id not in self.threads:
                                # 監視スレッドスタート
                                self.threads[report_id] = threading.Thread(target=self.doCheck, name=report_id)
                                self.threads[report_id].start()

                                if self.epicenter:
                                    # 震央取得
                                    text, epi_url = get_epicenter(float(latitude), float(longitude), mapboxes=self.mapboxes)
                                    data = {
                                        'text': text or region_name,
                                        'image_url': epi_url,
                                    }
                                    logger.info(f'epicenter {data}')
                                    try:
                                        post(data)
                                    except RetryError:
                                        logger.warning(f'Task epicenter post error {now}')
                                    except requests.exceptions.Timeout as e:
                                        logger.warning(f'Task epicenter post Timeout {e} {now}')

                            try:
                                post({
                                    'text': result,
                                })
                                logger.info(result)
                            except RetryError:
                                logger.warning(f'Task post error {now}')
                            except requests.exceptions.Timeout as e:
                                logger.warning(f'Task post Timeout {e} {now}')
            except requests.exceptions.Timeout:
                pass
            except Exception as e:
                logger.warning(f'Task Exception {e} {now}')

            # 監視スレッドが終了していたらスレッド・情報解放
            ths = self.threads.copy()
            if ths:
                for eid in ths:
                    th = self.threads[eid]
                    if not th.is_alive():
                        th.join()
                        del self.threads[eid]
                        del self.reports[eid]
                        logger.debug(f'Check thread {eid} Done')

            elapsed = time.perf_counter() - begin
            sleep_time = max(0, INTERVAL - elapsed)
            if self.stop_event.wait(sleep_time):
                break

    def doCheck(self):
        """
        監視スレッド
        """
        self.sound_queue.put(Sound.ALERT)

        # session for jma, yahoo
        session = requests.Session()

        eid = threading.current_thread().name
        logger.debug(f'check thread {eid} Start')

        report = self.reports[eid]
        logger.debug(self.location)
        logger.debug(report)

        eq_pos = (
            float(report['latitude']),
            float(report['longitude']),
            int(report['depth'].removesuffix('km')),
            float(report['magunitude']),
        )
        dist, delta, intensity = calc(eid, self.location, eq_pos)

        logger.debug(f'{dist=:.1f}km {delta=:.1f}s {intensity=:.4f}')
        if intensity > CALC_INTENSITY:
            message = f'警告: {int(delta)}秒後に到達します'
            logger.debug(message)
            try:
                vvox(message, speed=1.2, volume=3.0)
            except Exception:
                pass

        # 震源・震度情報が揃うまで待機
        gl = None
        found = False
        ibegin = time.perf_counter()    # information check start
        while not self.stop_event.is_set():
            # 'ttl': '震源・震度情報' であれば反映完了と思われる
            begin = time.perf_counter()

            try:
                gl = getList(session)
                data = gl.find(eid)
                if data:
                    logger.debug(f'Check list {eid} Found')
                    found = True
                    ibegin = 0          # reset information start time
                    break
            except Exception as e:
                logger.debug(f'Check list Exception {e}')

            if time.perf_counter() - ibegin >= CHECK_SPAN:
                break

            elapsed = time.perf_counter() - begin
            sleep_time = max(0, CHECK_INTERVAL - elapsed)
            if self.stop_event.wait(sleep_time):
                break

        if not found:
            logger.warning(f'Check list {eid} {self.reports[eid]} not found')

        # url contain eid check
        url = f'https://typhoon.yahoo.co.jp/weather/jp/earthquake/{eid}.html'

        rbegin = time.perf_counter()    # result check start
        while not self.stop_event.is_set():
            begin = time.perf_counter()

            try:
                with session.get(url, timeout=1) as r:
                    if r.status_code == 200:
                        soup = bs(r.content, 'html.parser')
                        meta = soup.find('meta', property='og:image')
                        if meta:
                            img_url = meta.get('content')
                            if img_url:
                                if not img_url.startswith('https://weather-pctr.c.yimg.jp/t/weather-img/earthquake/'):
                                    raise Exception('OGP not ready')

                                try:
                                    self.app.title = title = gl.get_title(eid)
                                    text = title.replace('\n', ' ')
                                    post({
                                        'text': text,
                                        'image_url': img_url,
                                    })
                                    logger.info(f'{text} {img_url}')
                                    return
                                except RetryError:
                                    logger.warning(f'Check post retry error {img_url}')
                                except requests.exceptions.Timeout as e:
                                    logger.warning(f'Check post Timeout {e} {img_url}')
                                except Exception as e:
                                    logger.warning(f'Check post error {e} {img_url}')
                    else:
                        logger.warning(f'status code {r.status_code} {url}')
                        if r.status_code == 404:
                            rbegin = 0
            except requests.exceptions.Timeout as e:
                logger.warning(f'Check Timeout {e} {url}')
            except Exception as e:
                logger.warning(f'Check Exception {e} {url}')

            if time.perf_counter() - rbegin >= CHECK_SPAN:
                break

            elapsed = time.perf_counter() - begin
            sleep_time = max(0, CHECK_INTERVAL - elapsed)
            if self.stop_event.wait(sleep_time):
                break

        logger.debug(f'Check thread {eid} Finished')

    def setup_routes(self):
        @self.api_server.route('/api/<path:path>', method=['GET', 'POST'])
        def api(path):
            def error(code):
                response.status = code
                return {'status': 'ng', 'state': HTTP_CODES[code]}

            state = None
            match request.method:
                # GET ==================================================
                case 'GET':
                    match path:
                        case 'alert':
                            state = self.sound
                        case 'warn':
                            state = self.wsound
                        case 'epicenter':
                            state = self.epicenter
                        case 'intensity':
                            for i in self.quake_check:
                                if self.quake_check[i]:
                                    break
                            state = i
                        case _:
                            return error(400)

                    return {'status': 'ok', 'state': state}
                # /GET =================================================

                # POST =================================================
                case 'POST':
                    data = None
                    match request.json:
                        case dict() as data:
                            pass
                        case _ if request.forms:
                            data = {k: request.forms.getunicode(k) for k in request.forms}
                        case _:
                            return error(400)

                    value = None
                    if path in data:
                        value = data[path]

                    match path:
                        case _ if path in ['alert', 'warn', 'epicenter']:
                            if value in ['on', 'off']:
                                match path:
                                    case 'alert':
                                        self.sound = value == 'on'
                                    case 'warn':
                                        self.wsound = value == 'on'
                                    case 'epicenter':
                                        self.epicenter = value == 'on'
                                self.app.menu = self.update_menu()
                                self.save_config()
                            else:
                                return error(400)

                        case 'intensity':
                            if value in QUAKE_CLASS:
                                self.setIntensity(None, value)
                            else:
                                return error(400)

                        case _:
                            return error(400)

                    return {'status': 'ok'}
                # /POST ================================================

                case _:
                    return error(405)

    def run_api(self):
        self.api_server.run(host='192.168.0.1', port=15678)

    def stopApp(self):
        self.stop_event.set()
        self.app.stop()

    def runApp(self):
        self.stop_event.clear()

        threading.Thread(target=self.sound_worker, daemon=True).start()
        threading.Thread(target=self.doMonitor, name='Monitor').start()
        threading.Thread(target=self.run_api, daemon=True).start()

        self.app.run()


if __name__ == '__main__':
    taskTray().runApp()
