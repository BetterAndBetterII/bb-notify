import os
import pickle
import smtplib
import sqlite3
import traceback
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
import requests
import urllib3.contrib.pyopenssl
from lxml import etree
from requests import Session
from tqdm import tqdm
from typing import cast

"""
This is an auto script for CUHKSZ Blackboard.
"""

"""
login.py below
"""


class ValidationError(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message


class Login:
    _session: Session
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/79.0.3945.88 Safari/537.36",
        "Connection": "close",
    }

    def __init__(self, username, password):
        self._session = self.login(username, password)

    def get_session(self) -> Session:
        return self._session

    def login(self, username, password) -> Session:
        pass

    def get(self, url, **kwargs):
        return self._session.get(url, headers=self.headers, **kwargs)

    def post(self, url, **kwargs):
        return self._session.post(url, headers=self.headers, **kwargs)


class BBLogin(Login):
    def login(self, username, password) -> Session:
        urllib3.contrib.pyopenssl.inject_into_urllib3()
        _session = requests.Session()

        def stage1(_session: Session):
            response_type = "code"
            client_id = "4b71b947-7b0d-4611-b47e-0ec37aabfd5e"
            redirect_uri = "https://bb.cuhk.edu.cn/webapps/bb-SSOIntegrationOAuth2-BBLEARN/authValidate/getCode"
            client_request_id = "b956ea95-440d-4aa8-88c0-0040020000bb"
            params = {
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "client-request-id": client_request_id,
            }
            data = {
                "UserName": "cuhksz\\" + username,
                "Password": password,
                "Kmsi": "true",
                "AuthMethod": "FormsAuthentication",
            }
            url = "https://sts.cuhk.edu.cn/adfs/oauth2/authorize"
            r = _session.post(
                url,
                headers=self.headers,
                params=params,
                data=data,
                allow_redirects=True,
            )
            # print(r.url)
            if not ("bb.cuhk.edu.cn:443" in r.url):
                raise ValidationError("Username or password incorrect!")

        stage1(_session)
        print("Login successfully!")
        return _session


"""
database.py below
"""


