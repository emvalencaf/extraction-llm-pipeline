"""Spike 3: Lambda RIE with two simultaneous invokes against ONE container."""
import concurrent.futures as cf, json, time, requests
URL = "http://localhost:9000/2015-03-31/functions/function/invocations"
def call(i):
    t0 = time.time()
    try:
        r = requests.post(URL, json={"id": i, "sleep": 3}, timeout=30)
        return i, r.status_code, r.text[:200], round(time.time() - t0, 2)
    except Exception as e:
        return i, "ERR", repr(e)[:200], round(time.time() - t0, 2)
t0 = time.time()
with cf.ThreadPoolExecutor(2) as ex:
    fs = [ex.submit(call, 1)]
    time.sleep(0.5)
    fs.append(ex.submit(call, 2))
    for f in fs: print(f.result())
print("total wall:", round(time.time() - t0, 2))
