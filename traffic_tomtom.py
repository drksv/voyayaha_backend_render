import os, requests
def get_traffic_status(lat,lon):
    key=os.getenv("TOMTOMKEY") or os.getenv("TOMTOM_API_KEY")
    if not key:return {"status":"Unavailable","source":"fallback"}
    try:
        r=requests.get("https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json",
                       params={"point":f"{lat},{lon}","key":key},timeout=10)
        r.raise_for_status(); d=r.json().get("flowSegmentData")
        if not d:return {"status":"Unavailable"}
        cur=d.get("currentSpeed"); free=d.get("freeFlowSpeed"); ratio=cur/free if free else 1
        level="Low" if ratio>.8 else "Moderate" if ratio>.5 else "High"
        return {"traffic_level":level,"current_speed_kmph":cur,"free_flow_speed_kmph":free,
                "delay_advice":"Minimal" if level=="Low" else "Possible delays" if level=="Moderate" else "Likely delays"}
    except Exception as e: print("Traffic error:",repr(e)); return {"status":"Unavailable","source":"fallback"}
