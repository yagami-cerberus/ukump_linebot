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

echo 安裝 nodejs 相關套件(出png圖用)...
sleep 0.5
npm install -g phantomjs


echo 安裝 python 相關套件...
sleep 0.5
pip3 install --upgrade pip
pip3 install django psycopg2 line-bot-sdk python-dateutil


echo 準備安裝 ukumpcore...
[ -d /var/repository ] && echo "/var/repository 已建立" || mkdir /var/repository

if [ -f ~/.ssh/id_rsa.pub ]; then
    echo ""
else
    echo 準備建立 ssh key
    ssh-keygen -f ~/.ssh/id_rsa -N ''
    if [ $? -ne 0 ]; then
        echo 建立 ssh key 時發生問題
        exit 1
    fi
fi

cd /var/repository
if [ -d ukumpcore ]; then
    echo 準備更新程式碼...
    cd ukumpcore
    git pull
else
    echo 下載程式碼...
    git clone git@bitbucket.org:Yagami/ukumpcore.git
fi

if [ $? -ne 0 ]; then
    echo 下載/更新程式碼時發生問題，請確認存取權限，必要時請提供公鑰:
    cat ~/.ssh/id_rsa.pub
    exit 1
fi

echo 安裝程序完成，請確認後續安裝程序
echo "1. ukumpcore 設定"
echo "2. 資料庫 migration"
echo "3. uwsgi 設定"
echo "4. Web Server (nginx or apache) 設定"