class Database:
    def __init__(self, db_name):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.initialize_database()

    def initialize_database(self):
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS events
                               (id TEXT, obj BLOB, id_str TEXT, event_type TEXT,
                               PRIMARY KEY (id_str, event_type))"""
        )
        self.conn.commit()

    def add_event(self, _event):
        obj_data = pickle.dumps(_event)
        self.cursor.execute(
            "INSERT OR REPLACE INTO events (obj, id_str, event_type) VALUES (?, ?, ?)",
            (obj_data, _event.id, _event.__class__.__name__),
        )
        self.conn.commit()

    def get_event(self, event_type, **kwargs) -> object:
        _all = self.filter_events(event_type, **kwargs)
        if _all:
            return _all[0]
        raise ValueError(f"No {event_type} found with {kwargs}")

    def filter_events(self, event_type, id=None, **kwargs) -> list[object]:
        if id:
            query = "SELECT obj FROM events WHERE event_type = ? AND id_str = ?"
            self.cursor.execute(query, (event_type, id))

        else:
            query = "SELECT obj FROM events WHERE event_type = ?"
            self.cursor.execute(query, (event_type,))
        results = self.cursor.fetchall()
        _all = []
        for obj in results:
            _event = pickle.loads(obj[0])
            if all(
                getattr(_event, key, None) == value for key, value in kwargs.items()
            ):
                _all.append(_event)
        return _all

    def delete_event(self, event_type, id, **kwargs):
        self.cursor.execute(
            "DELETE FROM events WHERE event_type = ? AND id_str = ?",
            (
                event_type,
                id,
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


"""
event.py below
"""


class BaseEvent:
    db = Database("events.db")
    title: str
    id: str
    login: Login

    def __init__(self, title, _id, _login):
        self.title = title
        self.id = _id
        self.login = _login
        self.save()  # 自动保存到数据库

    def save(self):
        self.db.add_event(self)

    @classmethod
    def get(cls, **kwargs):
        return cls.db.get_event(cls.__name__, **kwargs)

    @classmethod
    def filter(cls, **kwargs):
        return cls.db.filter_events(cls.__name__, **kwargs)

    @classmethod
    def all(cls):
        return cls.db.filter_events(cls.__name__)

    @classmethod
    def delete(cls, **kwargs):
        cls.db.delete_event(cls.__name__, **kwargs)

    def delete_self(self):
        self.db.delete_event(self.__class__.__name__, id=self.id)

    def __str__(self):
        pass


class CourseEvent(BaseEvent):
    def __init__(self, course_id, course_name, _login):
        self.root_content_list = []
        super().__init__(title=course_name, _id=course_id, _login=_login)

    def add_content_list(self, content_list):
        if content_list.__class__.__name__ == "ContentListEvent":
            content_list = [content_list]
        elif content_list.__class__.__name__ == "list":
            pass
        else:
            raise ValueError("content_list should be ContentListEvent or list")
        for __content_list in content_list:
            if __content_list.id in [
                __content.id for __content in self.root_content_list
            ]:
                continue
            self.root_content_list.append(__content_list)
        self.save()

    def __str__(self):
        return f"{self.title}"


class CalendarEvent(BaseEvent):
    start: datetime
    end: datetime
    location: CourseEvent | str
    sub_title: str
    name: str
    description: str

    def __init__(
        self, start, end, title, location, sub_title, _id, name, description, _login
    ):
        self.start = start
        self.end = end
        self.location = location
        self.sub_title = sub_title
        self.name = name
        self.description = description
        super().__init__(title=title, _id=_id, _login=_login)

    def __str__(self):
        return f"{self.title}"


class ContentEvent(BaseEvent):
    course: CourseEvent
    path: str
    detail: str
    metadata: dict = {}

    def __init__(
        self,
        _course: CourseEvent,
        content_id,
        content_name,
        path,
        detail="",
        metadata=None,
    ):
        if metadata is None:
            metadata = {"detail": detail}
        self.course = _course
        self.path = path
        self.detail = detail
        self.metadata.update(metadata)
        super().__init__(title=content_name, _id=content_id, _login=_course.login)

    def get_detail(self) -> str:
        return self.metadata["detail"] if "detail" in self.metadata else self.detail

    def __str__(self):
        return f"{self.course} {self.title}"


class AnnouncementEvent(BaseEvent):
    course: CourseEvent
    metadata: dict = {}

    def __init__(
        self, _course: CourseEvent, announcement_id, announcement_name, metadata=None
    ):
        if metadata is None:
            metadata = {}
        self.course = _course
        self.metadata = metadata
        super().__init__(
            title=announcement_name, _id=announcement_id, _login=_course.login
        )

    def __str__(self):
        return f"{self.title}"

    def get_detail(self):
        return self.metadata.get("detail", "")


class AssignmentEvent(ContentEvent):
    def __init__(
        self, _course: CourseEvent, assignment_id, assignment_name, path, metadata=None
    ):
        if metadata is None:
            metadata = {}
        super().__init__(
            _course=_course,
            content_id=assignment_id,
            content_name=assignment_name,
            path=path,
            metadata=metadata,
        )
        self._get_detail()
        self.save()

    def _get_detail(self) -> None:
        url = (
            f"https://bb.cuhk.edu.cn/webapps/assignment/uploadAssignment?course_id={self.course.id}"
            f"&content_id={self.id}"
        )
        r = self.login.get(url)
        if "Review Submission" in r.text:
            is_finished = True
        else:
            is_finished = False

        url_new_attempt = (
            f"https://bb.cuhk.edu.cn/webapps/assignment/uploadAssignment?action=newAttempt&"
            f"course_id={self.course.id}&content_id={self.id}"
        )
        r2 = self.login.get(url_new_attempt)
        r2 = etree.HTML(r2.text)
        # Get due date
        # //*[@id="metadata"]/div/div/div[1]/div[2]
        due_date = r2.xpath('//*[@id="metadata"]/div/div/div[1]/div[2]/text()')[
            0
        ].strip()  # Sunday, March 10, 2024
        due_time = r2.xpath('//*[@id="metadata"]/div/div/div[1]/div[2]/span/text()')[
            0
        ].strip()  # 11:59PM
        # parse datetime object beijing time
        # print(f'Due: {due_date} {due_time}')
        try:
            due = datetime.strptime(due_date + " " + due_time, "%A, %B %d, %Y %I:%M %p")
        except ValueError:
            due = datetime.now() + timedelta(days=1)
            print(f"Due date not found for {self.course} {self.title}, set to tomorrow")
            notify_email(
                "warning",
                f"Due date not found for {self.course} {self.title}. Set to tomorrow.",
            )
        # due = datetime.strptime(due_date + " " + due_time, "%A, %B %d, %Y %I:%M %p")
        due = due.astimezone(pytz.timezone("Asia/Shanghai"))
        if datetime.now().astimezone(pytz.timezone("Asia/Shanghai")) > due:
            is_finished = True

        # Get detail
        _li = r2.xpath('//*[@id="instructions"]')[0]
        # parse all text in li
        detail = _li.xpath("string(.)").strip()

        metadata = {"is_finished": is_finished, "due": due, "detail": detail}
        self.metadata = metadata

    def get_due(self) -> datetime:
        return self.metadata["due"]

    def is_finished(self) -> bool:
        return self.metadata["is_finished"]

    def __str__(self):
        return f"{self.course} {self.title}"


class ContentListEvent(ContentEvent):
    contents: list[ContentEvent]
    contents_num: int

    def __init__(self, _course: CourseEvent, content_id, content_name, path):
        self.contents_num = 0
        self.contents = []
        super().__init__(
            _course=_course, content_id=content_id, content_name=content_name, path=path
        )
        self.course.add_content_list(self)

    def add_content(self, content: ContentEvent):
        self.contents.append(content)
        self.contents_num += 1
        self.save()

    def recursive_get_content_data(self):
        url = (
            f"https://bb.cuhk.edu.cn/webapps/blackboard/content/listContent.jsp?course_id={self.course.id}"
            f"&content_id={self.id}&mode=reset"
        )
        r = self.login.get(url=url)
        _html = etree.HTML(r.text)
        # //*[@id="content_listContainer"]
        if len(_html.xpath('//*[@id="content_listContainer"]')) <= 0:
            return
        for _li in _html.xpath('//*[@id="content_listContainer"]')[0]:
            # li's id is "contentListItem:_435903_1"
            _li_id = _li.xpath("@id")[0]
            _content_id = _li_id.split(":")[1]
            # '//*[@id="contentListItem:_424214_1"]/img'
            _type = _li.xpath("img/@src")[0].split("/")[-1].split("_")[0]
            if _type == "folder":
                # '//*[@id="anonymous_element_8"]/a/span'
                div = _li.xpath("div[1]")
                _title = div[0].xpath("h3/a/span/text()")[0]
                __content = ContentListEvent(
                    self.course, _content_id, _title, self.path + "/" + _title
                )
                self.add_content(__content)
            elif _type == "document":
                div = _li.xpath("div[1]")
                _title = div[0].xpath("h3/span[2]/text()")[0]
                # '//*[@id="contentListItem:_434678_1"]/div[2]/div[2]/div/span'
                try:
                    _detail = _li.xpath("div[2]/div[2]/div/span/text()")[0]
                except IndexError:
                    # raise ValueError(f"Detail not found for {_title}, _li: {etree.tostring(_li)}")
                    _detail = ""
                __content = ContentEvent(
                    self.course, _content_id, _title, self.path + "/" + _title, _detail
                )
                self.add_content(__content)
            elif _type == "assignment":
                div = _li.xpath("div[1]")
                _title = div[0].xpath("h3/a/span/text()")[0]
                __content = AssignmentEvent(
                    self.course, _content_id, _title, self.path + "/" + _title
                )
                self.add_content(__content)
            elif _type == "file":
                # //*[@id="anonymous_element_8"]/a/span
                div = _li.xpath("div[1]")
                _title = div[0].xpath("h3/a/span/text()")[0]
                __content = FileEvent(
                    self.course, _content_id, _title, self.path + "/" + _title
                )
                self.add_content(__content)
            elif _type == "image":
                div = _li.xpath("div[1]")
                _title = div[0].xpath("h3/span[2]/text()")[0]
                __content = FileEvent(
                    self.course, _content_id, _title, self.path + "/" + _title
                )
                self.add_content(__content)
            elif _type == "panopto":
                div = _li.xpath("div[1]")
                _title = (
                    div[0].xpath("h3/a/span/text()")[0]
                    if div[0].xpath("h3/a/span/text()")
                    else div[0].xpath("h3/span/text()")[0]
                )
                _detail = "Panopto Video"
                __content = ContentEvent(
                    self.course, _content_id, _title, self.path + "/" + _title, _detail
                )
                self.add_content(__content)
            elif _type == "discussion":
                div = _li.xpath("div[1]")
                _title = div[0].xpath("h3/a/span/text()")[0]
                _detail = "Discussion"
                __content = ContentEvent(
                    self.course, _content_id, _title, self.path + "/" + _title, _detail
                )
                self.add_content(__content)
            else:
                try:
                    div = _li.xpath("div[1]")
                    _title = div[0].xpath("h3/a/span/text()")[0]
                    _detail = _type
                    __content = ContentEvent(
                        self.course,
                        _content_id,
                        _title,
                        self.path + "/" + _title,
                        _detail,
                    )
                    self.add_content(__content)
                except IndexError:
                    div = _li.xpath("div[1]")
                    _title = div[0].xpath("h3/span[2]/text()")[0]
                    _detail = _type
                    __content = ContentEvent(
                        self.course,
                        _content_id,
                        _title,
                        self.path + "/" + _title,
                        _detail,
                    )
                    self.add_content(__content)
                except Exception:
                    raise ValueError(
                        f"Unknown content type: {_type} when "
                        f"parsing Content at {self.course}, path: {self.path}"
                    )

    def get_all_contents(self) -> list[ContentEvent]:
        if self.contents_num == 0:
            self.recursive_get_content_data()

        _all = []
        for child in self.contents:
            if isinstance(child, ContentListEvent):
                _all.extend(child.get_all_contents())
            else:
                _all.append(child)
        self.save()
        return _all

    def __str__(self):
        return f"{self.course} {self.title} Folder"


class FileEvent(ContentEvent):
    def __init__(
        self, _course, content_id, content_name, path, detail="", metadata=None
    ):
        super().__init__(
            _course, content_id, content_name, path, detail=detail, metadata=metadata
        )

    def __str__(self):
        return f"{self.course} {self.title}"


"""
retriever.py below
"""


class BaseRetriever:
    login: Login

    def __init__(self, _login: Login):
        self.login = _login
        __class__.login = _login

    @classmethod
    def init(cls, _login):
        cls.login = _login

    def retrieve(self, query):
        raise NotImplementedError("retrieve method must be implemented")


YEARS = "years"
MONTHS = "months"
WEEKS = "weeks"
DAYS = "days"

CALENDAR = "calendar"
COURSE = "course"
CONTENT = "content"
ANNOUNCEMENT = "announcement"
ASSIGNMENT = "assignment"
DISCUSSION = "discussion"


class CalendarRetriever(BaseRetriever):
    def retrieve(self, query: str) -> list[CalendarEvent]:
        """
        retrieve data from blackboard
        :param query: Default is None. Get all CalendarEvents
        :return: list of data (BaseEvent)
        """
        return self.get_calendar_data(2, YEARS)

    def _parse_calendar_data(self, data) -> list[CalendarEvent]:
        events = []
        for item in data:
            _event = CalendarEvent(
                start=item["start"],
                end=item["end"],
                title=item["calendarName"],
                location=item["calendarNameLocalizable"],
                sub_title=item["title"],
                _id=item["id"],
                name=item["title"],
                description=item["eventType"],
                _login=self.login,
            )
            events.append(_event)
        return events

    def get_calendar_data_period(self, start, end) -> list[CalendarEvent]:
        # timestamp in milliseconds
        params = {"start": start, "end": end, "course_id": "", "mode": "personal"}
        r = self.login.get(
            "https://bb.cuhk.edu.cn/webapps/calendar/calendarData/selectedCalendarEvents",
            params=params,
        )
        data = r.json()
        events = self._parse_calendar_data(data)
        return events

    def get_calendar_data(self, counts=1, _type=MONTHS) -> list[CalendarEvent]:
        import time

        now = int(time.time() * 1000)
        if _type == MONTHS:
            start = now - 1000 * 60 * 60 * 24 * 30 * counts
            end = now + 1000 * 60 * 60 * 24 * 30 * counts
            return self.get_calendar_data_period(start, end)
        elif _type == WEEKS:
            start = now - 1000 * 60 * 60 * 24 * 7 * counts
            end = now + 1000 * 60 * 60 * 24 * 7 * counts
            return self.get_calendar_data_period(start, end)
        elif _type == DAYS:
            start = now - 1000 * 60 * 60 * 24 * counts
            end = now + 1000 * 60 * 60 * 24 * counts
            return self.get_calendar_data_period(start, end)
        elif _type == YEARS:
            start = now - 1000 * 60 * 60 * 24 * 365 * counts
            end = now + 1000 * 60 * 60 * 24 * 365 * counts
            return self.get_calendar_data_period(start, end)
        else:
            raise ValueError("type must be one of 'years', 'months', 'weeks', 'days'")

    def get_ical_link(self) -> str:
        url = "https://bb.cuhk.edu.cn/webapps/calendar/calendarFeed/url"
        return self.login.get(url).text


class CourseRetriever(BaseRetriever):
    login: Login
    course_list: list[CourseEvent] = []

    def retrieve(self, query: str) -> list[CourseEvent]:
        """
        retrieve courses from blackboard
        :param query: Default is None. Get all courses
        :return: list of courses (CourseEvent)
        """
        return self.get_course_list()

    @staticmethod
    def get_course_list() -> list[CourseEvent]:
        if CourseRetriever.course_list:
            return CourseRetriever.course_list
        r = CourseRetriever.login.get(
            "https://bb.cuhk.edu.cn/webapps/portal/execute/tabs/tabAction?tab_tab_group_id"
            "=_1_1"
        )
        data = r.text
        courses = CourseRetriever._parse_course_data(data)
        CourseRetriever.course_list = courses
        return courses

    @staticmethod
    def _parse_course_data(data: str) -> list[CourseEvent]:
        courses = []
        for line in data.split("\n"):
            if "type=Course" in line:
                # <a href=" /webapps/blackboard/execute/launcher?type=Course&id=_10351_1&url="
                # target="_top">CHI1000:Chinese_L13L14L15L16</a>
                course_id = line.split("id=")[1].split("&")[0]
                course_name = line.split(">")[1].split("<")[0]
                __course = CourseEvent(
                    course_id, course_name, _login=CourseRetriever.login
                )
                courses.append(__course)
        return courses

    def get_course_by_title(self, title: str) -> CourseEvent | None:
        courses = self.get_course_list()
        for __course in courses:
            if __course.title == title:
                return __course

        # blur search
        for __course in courses:
            if title in __course.title:
                return __course
        return None


class ContentRetriever(BaseRetriever):
    def retrieve(self, query: str) -> list[ContentEvent]:
        return self.get_content_list()

    @classmethod
    def get_root_content_list_by_course(
        cls, courses: CourseEvent | list[CourseEvent]
    ) -> list[ContentListEvent]:
        if isinstance(courses, CourseEvent):
            courses = [courses]
        root_contents = []
        for __course in tqdm(courses, desc="Retrieving Root Content"):
            if __course.root_content_list:
                root_contents.extend(__course.root_content_list)
                continue
            url = f"https://bb.cuhk.edu.cn/webapps/blackboard/execute/modulepage/view?course_id={__course.id}"
            r = cls.login.get(url=url)
            data = r.text
            # print(data)
            root_contents.extend(cls.parse_content_data(data, __course))

        return root_contents

    @classmethod
    def get_content_list_by_course(
        cls, courses: CourseEvent | list[CourseEvent]
    ) -> list[ContentEvent]:
        root_contents = cls.get_root_content_list_by_course(courses)

        _all = []
        for root_content in tqdm(root_contents, desc="Retrieving Full Content"):
            _all.extend(root_content.get_all_contents())
        return _all

    @classmethod
    def get_content_list(cls) -> list[ContentEvent]:
        courses = CourseRetriever.get_course_list()
        contents = cls.get_content_list_by_course(courses)
        return contents

    @staticmethod
    def parse_content_data(data: str, _course: CourseEvent) -> list[ContentListEvent]:
        root_contents = []
        # etree parse html, li element with href contains "content_id"
        html = etree.HTML(data)
        _li_list = html.xpath("//li")
        if len(_li_list) <= 0:
            return []
        for element in _li_list:
            href = element.xpath("a")
            if len(href) <= 0:
                continue
            href_str = href[0].get("href")
            if href and "content_id" in href_str:
                content_id = href_str.split("content_id=")[1].split("&")[0]
                title = href[0].xpath("span/text()")[0]
                __content = ContentListEvent(
                    _course, content_id, title, path=_course.title + "/" + title
                )
                root_contents.append(__content)

        # print(f'Get {len(root_contents)} Folders in {course.title}!')

        return root_contents


class AssignmentRetriever(BaseRetriever):
    def retrieve(self, query: str) -> list[AssignmentEvent]:
        return self.get_assignment_list()

    @classmethod
    def get_assignment_list_by_course(
        cls, courses: CourseEvent | list[CourseEvent]
    ) -> list[AssignmentEvent]:
        _all_contents = ContentRetriever(cls.login).get_content_list_by_course(courses)
        _all_assignments = []
        for __content in tqdm(_all_contents, desc="Retrieving Assignments"):
            if isinstance(__content, AssignmentEvent):
                _all_assignments.append(__content)
        return _all_assignments

    @classmethod
    def get_assignment_list(cls) -> list[AssignmentEvent]:
        return cls.get_assignment_list_by_course(CourseRetriever.get_course_list())


class AnnouncementRetriever(BaseRetriever):
    def retrieve(self, query: str) -> list[AnnouncementEvent]:
        return self.get_announcement_list()

    @classmethod
    def get_announcement_list_by_course(
        cls, courses: CourseEvent | list[CourseEvent]
    ) -> list[AnnouncementEvent]:
        if isinstance(courses, CourseEvent):
            courses = [courses]
        _all_announcements = []
        for __course in courses:
            url = (
                f"https://bb.cuhk.edu.cn/webapps/blackboard/execute/announcement?"
                f"method=search&context=mybb&course_id={__course.id}&viewChoice=2"
            )
            r = AnnouncementRetriever.login.get(url=url)
            data = r.text
            # print(data)
            _all_announcements.extend(cls._parse_announcement_data(data, __course))
        return _all_announcements

    @classmethod
    def get_announcement_list(cls) -> list[AnnouncementEvent]:
        courses = CourseRetriever.get_course_list()
        announcements = []
        for __course in tqdm(courses, "Retrieving Announcements"):
            announcements += AnnouncementRetriever.get_announcement_list_by_course(
                __course
            )
        return announcements

    @classmethod
    def _parse_announcement_data(
        cls, data: str, _course: CourseEvent
    ) -> list[AnnouncementEvent]:
        announcements = []
        # etree parse html, li element with href contains "content_id"
        html = etree.HTML(data)
        ul_list = html.xpath('//*[@id="announcementList"]')
        if len(ul_list) <= 0:
            return []
        for element in ul_list[0].xpath("//li"):
            _id = element.xpath("@id")
            if _id and _id[0].startswith("_"):
                # <a href="/webapps/blackboard/content/listContent.jsp?
                # course_id=_11467_1&content_id=_123237_1&mode=reset"
                # target="_top">Assignment 1</a>
                announcement_id = _id[0]
                title = element.xpath("h3/text()")[0]

                raw_detail = element.xpath("string(.)").strip().split("\n")
                raw_detail = [x.strip() for x in raw_detail if x.strip()]
                detail = "\n".join(raw_detail[1:])

                __announcement = AnnouncementEvent(
                    _course, announcement_id, title, metadata={"detail": detail}
                )
                announcements.append(__announcement)

        return announcements


"""
mail.py below
template:
    new_assignments
    new_announcements
    unfinished_assignments
    new_content
    daily_summary
