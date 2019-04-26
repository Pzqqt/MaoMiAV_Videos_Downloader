#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import os
import sys
import tempfile
import shutil
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from argparse import ArgumentParser

class MaomiAV:

    req_timeout = 10
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Apple"
                       "WebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3"
                       "202.94 Safari/537.36")
    }

    def __init__(self, url, jobs, road, proxies):
        self.url = url
        if "play-" not in self.url:
            self.url = "%s/play-%s" % tuple(self.url.rsplit("/", 1))
        self.jobs = self.set_jobs(jobs)
        self.road = self.set_road(road)
        self.proxies = proxies
        self.bs4_parser = select_bs4_parser()
        if not self.bs4_parser:
            print("\nFailed to run this program!")
            print("\nPlease install at least one parser in \"lxml\" and \"html5lib\"!")
            sys.exit()

    @staticmethod
    def set_jobs(jobs):
        if jobs <= 1:
            return 1
        if jobs >= 32:
            return 32
        jobs_list = [2**x for x in range(6)]
        for x in range(5):
            if jobs_list[x] <= jobs < jobs_list[x+1]:
                return jobs_list[x]

    @staticmethod
    def set_road(road):
        if road == 1:
            return "head"
        if road == 2:
            return "head1"
        if road == 3:
            return "head2"
        return "head1"

    def run(self):
        self.bs = self.get_bs()
        self.get_m3u8()
        self.temp_dir = tempfile.mkdtemp(prefix="mmav_")
        self.dst_filename = self.adj_file_name(self.get_title()) + ".mp4"
        print("File name: " + self.dst_filename)
        if hasattr(self, "video_url"):
            dload_file_all(self.jobs, self.temp_dir, self.proxies, [self.video_url,])
        else:
            dload_file_all(self.jobs, self.temp_dir, self.proxies, self.m3u8_tss_urls)
        if hasattr(self, "video_url"):
            file2file(os.path.join(self.temp_dir, os.listdir(self.temp_dir)[0]),
                      os.path.join(os.getcwd(), self.dst_filename))
        else:
            print("\nMerge files...")
            self.merge_ts()
            file2dir(os.path.join(self.temp_dir, self.dst_filename), os.getcwd())
        remove_path(self.temp_dir)
        print("\nDone!")

    def get_bs(self):
        # 使用浏览器 UA 来请求页面
        req = requests.get(url=self.url,
                           headers=self.headers,
                           timeout=self.req_timeout,
                           proxies={"http": self.proxies, "https": self.proxies})
        req.encoding = "utf-8"
        return BeautifulSoup(req.text, self.bs4_parser)

    def get_m3u8(self):
        m3u8_script = self.get_m3u8_script()
        self.m3u8_info = {}
        for line in m3u8_script:
            if not line.strip():
                continue
            if "var video" in line:
                self.m3u8_info["end"] = line.split()[-1][1:-2]
            if "var m3u8_host" in line:
                self.m3u8_info["head"] = line.split()[-1][1:-2]
            if "var m3u8_host1" in line:
                self.m3u8_info["head1"] = line.split()[-1][1:-2]
            if "var m3u8_host2" in line:
                self.m3u8_info["head2"] = line.split()[-1][1:-2]
        if self.m3u8_info["end"].endswith(".m3u8"):
            m3u8_req = requests.get(
                url=self.m3u8_info[self.road] + self.m3u8_info["end"],
                headers=self.headers,
                timeout=self.req_timeout,
                proxies={"http": self.proxies, "https": self.proxies}
            )
            m3u8_req.encoding = "utf-8"
            self.m3u8_tss_names = [line.strip() for line in m3u8_req.text.split() if not line.startswith("#")]
            self.m3u8_tss_urls = [self.merge_m3u8_url(line.strip()) for line in self.m3u8_tss_names]
        elif self.m3u8_info["end"].endswith(".mp4"):
            self.video_url = self.m3u8_info[self.road] + self.m3u8_info["end"]
        else:
            raise Exception("Unsupported url!")

    def get_m3u8_script(self):
        script_first = self.bs.head.script.get_text()
        if "var video" not in script_first:
            raise Exception("Unsupported url!")
        return script_first.split("\n")

    def get_title(self):
        return self.bs.find("span", {"class": "cat_pos_l"}).find_all("a")[-1].get_text()

    def merge_m3u8_url(self, file_name):
        return self.m3u8_info[self.road] + self.m3u8_info["end"].rsplit("/", 1)[0] + "/" + file_name

    def merge_ts(self):
        workdir_bak = os.getcwd()
        os.chdir(self.temp_dir)
        if len(self.m3u8_tss_names) > 100:
            # 列表分割
            names_split = [self.m3u8_tss_names[i:100+i]
                           for i in range(0, len(self.m3u8_tss_names), 100)]
            files_split = []
            i = 0
            for names in names_split:
                files_split.append("tmp.%s" % i)
                self.merge_files(names, files_split[-1])
                i += 1
            self.merge_files(files_split, self.dst_filename)
        else:
            self.merge_files(self.m3u8_tss_names, self.dst_filename)
        os.chdir(workdir_bak)

    @staticmethod
    def adj_file_name(file_name):
        # 调整文件名 过滤不规范的字符
        for char in (" ", "?", "/", "\\", ":", "*", "\"", "<", ">", "|"):
            file_name = file_name.replace(char, "")
        return file_name.strip()

    @staticmethod
    def merge_files(files, dst):
        # 合并文件
        if os.name == "nt":
            cmd_str = "copy /b %s %s >nul" % ("+".join(files), dst)
        else:
            cmd_str = "cat %s > %s" % (" ".join(files), dst)
        os.system(cmd_str)

