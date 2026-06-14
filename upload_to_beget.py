import ftplib
import os
import ssl

HOST = 'palkina-therapy.ru'
USER = 'ogp56bkn_svet'
PASS = 'Ogp068999!'

LOCAL_DIR = os.path.join(os.path.dirname(__file__), 'landing')
FILES = ['index.html', 'styles.css', 'script.js']

def upload():
    print(f'Подключаюсь к {HOST} (FTPS)…', flush=True)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with ftplib.FTP_TLS(HOST, timeout=30, context=ctx) as ftp:
        ftp.login(USER, PASS)
        ftp.prot_p()   # защищённый канал данных
        print(f'  Вошёл как {USER}', flush=True)

        for fname in FILES:
            local_path = os.path.join(LOCAL_DIR, fname)
            print(f'  Загружаю {fname}…', flush=True)
            with open(local_path, 'rb') as f:
                ftp.storbinary(f'STOR {fname}', f)
            print(f'  ✓ {fname}', flush=True)

    print('\nГотово! https://palkina-therapy.ru')

if __name__ == '__main__':
    upload()
