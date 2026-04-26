# -*- coding: utf-8 -*-
from datetime import datetime as dt
import binascii
import ctypes
import io
import logging
import logging.handlers
import threading
import time
import wave
import webbrowser

from PIL import Image
from bs4 import BeautifulSoup as bs
try:
    from post import post
except ModuleNotFoundError as e:
    print(f'\033[33;1m{e}: post_template.py を参考に post.py を作成してください\033[m')
    exit(1)
from pystray import Icon, Menu, MenuItem
from tenacity import RetryError
import darkdetect as dd
import pyaudio
import requests

from utils import resource_path

TITLE = 'quake'
INTERVAL = 1
CHECK_INTERVAL = 30
RETRY_MAX = 15
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
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler("log.log", encoding='utf-8', maxBytes=1000000, backupCount=0),
        logging.StreamHandler(),
    ],
    datefmt='%Y/%m/%d %X'
)
logger = logging.getLogger(TITLE)
logger.setLevel(logging.DEBUG)


class taskTray:
    def __init__(self):
        self.running = False
        # 待機スレッド
        self.threads = {}
        # レポート初期化
        self.reports = {}

        # quake class check: 1, 2 is False
        self.quake_check = {i: (i not in ['1', '2']) for i in QUAKE_CLASS}
        self.sound = True

        with wave.open(resource_path('Assets/nc124106m.wav'), 'rb') as wf:
            self.alert_sound = wf.readframes(wf.getnframes())
            self.sample = wf.getsampwidth()
            self.channels = wf.getnchannels()
            self.rate = wf.getframerate()

        image = Image.open(io.BytesIO(binascii.unhexlify(ICON.replace('\n', '').strip())))
        item = [
            MenuItem('LMONI', self.openLMONI, default=True),
            MenuItem('List', self.openYahoo),
            Menu.SEPARATOR,
            MenuItem('Sound', self.toggleSound, checked=lambda _: self.sound),
            Menu.SEPARATOR,
            MenuItem('Set All', self.setAll),
            MenuItem('Unset All', self.unsetAll),
            Menu.SEPARATOR,
        ]
        # TODO: change toggle to slider
        for i in self.quake_check:
            item.append(MenuItem(i, self.toggle, checked=lambda x: self.quake_check[str(x)]))
        item.append(Menu.SEPARATOR)
        item.append(MenuItem('Exit', self.stopApp))
        menu = Menu(*item)
        self.app = Icon(name=f'PYTHON.win32.{TITLE}', title=TITLE, icon=image, menu=menu)

    def toggleSound(self, _, __):
        self.sound = not self.sound
        self.app.update_menu()

    def doAlert(self):
        if not self.sound:
            return

        pya = pyaudio.PyAudio()
        stream = pya.open(
            format=pya.get_format_from_width(self.sample),
            channels=self.channels,
            rate=self.rate,
            output=True,
        )
        stream.write(self.alert_sound)
        stream.stop_stream()
        stream.close()
        pya.terminate()

    def openLMONI(self):
        webbrowser.open(LMONI)

    def openYahoo(self):
        webbrowser.open(YAHOO_LIST)

    def setAll(self):
        for i in self.quake_check:
            self.quake_check[i] = True
        self.app.update_menu()

    def unsetAll(self):
        for i in self.quake_check:
            self.quake_check[i] = False
        self.app.update_menu()

    def toggle(self, _, _item):
        item = str(_item)
        self.quake_check[item] = not self.quake_check[item]
        self.app.update_menu()

    def doMonitor(self):
        """
        待機スレッド
        """
        # session for KMONI
        session = requests.Session()

        pre_result = None
        while self.running:
            # 受信開始
            now = dt.now().strftime("%Y%m%d%H%M%S")
            url = f'{KMONI}/webservice/hypo/eew/{now}.json'
            begin = time.time()

            try:
                with session.get(url, timeout=INTERVAL - 0.1) as r:
                    data = r.json()
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
                        region_name = data.get('region_name')
                        calcintensity = data.get('calcintensity')
                        magunitude = data.get('magunitude')
                        lines = [
                            '【訓練】' if data.get('is_training') else '',
                            data.get('report_time') + (' 最終報' if data.get('is_final') else f' 第{data.get("report_num")}報'),
                            region_name,
                            f'M{magunitude} 深さ {data.get("depth")}',
                            f'最大予測震度 {calcintensity}',
                        ]
                        self.app.title = '\n'.join(lines).strip()
                        self.app.update_menu()

                        report_id = data.get('report_id')
                        result = ' '.join(lines).strip()

                        if pre_result != result:
                            logger.debug(result)
                            pre_result = result

                        # 指定された震度の場合のみ監視開始
                        if self.quake_check[calcintensity] and \
                           (
                               self.reports.get(report_id, {}).get('region_name') != region_name
                               or
                               self.reports.get(report_id, {}).get('calcintensity') != calcintensity
                               or
                               self.reports.get(report_id, {}).get('magunitude') != magunitude
                           ):
                            if report_id not in self.threads:
                                # 監視スレッドスタート
                                self.threads[report_id] = threading.Thread(target=self.doCheck, name=report_id)
                                self.threads[report_id].start()

                            self.reports[report_id] = {
                                'region_name': region_name,
                                'calcintensity': calcintensity,
                                'magunitude': magunitude,
                            }
                            try:
                                post({
                                    'text': result,
                                })
                                logger.info(result)
                            except RetryError:
                                logger.warning(f'Task post error {now}')
                            except requests.exceptions.Timeout as e:
                                logger.warning(f'Check post Timeout {e} {now}')
            except requests.exceptions.Timeout:
                logger.warning(f'Task Timeout {now}')
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
                        logger.info(f'Check thread {eid} Done')

            # for th in threading.enumerate():
            #     if th.name not in ['MainThread', 'Monitor']:
            #         print('  ', th.name)

            elapsed = time.time() - begin
            # print(url, elapsed)
            if elapsed < INTERVAL:
                time.sleep(INTERVAL - elapsed)

    def doCheck(self):
        """
        監視スレッド
        """
        self.doAlert()

        # session for jma, yahoo
        session = requests.Session()

        eid = threading.current_thread().name
        logger.info(f'check thread {eid} start')

        # 震源・震度情報が揃うまで待機
        found = False
        icount = 0
        while self.running:
            # 'ttl': '震源・震度情報' であれば反映完了と思われる
            begin = time.time()

            try:
                with session.get('https://www.jma.go.jp/bosai/quake/data/list.json', timeout=3) as r:
                    for j in r.json():
                        if j.get('eid') == eid and j.get('ttl') == '震源・震度情報':
                            logger.info(f'Check list {eid} found')
                            found = True
                            icount = RETRY_MAX
                            break
                icount += 1
            except Exception as e:
                logger.debug(f'Check list Exception {e}')

            if icount >= RETRY_MAX:
                break

            elapsed = time.time() - begin
            # logger.debug(f'Check list {eid} {elapsed}')
            if elapsed < CHECK_INTERVAL:
                time.sleep(CHECK_INTERVAL - elapsed)

        if not found:
            logger.info(f'Check list {eid} {self.reports[eid]} not found')
            return

        # url contain eid check
        url = f'https://typhoon.yahoo.co.jp/weather/jp/earthquake/{eid}.html'

        rcount = 0
        while self.running:
            begin = time.time()

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
                                    post({
                                        'text': self.reports[eid]['region_name'],
                                        'image_url': img_url,
                                    })
                                    logger.info(f'Check Done {self.reports[eid]['region_name']} {img_url}')
                                    return
                                except RetryError:
                                    logger.warning(f'Check post retry error {img_url}')
                                except requests.exceptions.Timeout as e:
                                    logger.warning(f'Check post Timeout {e} {img_url}')
                                except Exception as e:
                                    logger.warning(f'Check post error {e} {img_url}')
                    else:
                        logger.warning(f'status code {r.status_code} {url}')
                        rcount += 1
            except requests.exceptions.Timeout as e:
                logger.warning(f'Check Timeout {e} {url}')
                rcount += 1
            except Exception as e:
                logger.warning(f'Check Exception {e} {url}')
                rcount += 1

            if rcount >= RETRY_MAX:
                break

            elapsed = time.time() - begin
            # logger.debug(f'Check yahoo {url} {elapsed}')
            if elapsed < CHECK_INTERVAL:
                time.sleep(CHECK_INTERVAL - elapsed)

        logger.info(f'Check thread {eid} Finished')

    def stopApp(self):
        self.running = False
        self.app.stop()

    def runApp(self):
        self.running = True

        monitor_thread = threading.Thread(target=self.doMonitor, name='Monitor')
        monitor_thread.start()

        self.app.run()


