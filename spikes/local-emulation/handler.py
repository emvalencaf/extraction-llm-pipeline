import time
def handler(event, context):
    time.sleep(float(event.get("sleep", 3)))
    return {"id": event.get("id"), "done": time.time()}
