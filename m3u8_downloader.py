#!/usr/bin/env python3
# encoding: utf-8

import os
import re
import shutil
import tempfile
from time import sleep
from concurrent.futures import ThreadPoolExecutor
from argparse import ArgumentParser

import requests
from Crypto.Cipher import AES

REQ_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36")
}

class M3u8Downloader:

    req_timeout = 15

    def __init__(self, url, jobs, proxies, output):
        self.url = url
        self.jobs = self.set_jobs(jobs)
        self.proxies = proxies
        self.output = self.adj_file_name(output)

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
        return 8

    def run(self):
        urls, key_method, key_content = self.get_m3u8(self.url, self.proxies)
        temp_dir = tempfile.mkdtemp(prefix="m3u8_")
        try:
            print("\nDownload ts files...")
            file_list = download_file_all(
                max_threads_num=self.jobs,
                temp_dir=temp_dir,
                proxies=self.proxies,
                urls=urls,
                key_method=key_method,
                key_content=key_content,
            )
            print("\nMerge files...")
            self.merge_ts(
                temp_dir=temp_dir,
                src_files=file_list,
                dst_file=self.output
            )
            file2dir(os.path.join(temp_dir, self.output), os.getcwd())
        finally:
            remove_path(temp_dir)
        print("\nDone!")

    @classmethod
    def get_m3u8(cls, url, proxies=""):
        base_url = url.rsplit("/", 1)[0]
        req = requests.get(
            url,
            headers=REQ_HEADERS, timeout=10, proxies={"http": proxies, "https": proxies}
        )
        req.raise_for_status()
        req_text = req.text

        if "#EXT-X-STREAM-INF" in req_text:
            return cls.get_m3u8(base_url+"/"+cls.select_m3u8_stream(req_text), proxies)

        if "#EXT-X-KEY" in req_text:
            re_pattern = r'#EXT-X-KEY:METHOD=(.*?),URI="(.*?)"'
            re_result = re.search(re_pattern, req_text)
            key_method = re_result.group(1)
            key_url = re_result.group(2)
            if not key_url.startswith("http"):
                key_url = base_url + "/" + key_url
            key_content = requests.get(
                key_url,
                headers=REQ_HEADERS, timeout=10, proxies={"http": proxies, "https": proxies}
            ).content
        else:
            key_method = None
            key_content = None

        urls = []
        for line in req_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("http"):
                urls.append(line)
            else:
                urls.append(base_url + "/" + line)
        return urls, key_method, key_content

    @staticmethod
    def select_m3u8_stream(m3u8_text):
        stream_info = {}
        stream_list = []
        for line in m3u8_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXT-X-STREAM-INF"):
                stream_info = {"info": line.split(":", 1)[1]}
                continue
            if stream_info:
                stream_info["sub_url"] = line
                stream_list.append(stream_info.copy())
                stream_info = {}
        print("\n- Found %s stream:" % len(stream_list))
        for index, stream_info_ in enumerate(stream_list, 1):
            print("  - %s. %s" % (index, stream_info_["info"]))
        input_str = input("\n- Input the item number you want to download(default: 1):")
        if input_str in [str(x) for x in range(1, len(stream_list)+1)]:
            index = int(input_str) - 1
        else:
            index = 0
        return stream_list[index]["sub_url"]

    @classmethod
    def merge_ts(cls, temp_dir, src_files, dst_file):
        pwd_bak = os.getcwd()
        os.chdir(temp_dir)
        try:
            if len(src_files) > 100:
                # 列表分割
                names_split = [
                    src_files[i:100+i]
                    for i in range(0, len(src_files), 100)
                ]
                files_split = []
                for i, names in enumerate(names_split):
                    files_split.append("tmp_%s.mp4" % i)
                    cls.merge_files(names, files_split[-1])
                cls.merge_files(files_split, dst_file)
            else:
                cls.merge_files(src_files, dst_file)
        finally:
            os.chdir(pwd_bak)

    @staticmethod
    def merge_files(files, dst):
        # 合并文件
        if os.name == "nt":
            cmd_str = "copy /b %s %s >nul" % ("+".join(files), dst)
        else:
            cmd_str = "cat %s > %s" % (" ".join(files), dst)
        os.system(cmd_str)

    @staticmethod
    def adj_file_name(file_name):
        """ 调整文件名 过滤不规范的字符 """
        for char in (" ", "?", "/", "\\", ":", "*", "\"", "<", ">", "|"):
            file_name = file_name.replace(char, "")
        return file_name


def download_file_all(max_threads_num, temp_dir, proxies, urls, key_method, key_content):
    if key_method and key_content:
        cryptor = AES.new(key_content, AES.MODE_CBC, key_content)
    else:
        cryptor = None

    def download_file(url, file_name):
        while True:
            print(" - Request %s..." % file_name)
            try:
                r = requests.get(
                    url,
                    headers=REQ_HEADERS, timeout=15, proxies={"http": proxies, "https": proxies}
                )
            except Exception as error:
                if isinstance(error, requests.exceptions.ReadTimeout):
                    print(" ! Request %s failed, timeout! Try again after 5s.." % file_name)
                elif isinstance(error, (requests.exceptions.SSLError, requests.exceptions.ProxyError)):
                    print(" ! Request %s failed, proxy error! Try again after 5s.." % file_name)
                else:
                    print(" ! %s: %s" % (type(error), error))
                    print(" ! Request %s failed! Try again after 5s.." % file_name)
                sleep(5)
                continue
            if not r.ok:
                print(" ! Request %s %s! Try again after 5s..." % (file_name, r.status_code))
                sleep(5)
                continue
            with open(os.path.join(temp_dir, file_name), "wb") as f:
                if cryptor:
                    f.write(cryptor.decrypt(r.content))
                else:
                    f.write(r.content)
            print(" - Download %s OK!" % file_name)
            return

    file_list = [str(x) + ".ts" for x in range(len(urls))]
    with ThreadPoolExecutor(max_threads_num) as executor1:
        executor1.map(download_file, urls, file_list)
    return file_list

def mkdir(path):
    """ 创建目录 """
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
    """ 复制文件到文件
    move为True时移动文件而不是复制文件
    """
    mkdir(os.path.split(dst)[0])
    if move:
        shutil.move(src, dst)
    else:
        shutil.copyfile(src, dst)
    return dst

def file2dir(src, dst, move=False):
    """ 复制文件到目录(不修改文件名)
    move为True时复制后删除原文件
    """
    mkdir(dst)
    shutil.copy(src, dst)
    if move:
        os.remove(src)
    return os.path.join(dst, os.path.split(src)[1])

def remove_path(path):
    """ 移除文件/目录(如果存在的话) """
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)

def main():
    parser = ArgumentParser()
    parser.add_argument("url", help="url for m3u8 file")
    parser.add_argument(
        "-j", "--jobs", type=int, default=8,
        help="number of recipes (jobs)(available: 1~32)(default: 8)")
    parser.add_argument(
        "-p", "--proxies", default="",
        help="use HTTP proxy (address:port)(default: None)"
    )
    parser.add_argument(
        "-d", "--tmpdir",
        help="Custom temp dir(default: read from environment variables)"
    )
    parser.add_argument(
        "-o", "--output", default="output.mp4",
        help="output file name (default: output.mp4)"
    )

    args = parser.parse_args()

    tempfile.tempdir = args.tmpdir
    mkdir(tempfile.gettempdir())

    M3u8Downloader(args.url, args.jobs, args.proxies, args.output).run()

if __name__ == '__main__':
    main()
