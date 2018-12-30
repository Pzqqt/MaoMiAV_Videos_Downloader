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
            print("\nPlease install at least one parser "
                  "in \"lxml\" and \"html5lib\"!")
            sys.exit()

    def set_jobs(self, jobs):
        if jobs <= 1:
            return 1
        if jobs >= 32:
            return 32
        jobs_list = [2**x for x in range(6)]
        for x in range(5):
            if jobs_list[x] <= jobs < jobs_list[x+1]:
                return jobs_list[x]

    def set_road(self, road):
        if road == 1:
            return "head"
        if road == 2:
            return "head1"
        if road == 3:
            return "head2"
        return "head1"

    def run(self):
        self.get_bs()
        self.get_m3u8()
        self.temp_dir = tempfile.mkdtemp(prefix="mmav_")
        dload_file_all(self.jobs, self.temp_dir, self.proxies, self.m3u8_tss_urls)
        self.merge_ts()
        remove_path(self.temp_dir)
        print("\nDone!")

    def get_m3u8(self):
        m3u8_script = self.bs.find("head").find("script").get_text().split("\n")
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
        m3u8_req = requests.get(
            url=self.m3u8_info[self.road] + self.m3u8_info["end"],
            headers=self.headers,
            timeout=self.req_timeout,
            proxies={"http": self.proxies, "https": self.proxies}
        )
        m3u8_req.encoding = "utf-8"
        self.m3u8_tss_names = [line.strip() for line in m3u8_req.text.split() if not line.startswith("#")]
        self.m3u8_tss_urls = [self.merge_m3u8_url(line.strip()) for line in self.m3u8_tss_names]

    def merge_m3u8_url(self, file_name):
        return self.m3u8_info[self.road] + self.m3u8_info["end"].rsplit("/", 1)[0] + "/" + file_name

    def merge_ts(self):
        dst_filename = adj_dir_name(self.bs.find("title").get_text()) + ".mp4"
        print("File name: " + dst_filename)
        print("\nMerge files...")
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
                merge_files(names, files_split[-1])
                i += 1
            merge_files(files_split, dst_filename)
        else:
            merge_files(self.m3u8_tss_names, dst_filename)
        file2dir(os.path.join(self.temp_dir, dst_filename), workdir_bak)
        os.chdir(workdir_bak)

    def get_bs(self):
        # 使用浏览器 UA 来请求页面
        req = requests.get(url=self.url,
                           headers=self.headers,
                           timeout=self.req_timeout,
                           proxies={"http": self.proxies, "https": self.proxies})
        req.encoding = "utf-8"
        self.bs = BeautifulSoup(req.text, self.bs4_parser)

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

    def dload_file(proxies, url):
        # 下载文件
        file_name = url.split("/")[-1]
        try:
            r = requests.get(url, timeout=15,
                             proxies={"http": proxies, "https": proxies})
        except:
            try:
                r = requests.get(url, timeout=15,
                                 proxies={"http": proxies, "https": proxies})
            except:
                return "", file_name, "timeout"
        if r.ok:
            return r.content, file_name, r.status_code
        return "", file_name, r.status_code

    dl_done_num = 0
    # 神奇的多线程下载
    with ThreadPoolExecutor(max_threads_num) as executor1:
        for req in executor1.map(dload_file, [proxies] * len(urls), urls):
            fcontent, file_name, status_code = req
            if fcontent:
                dload_file = os.path.join(temp_dir, file_name)
                with open(dload_file, 'wb') as f:
                    f.write(fcontent)
                dl_done_num += 1
                sys.stderr.write("Progress: [%s / %s] (%s%%)\r"
                                 % (dl_done_num, len(urls),
                                    dl_done_num * 100 // len(urls)))
            else:
                raise Exception("\nFailed to download %s! Status: %s\n"
                                % (file_name, status_code))
        clean_line()

def merge_files(files, dst):
    # 合并文件
    if os.name == "nt":
        cmd_str = "copy /b %s %s >nul" % ("+".join(files), dst)
    else:
        cmd_str = "cat %s > %s" % (" ".join(files), dst)
    os.system(cmd_str)

def clean_line():
    # 清行
    exec("sys.stderr.write(\'%%-%ss\\r\' %% \" \")"
         % os.get_terminal_size().columns)

def adj_dir_name(dir_name):
    for char in (" ", "?", "/", "\\", ":", "*", "\"", "<", ">", "|"):
        dir_name = dir_name.replace(char, "")
    return dir_name.strip()

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

def main():
    parser = ArgumentParser()
    parser.add_argument("url", help="url for webview")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="number of recipes (jobs)(available: 1~32)(default: 4)")
    parser.add_argument("-r", "--road", type=int, default=2, help="request road(available: 1~3)(default: 2)")
    parser.add_argument("-p", "--proxies", default="", help="use proxy (address:port)(default: None)")

    args = parser.parse_args()

    a = MaomiAV(args.url, args.jobs, args.road, args.proxies)
    a.run()

if __name__ == '__main__':
    main()
