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
from post import post
from pystray import Icon, Menu, MenuItem
from tenacity import RetryError
import darkdetect as dd
import pyaudio
import requests

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
        logging.handlers.RotatingFileHandler("log2.log", encoding='utf-8', maxBytes=1000000, backupCount=0),
        logging.StreamHandler(),
    ],
    datefmt='%Y/%m/%d %X'
)
logger = logging.getLogger(TITLE)
logger.setLevel(logging.DEBUG)


class taskTray:
    def __init__(self):
        self.running = False
        # session for KMONI
        self.session = requests.Session()
        # 待機スレッド
        self.threads = {}
        # レポート初期化
        self.reports = {}

        # quake class check: 1, 2 is False
        # self.quake_check = {i: (i not in ['1', '2']) for i in QUAKE_CLASS}
        self.quake_check = {i: (i not in []) for i in QUAKE_CLASS}
        self.sound = True

        # Stream #0:0: Audio: pcm_s16le ([1][0][0][0] / 0x0001), 22050 Hz, 1 channels, s16, 352 kb/s
        with wave.open('Assets/nc124106m.wav', 'rb') as wf:
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
        監視スレッド
        """
        while self.running:
            # 受信開始
            now = dt.now()
            url = f'{KMONI}/webservice/hypo/eew/{now.strftime("%Y%m%d%H%M%S")}.json'
            begin = time.time()

            try:
                with self.session.get(url, timeout=1) as r:
                    data = r.json()
                    if data.get('report_time'):
                        # logger.debug(data)
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

                        # 指定された震度の場合のみ監視開始
                        report_id = data.get('report_id')
                        if self.quake_check[calcintensity] and \
                           (
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
                                result = ' '.join(lines).strip()
                                post({
                                    'icon_emoji': 'hamu2',
                                    'text': result,
                                })
                                logger.info(result)
                            except RetryError:
                                logger.warning(f'Task post error {url}')
                            except requests.exceptions.Timeout as e:
                                logger.warning(f'Check post Timeout {e} {url}')
            except requests.exceptions.Timeout:
                logger.warning(f'Task Timeout {url}')
            except Exception as e:
                logger.warning(f'Task Exception {e} {url}')

            # 待機スレッドが終了していたらスレッド・情報解放
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
        # self.doAlert()

        eid = threading.current_thread().name
        # url contain eid check
        url = f'https://typhoon.yahoo.co.jp/weather/jp/earthquake/{eid}.html'
        logger.info(f'check thread {eid} start')

        # 震源・震度情報が揃うまで待機
        found = False
        icount = 0
        while self.running:
            # 'ttl': '震源・震度情報' であれば反映完了と思われる
            begin = time.time()

            try:
                with requests.get('https://www.jma.go.jp/bosai/quake/data/list.json', timeout=3) as r:
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

        rcount = 0
        while self.running:
            begin = time.time()

            try:
                with requests.get(url, timeout=1) as r:
                    if r.status_code == 200:
                        soup = bs(r.content, 'html.parser')
                        meta = soup.find('meta', property='og:image')
                        if meta:
                            img_url = meta.get('content')
                            if img_url:
                                if not img_url.startswith('https://weather-pctr.c.yimg.jp/t/weather-img/earthquake/'):
                                    raise Exception('OGP not ready')

                                logger.info(f'Check Done {self.reports[eid]['region_name']} {img_url}')

                                # try:
                                #     post({
                                #         'icon_emoji': 'hamu2',
                                #         'text': self.status.get('region_name'),
                                #         'image_url': img_url,
                                #     })
                                #     logger.info(f'Check Done {img_url}')
                                #     self.url_reported = True
                                #     self.rcount = 0
                                # except RetryError:
                                #     logger.warning(f'Check post retry error {img_url}')
                                # except requests.exceptions.Timeout as e:
                                #     logger.warning(f'Check post Timeout {e} {img_url}')
                                # except Exception as e:
                                #     logger.warning(f'Check post error {e} {img_url}')

                                return
                                # rcount = RETRY_MAX
                                # break
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
89504e470d0a1a0a0000000d4948445200000010000000100803000000282d0f530000000467414d410000b18f0bfc6105000000206348524d00007a
26000080840000fa00000080e8000075300000ea6000003a98000017709cba513c000001d7504c54450000000101010f0d0b00010103080a00020300
00000000000000001334451131410000000000001f54701b4b630000001e536f1b4a63000000081820256486225d7b08161d0000000000000b1e2824
6384235f7f08182000000000000000000008141a1c4b63276b8e2565871c4c650611160000000000002625238c8d89215b7907151d0000000000000f
212b979a970a1d260000000000002156721c4c66000000000000215a791d506b000000215b790000001f55711b4c650000000000000a1d2625668723
6080091a23000000010304050f14091c26235e7e236080091a23050f140001010001020002030002030002030001020102033ba1d63b9fd43ca3d83e
a7de3ba0d598c6da48ade13ca6de3da6de3da6dd3ea9e1399ccfd9e5e476c0e447abdf50b0e13ca6dd43a9df3da7df3a9fd392c8e16fbce345aadf7d
b6d192b2bf5ab3e05db4df93b2bf77b6d43ba1d741aae15bb6e4a4acab6f67619fd0e5a4d1e36e655faab7b854b3e33ea8e03eaae2439fd37d6d8b94
a8b891a9b067b9e26bbbe191a8b093a6b87c698842a0d53ba3d9479ed29b2f409a4a5c6f9ec34c91c24d91c2729bbf9c405099314145a0d43286b257
81ab983649933a4e933c5094394d96394d5384b03185b12d61812f5e7dffffffd3f96a210000005374524e530000000000001e1a199c93154ffaf645
fbf80669fcf95f043e73e8e36c37030259e4fdfed84e01076ae5e15f050c77ed640962efe95270fdfa5efd61eee7510b74ece761080762a2eee59d59
0b6f8786886305f4f0d3c000000001624b47449c71bcc2270000000774494d4507e8090e08280661217c2a000000d74944415418d363608000367606
14c0c1c9c58d22c0c3cbc78f2a2020882220242c222a268ee04a484a058748cbc8ca81b98cf20a8a4aa16161e1ca2aaa6a8c0c0c4cea1a9a119151d1
3151b1715ada3acc0cba7afaf1098949c9c94929a9695206860c46c6e9199959d939b979f929a90526a60c66e685c945c525a565e51595c95516960c
6656d535b575f50d8d4dcd2dadb140016b9bb6f68eceaeee9edebefe09c1b6760cf60e8e13274d9e3275eab4e933663a39bb30b0b8bab97bcc9a0d04
b33cbdbcc599812e63f6f1f5f3078280c0205606060074d237e8377bca260000002574455874646174653a63726561746500323032342d30392d3133
5432333a34303a30362b30393a3030d2b5b6cf0000002574455874646174653a6d6f6469667900323032342d30392d31335432333a34303a30362b30
393a3030a3e80e730000000049454e44ae426082
"""

if __name__ == '__main__':
    taskTray().runApp()
