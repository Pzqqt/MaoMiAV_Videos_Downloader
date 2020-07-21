#!/usr/bin/env python3
# encoding: utf-8

import os
import re
import sys
import time
from argparse import ArgumentParser

import requests
from bs4 import BeautifulSoup

from m3u8_downloader import M3u8Downloader, tempfile, mkdir

class MaomiAV:

    def __init__(self, url, jobs, road, proxies):
        self.url = url
        if "play-" not in self.url:
            self.url = "%s/play-%s" % tuple(self.url.rsplit("/", 1))
        self.jobs = jobs
        self.road = self.set_road(road)
        self.proxies = proxies

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
        bs_obj = self.get_bs()
        m3u8_script = self.get_m3u8_script(bs_obj)
        m3u8_info = self.parse_m3u8_script(m3u8_script)
        time_str = time.strftime("%Y%m%d", time.localtime())
        output_file = "%s.mp4" % time_str
        filename_index = 1
        while os.path.exists(output_file):
            output_file = "%s_%s.mp4" % (time_str, filename_index)
            filename_index += 1
        M3u8Downloader(
            m3u8_info[self.road] + m3u8_info["end"],
            self.jobs,
            self.proxies,
            output_file
        ).run()
        print("\nOutput file:", output_file)

    def get_bs(self):
        req = requests.get(
            url=self.url,
            headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Apple"
                               "WebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3"
                               "770.142 Safari/537.36")
            },
            timeout=10,
            proxies={"http": self.proxies, "https": self.proxies}
        )
        req.encoding = "utf-8"
        return BeautifulSoup(req.text, select_bs4_parser())

    @staticmethod
    def get_m3u8_script(bs_obj):
        script_first = bs_obj.head.script.get_text()
        if not script_first:
            script_first = bs_obj.head.script.next_element
        return script_first

    def parse_m3u8_script(self, m3u8_script):
        m3u8_info = {}
        re_pattern = (
            r'var video[\s]*=[\s]*[\'\"](.*?)[\'\"];[\s]*'
            r'var m3u8_host[\s]*=[\s]*[\'\"](.*?)[\'\"];[\s]*'
            r'var m3u8_host1[\s]*=[\s]*[\'\"](.*?)[\'\"];[\s]*'
            r'var m3u8_host2[\s]*=[\s]*[\'\"](.*?)[\'\"];'
        )
        re_result = re.search(re_pattern, m3u8_script)
        m3u8_info["end"] = re_result.group(1)
        m3u8_info["head"] = re_result.group(2)
        m3u8_info["head1"] = re_result.group(3)
        m3u8_info["head2"] = re_result.group(4)
        if not m3u8_info.get(self.road):
            # 如果所选线路不可用 则强制使用线路1
            self.road = "head"
        if m3u8_info["end"].endswith(".m3u8"):
            return m3u8_info
        raise Exception("Unsupported url!")


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
            print("\nFailed to run this program!")
            print("\nPlease install at least one parser in \"lxml\" and \"html5lib\"!")
            sys.exit(1)

def main():
    parser = ArgumentParser()
    parser.add_argument("url", help="url for web page")
    parser.add_argument(
        "-j", "--jobs", type=int, default=8,
        help="number of recipes (jobs)(available: 1~32)(default: 8)"
    )
    parser.add_argument(
        "-r", "--road", type=int, default=2,
        help="request road(available: 1~3)(default: 2)"
    )
    parser.add_argument(
        "-d", "--tmpdir",
        help="Custom temp dir(default: read from environment variables)"
    )
    parser.add_argument(
        "-p", "--proxies", default="",
        help="use proxy (address:port)(default: None)"
    )

    args = parser.parse_args()

    tempfile.tempdir = args.tmpdir
    mkdir(tempfile.gettempdir())

    MaomiAV(args.url, args.jobs, args.road, args.proxies).run()

if __name__ == '__main__':
    main()