ICON = """
47494638396110001000f700006b6b3f6c6c3e6e6e3e7676367d7d337979367979377171387373397676394242424c4c4746464a47474a4848494949
494a4a4849494a4a4a4a4b4b4b4f4f494d4d4b4f4f4a4e4e4b48484c4b4b4c4a4a4d4b4b4d4c4c4c4d4d4d4f4f4f5555435151455252455353475151
485353485353495454484f4f535050505151515252515252525353535757575555585858585959595d5d5d5e5e5e65654066665b7f7f5570705d6464
6364646465656567676569696762626a6464686a6a697f7f797e7e7ab9b91bbfbf19baba1cbbbb1c96962995952b99992899992a9d9d28818134a0a0
25a1a126a9a92aacac28adad34a0a03dc7c717cece14cfcf14d2d211d3d311d4d410dcdc15d4d41bd4d41cd5d51ce1e10ce8e809f0f006f0f007f5f5
04f6f604f8f803f9f903fcfc01ffff00ffff01fefe02f9f904fafa04f4f408fdfd08e8e810e9e910c5c52bc5c52cd6d626d4d4298080488c8c4a9292
46efef4ff0f04dd6d670d6d672e6e69ae6e69cd7d7c6d8d8c5d6d6cfd8d8d1d9d9d1dadad2e3e3c0e2e2c1e1e1ce0000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
0021f904000000000021ff0b496d6167654d616769636b0e67616d6d613d302e343534353435002c00000000100010000008d5009fd48853e0c38310
03848421c3b0a18d1e34042c78f0a0410824601a3294c3038a17020d285264a291cc953958c8041149f103959267185a09c1b28191920da984c8c0a1
6706041919869112858b129e3d396498b1258a9430494c9040502169d20a0848986052812752ab3e959248d055850ab01ccc66a860c0cb1000697b9a
95cb41c0102f0c8d9c78d1428502052a5ebc38814463131738649c4d2b03870b271ae100f17103c78e1d386ef888f3a6611a3777f4f0f143da0f9f3d
77dca42173260b1b3574f204122428109e3a6ad864391310003b
"""

if __name__ == '__main__':
    taskTray().runApp()