def select_bs4_parser():
    # 选择 BS4 解析器(优先使用lxml)
    try:
        import lxml
        del lxml
        return "lxml"
    except ModuleNotFoundError:
        try:
            import html5lib
            del html5lib
            return "html5lib"
        except ModuleNotFoundError:
            return

def dload_file_all(max_threads_num, temp_dir, proxies, urls):

    def dload_file(url):
        file_name = url.split("/")[-1]
        try:
            r = requests.get(url, timeout=15, proxies={"http": proxies, "https": proxies})
        except:
            try:
                r = requests.get(url, timeout=15, proxies={"http": proxies, "https": proxies})
            except:
                return False, file_name, "timeout"
        if r.ok:
            dload_file = os.path.join(temp_dir, file_name)
            with open(dload_file, 'wb') as f:
                f.write(r.content)
            return True, file_name, r.status_code
        return False, file_name, r.status_code

    dl_done_num = 0
    # 神奇的多线程下载
    with ThreadPoolExecutor(max_threads_num) as executor1:
        for result in executor1.map(dload_file, urls):
            if result[0]:
                dl_done_num += 1
                sys.stderr.write("Progress: [ %s%% %s/%s ]\r"
                                 % (dl_done_num * 100 // len(urls), dl_done_num, len(urls)))
            else:
                cleanup()
                raise Exception("Failed to download %s! Status: %s\n"
                                % (result[1], result[2]))
    clean_line()

def clean_line():
    # 清行
    exec("sys.stderr.write(\'%%-%ss\\r\' %% \" \")"
         % os.get_terminal_size().columns)

def mkdir(path):
    # 创建目录
    if os.path.exists(path):
        if not os.path.isdir(path):
            try:
                os.remove(path)
            except:
                pass
        else:
            return
    os.makedirs(path)

def file2file(src, dst, move=False):
    # 复制文件到文件
    # move为True时移动文件而不是复制文件
    mkdir(os.path.split(dst)[0])
    if move:
        shutil.move(src, dst)
    else:
        shutil.copyfile(src, dst)
    return dst

def file2dir(src, dst, move=False):
    # 复制文件到目录(不修改文件名)
    # move为True时复制后删除原文件
    mkdir(dst)
    shutil.copy(src, dst)
    if move:
        os.remove(src)
    return os.path.join(dst, os.path.split(src)[1])

def remove_path(path):
    # 移除文件/目录(如果存在的话)
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)

def cleanup():
    # 清理临时目录&文件
    for f in os.listdir(tempfile.gettempdir()):
        if f.startswith("mmav_"):
            remove_path(os.path.join(tempfile.gettempdir(), f))

def main():
    parser = ArgumentParser()
    parser.add_argument("url", help="url for webview")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="number of recipes (jobs)(available: 1~32)(default: 8)")
    parser.add_argument("-r", "--road", type=int, default=2, help="request road(available: 1~3)(default: 2)")
    parser.add_argument("-p", "--proxies", default="", help="use proxy (address:port)(default: None)")

    args = parser.parse_args()

    MaomiAV(args.url, args.jobs, args.road, args.proxies).run()

if __name__ == '__main__':
    main()
