import webbrowser
import pyperclip

hanja = pyperclip.paste()

webbrowser.open(f'https://hanja.dict.naver.com/#/search?range=all&query={hanja}')