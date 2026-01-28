from typing import Literal
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading
import time
import pprint
import os

__all__ = ['SubmissionRequest', 'APIError', 'Client', 'client']

class SubmissionRequest:
    def __init__(self, problem_id: int, type: Literal['normal', 'hack'] = 'normal'):
        self.problem_id = problem_id
        self.data = {
            'type': type,
        }
        self.files = {}

    def addSourceCodeText(self, name, text, language):
        self.files.update({
            f"sub_{name}_text": (None, text),
            f"sub_{name}_language": (None, language)
        })

    def addSourceCodeFile(self, name, file_path, language):
        self.files.update({
            f"sub_{name}_file": (file_path, open(file_path, "rb")),
            f"sub_{name}_language": (None, language)
        })

    def addHackInputText(self, text, language='plain:direct'):
        self.addSourceCodeText("hack_input", text, language)

    def addHackInputFile(self, file_path, language='plain:direct'):
        self.addSourceCodeFile("hack_input", file_path, language)
    
    def flagFormatInputFile(self):
        self.data['format_input_file'] = True


class APIError(Exception):
    def __init__(self, response):
        self.response = response
    
    def __str__(self):
        s = f"Status Code: {self.response.status_code}\n"
        s += f"Method: {self.response.request.method}\n"
        s += f"History: {[h.status_code for h in self.response.history]}\n"
        s += f"Content-Length header: {self.response.headers.get('Content-Length')}\n"
        s += f"Content-Encoding: {self.response.headers.get('Content-Encoding')}\n"
        s += f"Content-Type: {self.response.headers.get('Content-Type')}\n"
        try:
            res = self.response.json()
            s += f"Error: {res['error']}"
        except:
            s += f"Response: {self.response.text}"
        return s


class Client:
    DEFAULT_URL = "https://uoj.ac"
    SEM = threading.Semaphore(8)
    
    def __init__(self, url=None, api_key=None):
        self.url = url if url is not None else self.DEFAULT_URL
        if api_key is None:
            api_key = os.getenv("UOJ_API_KEY")
        assert api_key is not None, "API key is required"
        self.api_key = api_key
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 502, 503, 504], allowed_methods=["GET", "POST"])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.default_timeout = 60
    
    def getHeaders(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
        }
    
    def _request(self, method: str, url: str, **kwargs):
        timeout = kwargs.pop("timeout", self.default_timeout)
        # print(f"[HTTP] {method} {url} timeout={timeout}")
        try:
            with self.SEM:
                return self.session.request(method=method, url=url, headers=self.getHeaders(), timeout=timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            # print(f"[HTTP ERROR] {method} {url} -> {type(e).__name__}: {e}")
            raise
    
    def makeBackgroundSubmission(self, sub: SubmissionRequest, block: bool = True):
        url = f"{self.url}/api/problems/{sub.problem_id}/background-submissions"
        response = self._request("POST", url, data=sub.data, files=sub.files)

        try:
            res = response.json()
            if 'id' not in res:
                raise APIError(response)
            submission_id = res['id']
            
            if not block:
                return submission_id
            
            # print(f"Background submission created: {submission_id}")
            
            status_url = f"{self.url}/api/background-submissions/{submission_id}"
        except:
            raise APIError(response)

        while True:
            status_response = self._request("GET", status_url)
            try:
                info = status_response.json()
                result = info['result']
                status = result['status']
                if status == 'Judged':
                    return info
                # elif status == 'Waiting':
                #     print('Waiting...')
                # else:
                #     status_details = result['status_details'].strip() or '<no further details>'
                #     print(f"Judging: {status_details}")
            except:
                raise APIError(status_response)
            time.sleep(0.5)
    
    def getProblem(self, problem_id: int):
        url = f"{self.url}/api/problems/{problem_id}"
        response = self._request("GET", url)
        try:
            return response.json()
        except:
            raise APIError(response)
    
    def getProblemACers(self, problem_id: int):
        url = f"{self.url}/api/problems/{problem_id}/acers"
        response = self._request("GET", url)
        try:
            return response.json()
        except:
            raise APIError(response)
    
    def getSubmissions(self, problem_id: int, username: str = None):
        url = f"{self.url}/api/problems/{problem_id}/submissions"
        if username is not None:
            url += f"/user/{username}"
        response = self._request("GET", url)
        try:
            return response.json()
        except:
            raise APIError(response)
    
    def getSubmission(self, submission_id: int):
        url = f"{self.url}/api/submissions/{submission_id}"
        response = self._request("GET", url)
        try:
            return response.json()
        except:
            raise APIError(response)

    def getBackGroundSubmission(self, submission_id: int):
        url = f"{self.url}/api/background-submissions/{submission_id}"
        response = self._request("GET", url)
        try:
            return response.json()
        except:
            raise APIError(response)

    def getContestResult(self, contest_id: int):
        url = f"{self.url}/api/contests/{contest_id}/result"
        response = requests.get(url, headers=self.getHeaders())
        try:
            return response.json()
        except:
            raise APIError(response)


# set your API key here or set UOJ_API_KEY in environment variables
client = Client(api_key=None)


CODE1 = """#include <cstdio>
using namespace std;
inline unsigned read() {
    char c = getchar();
    unsigned res = 0;
    while (c<'0'||c>'9')c = getchar();
    while(c>='0'&&c<='9'){
        res = res*10+(c^'0');
        c = getchar();
    }
    return res;
}
unsigned a, b;
int main() {
    a = read();
    b = read();
    printf("%u", a+b);
    return 0;
}"""

CODE2 = """#include <iostream>
using namespace std;

int main()
{
    int a, b;
    cin >> a >> b;
    if (a ==77358889) {
        while (true);
        return 0;
    }
    cout << a + b << endl;
    return 0;
}
"""

def example1():
    sub = SubmissionRequest(problem_id=1, type='normal')
    sub.addSourceCodeText("answer", CODE1, language="C++20")

    pprint.pp(client.makeBackgroundSubmission(sub))

def example2():
    sub = SubmissionRequest(problem_id=1, type='hack')
    sub.addSourceCodeText("answer", CODE2, language="C++20")
    sub.addHackInputText("77358889 324325325\n")

    pprint.pp(client.makeBackgroundSubmission(sub))

def example3():
    pprint.pp(client.getProblem(1))

def example4():
    pprint.pp(client.getSubmissions(1, username="vfleaking"))

def example5():
    pprint.pp(client.getSubmission(486))

def example6():
    pprint.pp(client.getProblemACers(2))

def example7():
    sub = SubmissionRequest(problem_id=1, type='hack')
    sub.addSourceCodeText("answer", CODE2, language="C++20")
    sub.addHackInputText("print(77358889, 324325325, ' ' * 1000)", language="Python3")
    sub.flagFormatInputFile() # auto-remove extra spaces in the input file

    pprint.pp(client.makeBackgroundSubmission(sub))

def example8():
    pprint.pp(client.getContestResult(6))

if __name__ == '__main__':
    example8()