"""

TEMPLATE = {
    "new_assignments": """
Blackboard: 你有新的作业!  New assignments available.

Course: {course}

Assignment: {title}

DUE DATE: {due_date}

Description: {description}

You can view the assignments at: https://bb.cuhk.edu.cn/webapps/blackboard/content/listContent.jsp?course_id={course_id}&content_id={content_id}&mode=reset

""",
    "new_announcements": """
Blackboard: 你有新的公告!  New announcements available.

Course: {course}

Title: {title}

Description: {description}

You can view the announcements at: https://bb.cuhk.edu.cn/webapps/blackboard/content/listContent.jsp?course_id={course_id}&content_id={content_id}&mode=reset

""",
    "unfinished_assignments": """
Blackboard: 未完成的作业即将截止!  You have unfinished assignments.

Course: {course}

Assignment: {title}

DUE DATE: {due_date}

Description: {description}

You can view the assignments at: https://bb.cuhk.edu.cn/webapps/blackboard/content/listContent.jsp?course_id={course_id}&content_id={content_id}&mode=reset

""",
    "new_content": """
Blackboard: 你有新的内容!  New content available.

Course: {course}

Title: {title}

Description: {description}

You can view the content at: https://bb.cuhk.edu.cn/webapps/blackboard/content/listContent.jsp?course_id={course_id}&content_id={content_id}&mode=reset

