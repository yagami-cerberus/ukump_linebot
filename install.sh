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
sudo apt-get -y install uwsgi python3-pip git libpq-dev python3-dev uwsgi-plugin-python3 nodejs npm
if [ $? -ne 0 ]; then
    echo 無法安裝必要系統套件...
    exit 1
fi

echo "安裝 nodejs 相關套件(出png圖用)..."
sleep 0.5
npm install -g phantomjs


echo 安裝 python 相關套件...
sleep 0.5
pip3 install --upgrade pip
pip3 install django psycopg2 line-bot-sdk python-dateutil


echo 準備安裝 ukumpcore...
[ -d /var/repository ] && echo "/var/repository 已建立" || mkdir /var/repository


cd /var/repository
if [ -d ukumpcore ]; then
    echo 準備更新程式碼...
    cd ukumpcore
    git pull
else
    echo 下載程式碼...
    git clone git@github.com:yagami-cerberus/ukump_linebot.git
fi

if [ $? -ne 0 ]; then
    echo 下載/更新程式碼時發生問題，請確認存取權限
    exit 1
fi


echo 覆蓋 uwsgi 設定檔: /etc/uwsgi/apps-enabled/ukumpcore.xml
sleep 0.5
cat > /etc/uwsgi/apps-enabled/ukumpcore.xml <<- EOM
<uwsgi>

<plugin>python3</plugin>
<socket>/tmp/ukumpcore_socket</socket>
<chdir>/var/repository/ukumpcore</chdir>
<module>ukumpcore.wsgi</module>
<uid>www-data</uid>
<gid>www-data</gid>
<master/>
<processes>8</processes>

</uwsgi>
EOM

ln -s /etc/uwsgi/apps-available/ukumpcore.xml /etc/uwsgi/apps-enabled/ukumpcore.xml


echo 覆蓋 nginx ssl 設定檔: /etc/nginx/sites-enabled/ssl
sleep 0.5
cat > /etc/nginx/sites-enabled/ssl <<- EOM
server {
  listen 443 default ssl;
  ssl_certificate /etc/letsencrypt/live/neuron.fluxmach.com/fullchain.pem; # managed by Certbot
  ssl_certificate_key /etc/letsencrypt/live/neuron.fluxmach.com/privkey.pem; # managed by Certbot

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


echo 安裝程序完成，請確認後續安裝程序
echo "1. ukumpcore 設定"
echo "2. 資料庫 migration"
