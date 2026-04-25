# quake

緊急地震速報を音などでお知らせ

## Run

```powershell
git clone https://github.com/sharl/quake.git
cd quake
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cp post_template.py post.py
python quake.py
```

## Build

```powershell
pip install pyinstaller
pyinstaller quake.py --clean --onefile --noconsole --icon .\Assets\catfish.ico --add-data "Assets/nc124106m.wav;Assets"
```

dist/ 配下に実行ファイルが生成されます

## sound

ニュース速報のアラーム - ニコニ・コモンズ  
https://commons.nicovideo.jp/works/nc124106  
をトリミングしたものを利用しています