""",
    "daily_summary": """
Blackboard: 每日早报!  Daily summary.

又是美好的一天呢！请查收今天的DDL！

DDL Today:

{unfinished_assignments_info}

DDL in 3 days:

{new_assignments_info}

All DDL:

{all_unfinished_assignments_info}

不要忘记提交作业哦！

“生活就像海洋，只有意志坚强的人，才能到达彼岸！”
""",
}

WEEKDAY = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}


def template_to_MIMEText(
    template_name,
    obj: (
        AssignmentEvent | AnnouncementEvent | list[AssignmentEvent | AnnouncementEvent]
    ),
) -> MIMEMultipart:
    """
    Convert template to MIMEText
    :param template_name:
    :param obj:
    :return:
    """
    template = ""
    if template_name in TEMPLATE:
        template = TEMPLATE[template_name]
    if template_name == "new_assignments":
        if not isinstance(obj, AssignmentEvent):
            raise ValueError("obj must be an instance of AssignmentEvent")
        msg = MIMEMultipart()
        if obj.get_due() - pytz.timezone("Asia/Shanghai").localize(
            datetime.now()
        ) < timedelta(days=1):
            due_date_str = (
                obj.get_due().strftime("%m月%d日 %H:%M ")
                + WEEKDAY[obj.get_due().weekday()]
                + "  "
                + str(
                    (
                        obj.get_due()
                        - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                    ).total_seconds()
                    // 3600
                )
                + " 小时后"
            )
        else:
            due_date_str = (
                obj.get_due().strftime("%m月%d日 %H:%M ")
                + WEEKDAY[obj.get_due().weekday()]
                + "  "
                + str(
                    (
                        obj.get_due()
                        - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                    ).days
                )
                + " 天后"
            )
        message = template.format(
            course=obj.course.title,
            title=obj.title,
            due_date=due_date_str,
            description=obj.get_detail(),
            course_id=obj.course.id,
            content_id=obj.id,
        )
        msg["Subject"] = template.split("\n")[1]
        msg.attach(MIMEText(message, "plain"))
        return msg
    elif template_name == "new_announcements":
        if not isinstance(obj, AnnouncementEvent):
            raise ValueError("obj must be an instance of AnnouncementEvent")
        msg = MIMEMultipart()
        message = template.format(
            course=obj.course.title,
            title=obj.title,
            description=obj.get_detail(),
            course_id=obj.course.id,
            content_id=obj.id,
        )
        msg["Subject"] = template.split("\n")[1]
        msg.attach(MIMEText(message, "plain"))
        return msg
    elif template_name == "unfinished_assignments":
        if not isinstance(obj, AssignmentEvent):
            raise ValueError("obj must be an instance of AssignmentEvent")
        msg = MIMEMultipart()
        if obj.get_due() - pytz.timezone("Asia/Shanghai").localize(
            datetime.now()
        ) < timedelta(days=1):
            due_date_str = (
                obj.get_due().strftime("%m月%d日 %H:%M ")
                + WEEKDAY[obj.get_due().weekday()]
                + "  "
                + str(
                    (
                        obj.get_due()
                        - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                    ).total_seconds()
                    // 3600
                )
                + " 小时后"
            )
        else:
            due_date_str = (
                obj.get_due().strftime("%m月%d日 %H:%M ")
                + WEEKDAY[obj.get_due().weekday()]
                + "  "
                + str(
                    (
                        obj.get_due()
                        - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                    ).days
                )
                + " 天后"
            )
        time_left = (
            str(
                (
                    obj.get_due()
                    - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                ).total_seconds()
                // 3600
            )
            + " 小时"
        )
        message = template.format(
            course=obj.course.title,
            title=obj.title,
            due_date=due_date_str,
            description=obj.get_detail(),
            course_id=obj.course.id,
            content_id=obj.id,
            time_left=time_left,
        )
        msg["Subject"] = template.split("\n")[1]
        msg.attach(MIMEText(message, "plain"))
        return msg
    elif template_name == "new_content":
        if not isinstance(obj, ContentEvent):
            raise ValueError("obj must be an instance of ContentEvent")
        msg = MIMEMultipart()
        message = template.format(
            course=obj.course.title,
            title=obj.title,
            description=obj.get_detail(),
            course_id=obj.course.id,
            content_id=obj.id,
        )
        msg["Subject"] = template.split("\n")[1]
        msg.attach(MIMEText(message, "plain"))
        return msg
    elif template_name == "daily_summary":
        if not isinstance(obj, list):
            raise ValueError("obj must be a list")
        msg = MIMEMultipart()
        unfinished_assignments_info = ""
        new_assignments_info = ""
        all_unfinished_assignments_info = ""
        for __obj in obj:
            if not isinstance(__obj, AssignmentEvent):
                raise ValueError("obj must be a list of AssignmentEvent")
        obj.sort(key=lambda __: __.get_due())
        for __obj in obj:
            if __obj.get_due() - pytz.timezone("Asia/Shanghai").localize(
                datetime.now()
            ) < timedelta(days=1):
                due_date_str = (
                    __obj.get_due().strftime("%m月%d日%w %H:%M ")
                    + WEEKDAY[__obj.get_due().weekday()]
                    + "  "
                    + str(
                        (
                            __obj.get_due()
                            - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                        ).total_seconds()
                        // 3600
                    )
                    + " 小时后"
                )
            else:
                due_date_str = (
                    __obj.get_due().strftime("%m月%d日%w %H:%M ")
                    + WEEKDAY[__obj.get_due().weekday()]
                    + "  "
                    + str(
                        (
                            __obj.get_due()
                            - pytz.timezone("Asia/Shanghai").localize(datetime.now())
                        ).days
                    )
                    + " 天后"
                )
            if __obj.is_finished():
                continue
            if __obj.get_due() - pytz.timezone("Asia/Shanghai").localize(
                datetime.now()
            ) < timedelta(days=1):
                unfinished_assignments_info += (
                    f"{__obj.course.title}\n    {__obj.title} - {due_date_str}\n \n"
                )
            elif __obj.get_due() - pytz.timezone("Asia/Shanghai").localize(
                datetime.now()
            ) < timedelta(days=3):
                new_assignments_info += (
                    f"{__obj.course.title}\n    {__obj.title} - {due_date_str}\n \n"
                )
            all_unfinished_assignments_info += (
                f"{__obj.course.title}\n    {__obj.title} - {due_date_str}\n \n"
            )

        if not unfinished_assignments_info:
            unfinished_assignments_info = "No unfinished assignments today."
        if not new_assignments_info:
            new_assignments_info = "No unfinished assignments in 3 days."
        if not all_unfinished_assignments_info:
            all_unfinished_assignments_info = "No unfinished assignments."
        message = template.format(
            unfinished_assignments_info=unfinished_assignments_info,
            new_assignments_info=new_assignments_info,
            all_unfinished_assignments_info=all_unfinished_assignments_info,
        )
        msg["Subject"] = template.split("\n")[1]
        msg.attach(MIMEText(message, "plain"))
        return msg
    elif template_name == "error":
        msg = MIMEMultipart()
        message = str(obj)
        msg["Subject"] = "Runtime Error"
        msg.attach(MIMEText(message, "plain"))
        return msg
    elif template_name == "warning":
        msg = MIMEMultipart()
        message = str(obj)
        msg["Subject"] = "Warning"
        msg.attach(MIMEText(message, "plain"))
        return msg
    else:
        raise ValueError(f"template_name not found: {template_name}")


class NotifyRecord:
    template_name: str
    receiver: str
    send_time: datetime

    def __init__(self, template_name, receiver, send_time: datetime = None):
        self.template_name = template_name
        self.receiver = receiver
        self.send_time = (
            pytz.timezone("Asia/Shanghai").localize(datetime.now())
            if send_time is None
            else send_time
        )

    def save(self):
        """
        Save the record to csv file
        :return:
        """
        with open("notify_record.csv", "a") as f:
            f.write(
                f"{self.template_name},{self.receiver},{str(datetime.timestamp(self.send_time))}\n"
            )

    def __str__(self):
        return f"{self.template_name} - {self.receiver} - {self.send_time.strftime('%Y.%m.%d %H:%M')}"

    @staticmethod
    def all():
        if not os.path.exists("./notify_record.csv"):
            return []
        with open("notify_record.csv", "r") as f:
            data = f.readlines()
        records = []
        for line in data:
            line = line.strip()
            if not line:
                continue
            template_name, receiver, time_stamp = line.split(",")
            send_time = pytz.timezone("Asia/Shanghai").localize(
                datetime.fromtimestamp(float(time_stamp))
            )
            records.append(NotifyRecord(template_name, receiver, send_time))
        return records

    @staticmethod
    def create(template_name, receiver, send_time: datetime = None):
        # 添加通知记录
        record = NotifyRecord(
            template_name=template_name, receiver=receiver, send_time=send_time
        )
        record.save()
        return record


def notify_email(
    template_name,
    obj: (
        AssignmentEvent
        | AnnouncementEvent
        | str
        | list[AssignmentEvent | AnnouncementEvent]
    ),
    receiver=os.getenv("EMAIL_RECEIVER"),
):
    # 发送通知邮件
    smtp_server = os.getenv("EMAIL_SERVER")
    smtp_port = int(os.getenv("EMAIL_PORT"))
    username = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_PASSWORD")
    # 连接到 SMTP 服务器
    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
    except Exception as e:
        raise Exception("无法连接到SMTP服务器", smtp_server, smtp_port, e)

    receivers = receiver.split(",") if "," in receiver else [receiver]
    # 创建邮件对象
    server.connect(smtp_server, 465)
    server.ehlo()
    server.login(username, password)

    msg = template_to_MIMEText(template_name, obj)
    msg["From"] = username
    msg["To"] = receiver
    # 发送邮件
    server.sendmail(username, receivers, msg=msg.as_string())
    print("Email sent successfully!")

    server.quit()
    NotifyRecord.create(template_name, receiver)


def compare_data(
    db_data: list[BaseEvent], current_data: list[BaseEvent]
) -> tuple[list[BaseEvent], list[BaseEvent]]:
    new_data = []
    removed_data = []
    for data in current_data:
        if not (data.id in [db_data.id for db_data in db_data]):
            new_data.append(data)
    for data in db_data:
        if not (data.id in [current_data.id for current_data in current_data]):
            removed_data.append(data)
    return new_data, removed_data


def print_compare_data(
    contents, assignments, announcements, courses, update_or_remove: str
):
    (
        print(f"{len(contents)} {update_or_remove} contents found:")
        if len(contents) > 0
        else None
    )
    for __content in contents:
        print("    " + str(__content))
    (
        print(f"{len(assignments)} {update_or_remove} assignments found:")
        if len(assignments) > 0
        else None
    )
    for __assignment in assignments:
        print("    " + str(__assignment))
    (
        print(f"{len(announcements)} {update_or_remove} announcements found:")
        if len(announcements) > 0
        else None
    )
    for __announcement in announcements:
        print("    " + str(__announcement))
    (
        print(f"{len(courses)} {update_or_remove} courses found:")
        if len(courses) > 0
        else None
    )
    for __course in courses:
        print("    " + str(__course))
    (
        print(f"No {update_or_remove} content found.")
        if len(courses + contents + assignments + announcements) <= 0
        else None
    )


def main():
    disable_email = False
    login = BBLogin(os.getenv("BB_USERNAME"), os.getenv("BB_PASSWORD"))

    # Reading Data from DataBase
    print("Reading Data from DataBase...", end=" ")
    db_all_contents = ContentEvent.all() + FileEvent.all()
    db_all_assignments = AssignmentEvent.all()
    db_all_announcements = AnnouncementEvent.all()
    db_all_courses = CourseEvent.all()
    print("  Done!")
    print(
        f"DataBase has {len(db_all_contents)} contents, {len(db_all_assignments)} assignments, "
        f"{len(db_all_announcements)} announcements, and {len(db_all_courses)} courses."
    )

    if len(db_all_contents) <= 0:
        print("No data in DataBase, retrieving all data from Blackboard...")
        print("Disabling Email Notification...")
        disable_email = True

    # Retrieving Data from Blackboard
    CourseRetriever.init(login)
    ContentRetriever.init(login)
    AssignmentRetriever.init(login)
    AnnouncementRetriever.init(login)
    print("Retrieving Data from Blackboard...", end=" ")
    all_contents = ContentRetriever.get_content_list()
    all_contents = [
        content for content in all_contents if not isinstance(content, AssignmentEvent)
    ]
    print(f"  {len(all_contents)} contents retrieved.")
    all_assignments = AssignmentRetriever.get_assignment_list()
    print(f"  {len(all_assignments)} assignments retrieved.")
    all_announcements = AnnouncementRetriever.get_announcement_list()
    print(f"  {len(all_announcements)} announcements retrieved.")
    all_courses = CourseRetriever.get_course_list()
    print(f"  {len(all_courses)} courses retrieved.")

    # Comparing Data from Blackboard and DataBase
    db_all_contents = cast(list[ContentEvent], db_all_contents)
    db_all_assignments = cast(list[AssignmentEvent], db_all_assignments)
    db_all_announcements = cast(list[AnnouncementEvent], db_all_announcements)
    db_all_courses = cast(list[CourseEvent], db_all_courses)

    new_contents, removed_contents = compare_data(db_all_contents, all_contents)
    new_assignments, removed_assignments = compare_data(
        db_all_assignments, all_assignments
    )
    new_announcements, removed_announcements = compare_data(
        db_all_announcements, all_announcements
    )
    new_courses, removed_courses = compare_data(db_all_courses, all_courses)
    print("  Done!")

    # Printing Data
    print_compare_data(
        new_contents, new_assignments, new_announcements, new_courses, "new"
    )
    print_compare_data(
        removed_contents,
        removed_assignments,
        removed_announcements,
        removed_courses,
        "removed",
    )

    # Deleting Removed Data
    for _content in removed_contents:
        _content.delete_self()
    for _assignment in removed_assignments:
        _assignment.delete_self()
    for _announcement in removed_announcements:
        _announcement.delete_self()
    for _course in removed_courses:
        _course.delete_self()

    if disable_email:
        print("Email Notification Disabled!")
        exit(0)
    # Sending Notification Email
    for content in new_contents:
        # notify_email("new_content", content)
        pass
    for assignment in new_assignments:
        assignment = cast(AssignmentEvent, assignment)
        notify_email("new_assignments", assignment)
    for announcement in new_announcements:
        announcement = cast(AnnouncementEvent, announcement)
        notify_email("new_announcements", announcement)
    for assignment in all_assignments:
        assignment = cast(AssignmentEvent, assignment)
        if (
            assignment.get_due()
            - pytz.timezone("Asia/Shanghai").localize(datetime.now())
        ) <= timedelta(hours=2):
            (
                notify_email("unfinished_assignments", assignment)
                if not assignment.is_finished()
                else None
            )

    # Daily Summary
    all_notify_record = NotifyRecord.all()
    all_notify_record = [
        record
        for record in all_notify_record
        if record.send_time.date()
        == pytz.timezone("Asia/Shanghai").localize(datetime.now()).date()
    ]
    summary_notify_record = [
        record
        for record in all_notify_record
        if record.template_name == "daily_summary"
    ]
    if (
        pytz.timezone("Asia/Shanghai").localize(datetime.now()).hour >= 8
        and summary_notify_record == []
    ):
        assignments = AssignmentEvent.all()
        assignments = [cast(AssignmentEvent, assignment) for assignment in assignments]
        notify_email("daily_summary", assignments)

    print("All Done!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
        print("An error occurred!")
        error_msg = traceback.format_exc()
        notify_email("error", error_msg + "\n\n" + str(e))
        exit(1)
