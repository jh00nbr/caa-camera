#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gflags
import os
import sys
import time
import base64
import threading
import tornado.web
import tornado.websocket
import tornado.httpserver

gflags.DEFINE_integer("port", None, "port the server listen on")
gflags.DEFINE_string("ui_server_url", "http://localhost:5001", "ui_server_url")

FLAGS = gflags.FLAGS


class ImageHolder(object):
    """画像のバッファの入れ物."""

    def __init__(self):
        self._buffer = dict()
        self._lock = threading.Lock()
        with open("./static/img/default.jpg", "rb") as f:
            self._default_image = f.read()

    def push(self, index, buf):
        """画像の追加."""
        with self._lock:
            self._buffer[index] = buf

    def pop(self, index):
        """画像を取り出し，Noneをセットする"""
        with self._lock:
            if index not in self._buffer:
                return self._default_image
            buf = self._buffer[index]
            self._buffer[index] = None
            return buf

    def del_index(self, index):
        """キーを削除する"""
        self._buffer.pop(index)


class HttpHandler(tornado.web.RequestHandler):
    """HTTPのハンドラ

    /watchに対応．普通にindex.htmlを返す．
    """
    def initialize(self):
        pass

    def get(self, index):
        self.render("index.html",
                    index=index, ui_server_url=FLAGS.ui_server_url)


class WSPopHandler(tornado.websocket.WebSocketHandler):
    """ブラウザへの画像の送信

    /popに対応．
    """

    def initialize(self, image_holder):
        self.state = True
        self.image_holder = image_holder
        self.index = None

    def open(self, index):
        print index
        self.index = index
        # 送信スレッドの作成
        t = threading.Thread(target=self.loop)
        t.setDaemon(True)
        t.start()

    def loop(self):
        """メインスレッドと非同期でクライアントに画像を送りつける"""
        while self.state:
            buf = self.image_holder.pop(self.index)
            if buf:
                self.write_message(buf, binary=True)
            time.sleep(0.05)

    def on_close(self):
        # 映像送信のループを終了させる
        self.state = False
        self.close()
        print("close: " + self.request.remote_ip)


class WSPushHandler(tornado.websocket.WebSocketHandler):
    """Piからの画像を受け取るハンドラ

    /push に対応．

    画像はbase64でエンコードされて送られてくる（on_messageでバイナリで
    受け取る方法がわからなかったため）．
    """
    def initialize(self, image_holder):
        self.image_holder = image_holder
        self.index = None

    def open(self, index):
        print("open: " + self.request.remote_ip)
        self.index = index

    def on_message(self, msg):
        buf = base64.b64decode(msg)
        self.image_holder.push(self.index, buf)

    def on_close(self):
        self.close()
        self.image_holder.del_index(self.index)
        print(self.request.remote_ip, ": connection closed")


def main(argv):
    argv = gflags.FLAGS(argv)
    print("start!")

    # 初期画像
    holder = ImageHolder()

    # ハンドラの登録
    # ２つのハンドラに同じimg_listを渡しているのに注目！
    handlers = [
        (r"/watch/([0-9a-zA-Z]+)", HttpHandler),
        (r"/pop/([0-9a-zA-Z]+)", WSPopHandler, dict(image_holder=holder)),
        (r"/push/([0-9a-zA-Z]+)", WSPushHandler, dict(image_holder=holder)),
    ]
    settings = dict(
        template_path=os.path.join(os.path.dirname(__file__), "templates"),
        static_path=os.path.join(os.path.dirname(__file__), "static"),)
    app = tornado.web.Application(handlers, **settings)
    http_server = tornado.httpserver.HTTPServer(app)
    if FLAGS.port:
        port = FLAGS.port
    else:
        port = int(os.environ.get("PORT", 5000))
    print port
    http_server.listen(port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    main(sys.argv)
