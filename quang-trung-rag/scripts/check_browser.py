"""Check the independent history web app using an existing Chrome DevTools port."""
import argparse
import base64
import json
from pathlib import Path

import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parent.parent
output = ROOT / 'data' / 'screenshots'
output.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('--llm', action='store_true')
args = parser.parse_args()
errors = []
with httpx.Client(trust_env=False) as client:
    address = client.get('http://127.0.0.1:9223/json/version').json()['webSocketDebuggerUrl']

with connect(address, max_size=20_000_000) as ws:
    sequence, session = 0, None

    def call(method, params=None, browser=False):
        global sequence
        sequence += 1
        ident = sequence
        payload = {'id': ident, 'method': method, 'params': params or {}}
        if session and not browser:
            payload['sessionId'] = session
        ws.send(json.dumps(payload))
        while True:
            response = json.loads(ws.recv(timeout=120))
            if response.get('method') == 'Runtime.exceptionThrown':
                errors.append(response['params']['exceptionDetails'])
            if response.get('id') == ident:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                return response.get('result', {})

    def js(expression):
        result = call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result.get('result', {}).get('value')

    def wait_for(expression, timeout=20000):
        js(f'''new Promise((resolve,reject)=>{{const start=Date.now();const id=setInterval(()=>{{if({expression}){{clearInterval(id);resolve(true)}}else if(Date.now()-start>{timeout}){{clearInterval(id);reject(new Error('Timeout: '+{json.dumps(expression)}))}}}},80)}})''')

    def screenshot(name):
        result = call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        (output / name).write_bytes(base64.b64decode(result['data']))

    target = call('Target.createTarget', {'url': 'about:blank'}, browser=True)['targetId']
    session = call('Target.attachToTarget', {'targetId': target, 'flatten': True}, browser=True)['sessionId']
    call('Page.enable'); call('Runtime.enable')
    call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
    call('Page.navigate', {'url': 'http://127.0.0.1:8010/'})
    wait_for('document.querySelector("#stat-records")?.textContent === "20"')
    assert js('document.documentElement.scrollWidth <= innerWidth')
    screenshot('desktop.png')
    js('document.querySelector("#use-llm").checked=false;document.querySelector(".suggestion").click()')
    wait_for('!document.querySelector("#results").hidden && document.querySelectorAll(".source-card").length > 0')
    assert js('document.querySelector("#results").textContent.includes("Ngô Thì Nhậm")')
    js('document.querySelector("#results [data-record]").click()')
    wait_for('document.querySelector("#source-dialog").open')
    assert js('document.querySelector("#source-body a").href.startsWith("https://")')
    js('document.querySelector("#close-source").click();document.querySelector("[data-tab=graph]").click()')
    wait_for('document.querySelectorAll("#full-graph .graph-node").length > 0')
    js('document.querySelector("#entity-select").value="ngo-thi-nham";document.querySelector("#entity-select").dispatchEvent(new Event("change"))')
    wait_for('document.querySelector("#graph-detail").textContent.includes("Đảm trách") || document.querySelector("#graph-detail").textContent.includes("đảm trách")')
    screenshot('graph.png')
    js('document.querySelector("[data-tab=timeline]").click()')
    assert js('document.querySelectorAll(".timeline-item").length === 7')
    assert js('document.querySelector("#timeline-list").textContent.includes("Mồng 3 Tết")')
    screenshot('timeline.png')
    js('document.querySelector("[data-tab=documents]").click()')
    assert js('document.querySelectorAll(".library-source").length===6')
    js('document.querySelector("#document-select").value="chinhphu-2013";document.querySelector("#document-select").dispatchEvent(new Event("change"));document.querySelector("#document-query").value="ha hoi";document.querySelector("#document-query").dispatchEvent(new Event("input"))')
    assert js('document.querySelectorAll(".record-item").length===1')
    if args.llm:
        js('''window.__qaFetch=window.fetch;window.fetch=async (...args)=>{const response=await window.__qaFetch(...args);if(String(args[0]).endsWith('/api/ask'))window.__qaAnswer=await response.clone().json();return response;};
        document.querySelector('[data-tab=search]').click();document.querySelector('#use-llm').checked=true;
        document.querySelector('#question').value='Hà Hồi được hạ vào ngày nào, trước hay sau trận Ngọc Hồi?';document.querySelector('#submit-button').click();''')
        wait_for('window.__qaAnswer && !document.querySelector("#results").hidden', timeout=100000)
        answer = js('window.__qaAnswer')
        assert answer['answer_mode'] == 'generated', answer.get('generation_warning')
        assert '28/01/1789' in answer['answer'] or 'mồng 3' in answer['answer'].lower() or 'mùng 3' in answer['answer'].lower()
        assert 'trước' in answer['answer'].lower() and 'ngọc hồi' in answer['answer'].lower()
        assert 'cùng ngày' not in answer['answer'].lower()
        assert 'Đặng Tiến Đông' not in answer['answer']
        assert js('document.querySelectorAll(".answer-content [data-citation]").length>0')
        (ROOT / 'data' / 'llm-smoke.json').write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding='utf-8')
        js('document.querySelector("#results").scrollIntoView({block:"start"})')
        screenshot('answer.png')
        print(json.dumps({'answer': answer['answer'], 'elapsed_ms': answer['elapsed_ms']}, ensure_ascii=False), flush=True)
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Page.navigate', {'url': 'http://127.0.0.1:8010/'})
    wait_for('document.querySelector("#stat-records")?.textContent === "20"')
    assert js('document.documentElement.scrollWidth <= innerWidth')
    screenshot('mobile.png')
    js('document.querySelector("#menu-button").click()')
    assert js('document.querySelector("#sidebar").classList.contains("open")')
    js('document.querySelector("[data-category=\'dien-bien\']").click()')
    assert js('document.querySelector("#category-select").value === "dien-bien"')
    assert not js('document.querySelector("#sidebar").classList.contains("open")')
    call('Target.closeTarget', {'targetId': target}, browser=True)

report = {'desktop': 'passed', 'mobile': 'passed', 'retrieval': 'passed', 'citations': 'passed', 'graph': 'passed', 'timeline': 'passed', 'library_filter': 'passed', 'category_filter': 'passed', 'javascript_errors': errors}
if args.llm:
    report['ollama_answer'] = 'passed'
(output / 'browser-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
assert not errors, errors
print(json.dumps(report, ensure_ascii=False, indent=2))
