import json
import time
import re
import requests
from sys import exit as sys_exit
from os import getenv
from urllib3.exceptions import InsecureRequestWarning
from urllib.parse import quote
from urllib3 import disable_warnings

SERVICE_URL = "https://my.fudan.edu.cn/list/bks_xx_cj"
FETCH_DATA_URL = "https://my.fudan.edu.cn/data_tables/bks_xx_cj.json"
PUSH_DATA_URLS = [
    "https://api2.pushdeer.com/message/push?pushkey={TOKEN}&text={RESULT}",
    "http://www.pushplus.plus/send?token={TOKEN}&content={RESULT}&template=txt"
]
FETCH_DATA_START = 0
FETCH_DATA_LENGTH = 10

TOKEN = getenv("TOKEN")
PUSH_CHANNEL = getenv("PUSH_CHANNEL")
UID = getenv("STD_ID")
PSW = getenv("PASSWORD")
SHOW_DATA_IN_TITLE = getenv("SHOW_DATA_IN_TITLE")

class UISAuth:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:76.0) Gecko/20100101 Firefox/76.0"

    url_login = 'https://uis.fudan.edu.cn/authserver/login?service=' + SERVICE_URL

    def __init__(self, uid, password):
        self.session = requests.session()
        self.session.keep_alive = False
        self.session.headers['User-Agent'] = self.UA
        self.uid = uid
        self.psw = password

    def _page_init(self):
        page_login = self.session.get(self.url_login)
        if page_login.status_code == 200:
            return page_login.text
        else:
            self.close()

    def login(self):
        page_login = self._page_init()
        data = {
            "username": self.uid,
            "password": self.psw,
            "service": SERVICE_URL
        }

        result = re.findall(
            '<input type="hidden" name="([a-zA-Z0-9\-_]+)" value="([a-zA-Z0-9\-_]+)"/?>', page_login)

        data.update(result)

        headers = {
            "Host": "uis.fudan.edu.cn",
            "Origin": "https://uis.fudan.edu.cn",
            "Referer": self.url_login,
            "User-Agent": self.UA
        }

        post = self.session.post(
            self.url_login,
            data=data,
            headers=headers,
            allow_redirects=False)

        if post.status_code == 302:
            print("Login successfully\n")
        else:
            print("Login failed\n")
            self.close()

    def logout(self):
        exit_url = 'https://uis.fudan.edu.cn/authserver/logout?service=/authserver/login'
        self.session.get(exit_url).headers.get('Set-Cookie')

    def close(self, exit_code=0):
        self.logout()
        self.session.close()
        sys_exit(exit_code)

def check_env_set():
    if UID is None or PSW is None:
        print("Error: 未设置 UID 或 PSW 环境变量，无法登录教务服务")
        return False
    elif TOKEN is None:
        print("Warning: 未设置 TOKEN 环境变量，无法推送消息")
        return False
    elif PUSH_CHANNEL is None:
        print("Warning: 未设置 PUSH_CHANNEL 环境变量，无法推送消息")
        return False
    elif SHOW_DATA_IN_TITLE is None:
        print("Warning: 未设置 SHOW_DATA_IN_TITLE 环境变量，默认不在标题栏显示成绩")
    return True

def push_data(result):
    if result == "": return
    disable_warnings(InsecureRequestWarning)
    push_channel = int(PUSH_CHANNEL)
    if push_channel >= len(PUSH_DATA_URLS):
        print("Error: 推送通道不存在")
        return
    result = quote(result)
    url = PUSH_DATA_URLS[push_channel].format(TOKEN=TOKEN, RESULT=result)

    res = requests.get(url, verify=False)
    if res.status_code != 200:
        print("Warning: 推送失败，错误代码：", res.status_code)
        print("错误信息：", res.text)
    else:
        print("推送成功")

class JsonParser:
    def __init__(self, data_text):
        self.data = json.loads(data_text)
    
    def get_record_count(self):
        return self.data["recordsTotal"] if "recordsTotal" in self.data else 0
    
    def get_transcript(self):
        return self.data["data"] if "data" in self.data else []
    
    def compare_transcript_with(self, old):
        old_list = old.get_transcript()
        new_list = self.get_transcript()
        return [x for x in new_list if x not in old_list]
    
    def generate_title(self, courses_list, warning=False, show_data_in_title=False):
        if warning:
            return "Warning: 出现错误，请登录教务服务查看最新成绩！"
        if len(courses_list) == 0:
            return ""
        if show_data_in_title:
            return f"{courses_list[0][3]} {courses_list[0][5]}"
        else:
            return "你收到了新成绩，点击查看详情。"
        
    def generate_content(self, courses_list, warning=False):
        COLUMNS = ['课程代码', '学年度', '学期', '课程名称', '学分', '成绩']
        TURN_ON = [3, 5, 4, 0]
        content = ""
        for course in courses_list:
            for i in TURN_ON:
                content += f"{COLUMNS[i]}: {course[i]}\n"
            content += "-----\n"
        return content
    
    def pretty_print(self, courses_list, warning=False):
        show_data_in_title = (SHOW_DATA_IN_TITLE is not None and SHOW_DATA_IN_TITLE == 'TRUE')
        title = self.generate_title(courses_list, warning, show_data_in_title)
        content = self.generate_content(courses_list, warning)
        return f"{title}\n-----\n{content}"

    def get_new_courses_based_on(self, old):
        delta = self.get_record_count() - old.get_record_count()
        if delta == 0: return ""
        new_courses = self.compare_transcript_with(old)
        return self.pretty_print(new_courses, delta != len(new_courses))
    
    def store(self, path):
        with open(path, 'w') as f:
            json.dump(self.data, f)


class GradeChecker(UISAuth):
    def get_new_course(self):
        res = self.session.get(SERVICE_URL)
        res = self.session.post(FETCH_DATA_URL, 
                                data={"start": str(FETCH_DATA_START), "length": str(FETCH_DATA_LENGTH)})
        new_data = JsonParser(res.text)
        prev_data = None
        with open('record.json', 'r') as f:
            prev_data = JsonParser(f.read())
            time.sleep(0.1)

        new_data.store('record.json')
        return new_data.get_new_courses_based_on(prev_data)


if __name__ == '__main__':
    disable_warnings(InsecureRequestWarning)
    requests.adapters.DEFAULT_RETRIES = 5
    if not check_env_set():
        sys_exit(1)
    grade_checker = GradeChecker(UID, PSW)
    grade_checker.login()
    result = grade_checker.get_new_course()
    print(result == "" and "没有新成绩" or result)
    push_data(result)
