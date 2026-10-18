"""Browser QA against an existing Chrome DevTools port; no browser download."""
import base64
import argparse
import json
from pathlib import Path

import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parent.parent
output = ROOT / 'data' / 'screenshots'
output.mkdir(parents=True, exist_ok=True)
errors = []
parser = argparse.ArgumentParser()
parser.add_argument('--llm', action='store_true', help='Thử thêm câu trả lời Ollama thật trên giao diện.')
args = parser.parse_args()
with httpx.Client(trust_env=False) as client:
    websocket = client.get('http://127.0.0.1:9222/json/version').json()['webSocketDebuggerUrl']

with connect(websocket, max_size=20_000_000) as ws:
    sequence = 0
    session = None

    def call(method, params=None, *, browser=False):
        global sequence
        sequence += 1
        ident = sequence
        payload = {'id': ident, 'method': method, 'params': params or {}}
        if session and not browser:
            payload['sessionId'] = session
        ws.send(json.dumps(payload))
        while True:
            data = json.loads(ws.recv(timeout=45))
            if data.get('method') == 'Runtime.exceptionThrown':
                errors.append(data['params']['exceptionDetails'])
            if data.get('id') == ident:
                if 'error' in data:
                    raise RuntimeError(data['error'])
                return data.get('result', {})

    def js(expression):
        result = call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result.get('result', {}).get('value')

    def wait_for(expression, timeout=20000):
        js(f'''new Promise((resolve,reject)=>{{const start=Date.now();const id=setInterval(()=>{{if({expression}){{clearInterval(id);resolve(true)}}else if(Date.now()-start>{timeout}){{clearInterval(id);reject(new Error('Timeout: '+{json.dumps(expression)}))}}}},80)}})''')

    def screenshot(name):
        data = call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        (output / name).write_bytes(base64.b64decode(data['data']))

    target = call('Target.createTarget', {'url': 'about:blank'}, browser=True)['targetId']
    session = call('Target.attachToTarget', {'targetId': target, 'flatten': True}, browser=True)['sessionId']
    call('Page.enable')
    call('Runtime.enable')
    call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
    call('Page.navigate', {'url': 'http://127.0.0.1:8000/'})
    wait_for('document.querySelector("#stat-pages")?.textContent === "276"')
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Desktop overflow'
    screenshot('desktop.png')
    js('document.querySelector("#use-llm").checked=false; document.querySelector(".suggestion").click()')
    wait_for('!document.querySelector("#results").hidden && document.querySelectorAll(".source-card").length > 0')
    assert js('document.querySelector("#results").textContent.includes("Trang PDF 43")')
    screenshot('results.png')
    js('document.querySelector("#results [data-page]").click()')
    wait_for('document.querySelector("#source-dialog").open')
    assert js('document.querySelector("#source-frame").src.includes("#page=")')
    js('document.querySelector("#close-source").click(); document.querySelector("[data-tab=graph]").click()')
    wait_for('document.querySelectorAll("#full-graph .graph-node").length > 0')
    js('document.querySelector("#full-graph [data-node]").dispatchEvent(new MouseEvent("click",{bubbles:true}))')
    wait_for('document.querySelector("#ask-concept") !== null')
    screenshot('graph.png')
    js('document.querySelector("[data-tab=document]").click(); document.querySelector("#pdf-page").value=67; document.querySelector("#go-page").click()')
    assert js('document.querySelector("#document-frame").src.includes("page=67")')
    if args.llm:
        js('''window.__qaOriginalFetch=window.fetch;
        window.fetch=async (...args)=>{const r=await window.__qaOriginalFetch(...args);if(String(args[0]).endsWith('/api/ask'))window.__qaAnswer=await r.clone().json();return r;};
        document.querySelector('[data-tab=search]').click();
        document.querySelector('#use-llm').checked=true;
        document.querySelector('#question').value='Xác minh và thẩm định phần mềm khác nhau như thế nào?';
        document.querySelector('#submit-button').click();''')
        wait_for('window.__qaAnswer && !document.querySelector("#results").hidden', timeout=40000)
        answer = js('window.__qaAnswer')
        assert answer['answer_mode'] == 'generated', answer.get('generation_warning')
        assert js('document.querySelectorAll(".answer-content [data-citation]").length > 0')
        assert 'embeddinggemma' in answer['backend']
        (ROOT / 'data' / 'ollama-smoke.json').write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding='utf-8')
        js('document.querySelector("#results").scrollIntoView({block:"start"})')
        screenshot('answer.png')
        print(json.dumps({'answer_mode': answer['answer_mode'], 'elapsed_ms': answer['elapsed_ms'], 'answer': answer['answer']}, ensure_ascii=False), flush=True)
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Page.navigate', {'url': 'http://127.0.0.1:8000/'})
    wait_for('document.querySelector("#stat-pages")?.textContent === "276"')
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    screenshot('mobile.png')
    js('document.querySelector("#menu-button").click()')
    assert js('document.querySelector("#sidebar").classList.contains("open")')
    js('document.querySelector(".chapter-button[data-chapter=6]").click()'.replace('data-chapter=6', "data-chapter=\'6\'"))
    assert js('document.querySelector("#chapter-select").value === "6"')
    assert not js('document.querySelector("#sidebar").classList.contains("open")')
    call('Target.closeTarget', {'targetId': target}, browser=True)

report = {'desktop': 'passed', 'mobile': 'passed', 'search': 'passed', 'source_dialog': 'passed', 'graph': 'passed', 'document_navigation': 'passed', 'chapter_filter': 'passed', 'javascript_errors': errors}
if args.llm:
    report['ollama_answer'] = 'passed'
(output / 'browser-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
assert not errors, errors
print(json.dumps(report, ensure_ascii=False, indent=2))
