#!/usr/bin/env sh

if [ "$(id -u)" != "0" ]; then
    echo 請使用 root 帳號執行腳本
    exit 1
fi

echo 更新套件資料...
sleep 0.5
apt-get update
if [ $? -ne 0 ]; then
    echo 無法更新套件資料
    exit 1
fi

echo 安裝必要系統套件...
sleep 0.5
sudo apt-get -y install uwsgi nginx python3-pip git libpq-dev python3-dev uwsgi-plugin-python3 build-essential chrpath libssl-dev libxft-dev libfreetype6 libfreetype6-dev libfontconfig1 libfontconfig1-dev phantomjs
if [ $? -ne 0 ]; then
    echo 無法安裝必要系統套件...
    exit 1
fi


echo "安裝 python 相關套件..."
sleep 0.5
pip3 install --upgrade pip
pip3 install django psycopg2 line-bot-sdk python-dateutil


echo "準備安裝 ukumpcore..."
[ -d /var/repository ] && echo "/var/repository 已建立" || mkdir /var/repository


cd /var/repository
if [ -d ukump_linebot ]; then
    echo 準備更新程式碼...
    cd ukump_linebot
    git pull
else
    echo 下載程式碼...
    git clone https://github.com/yagami-cerberus/ukump_linebot.git
fi

if [ $? -ne 0 ]; then
    echo 下載/更新程式碼時發生問題，請確認存取權限
    exit 1
fi


echo "準備資料庫"
sleep 0.5
apt-get install postgresql
sudo -u postgres createdb ukumpcore


echo "覆蓋 uwsgi 設定檔: /etc/uwsgi/apps-enabled/ukumpcore.xml"
sleep 0.5
cat > /etc/uwsgi/apps-enabled/ukumpcore.xml <<- EOM
<uwsgi>

<plugin>python3</plugin>
<socket>/tmp/ukumpcore_socket</socket>
<chdir>/var/repository/ukump_linebot</chdir>
<module>ukumpcore.wsgi</module>
<uid>postgres</uid>
<gid>www-data</gid>
<master/>
<processes>8</processes>

</uwsgi>
EOM

ln -s /etc/uwsgi/apps-available/ukumpcore.xml /etc/uwsgi/apps-enabled/ukumpcore.xml

echo "覆蓋 nginx ssl 設定檔: /etc/nginx/sites-enabled/ssl"
sleep 0.5
cat > /etc/nginx/sites-enabled/ssl <<- EOM
server {
  listen 443 default ssl;
  ssl_certificate /etc/ssl/nginx_fullchain.pem;
  ssl_certificate_key /etc/ssl/nginx_privkey.pem;

  # server_name neuron.fluxmach.com;

  access_log /var/log/nginx/ssl.access.log;
  error_log /var/log/nginx/ssl.error.log;
  root /var/www/shared;

  location /static/ {
    autoindex on;
    root /var/www/fluxneuron/;
  }

  location / {
    include uwsgi_params;
    uwsgi_pass unix:/tmp/ukumpcore_socket;
  } 
}
EOM


apt-get install postgresql

echo "準備設定檔"
cd /var/repository/ukump_linebot
if [ -n /etc/ukump_linebot.secret ]; then
    head -c 1024 < /dev/urandom > /etc/ukump_linebot.secret
    rm /var/repository/ukump_linebot/ukumpcore/settings.py
fi

[ -f /var/repository/ukump_linebot/ukumpcore/settings.py ] && echo "設定檔已存在" || cp /var/repository/ukump_linebot/ukumpcore/settings.py.example /var/repository/ukump_linebot/ukumpcore/settings.py
sudo -u postgres ./manage.py createcachetable
if [ $? -ne 0 ]; then
    echo "建立快取資料表時發生錯誤"
    exit 1
fi

sudo -u postgres ./manage.py migrate
if [ $? -ne 0 ]; then
    echo "Migrate 資料表時發生錯誤"
    exit 1
fi

if [ -f /etc/ssl/nginx_fullchain.pem ]; then
    echo ""
else
    openssl req -x509 -newkey rsa:4096 -nodes -keyout /etc/ssl/nginx_privkey.pem -out /etc/ssl/nginx_fullchain.pem -days 365 -subj "/C=US/ST=Denial/L=Springfield/O=Dis/CN=www.example.com"
fi

sudo /etc/init.d/uwsgi restart
sudo /etc/init.d/nginx restart
