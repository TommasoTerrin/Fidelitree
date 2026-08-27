import urllib.request
import urllib.parse
import json
import http.cookiejar
import ssl

BASE_URL = "http://127.0.0.1:8001"
CARD_1 = "38a6f69c-07d2-4205-a480-a24319159328"
CARD_2 = "e2274a34-4ad9-47af-a8fa-99165a9de814"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

results = []

def make_request(method, url, data=None, json_body=None, headers=None):
    if headers is None:
        headers = {}
    
    encoded_data = None
    if data is not None:
        encoded_data = urllib.parse.urlencode(data).encode('utf-8')
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
    elif json_body is not None:
        encoded_data = json.dumps(json_body).encode('utf-8')
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
            
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    
    status = None
    resp_body = None
    resp_headers = {}
    try:
        with opener.open(req) as resp:
            status = resp.status
            resp_body = resp.read().decode('utf-8')
            resp_headers = dict(resp.info())
    except urllib.error.HTTPError as e:
        status = e.code
        resp_body = e.read().decode('utf-8')
        resp_headers = dict(e.headers)
    except Exception as e:
        status = 0
        resp_body = str(e)
        
    try:
        parsed_json = json.loads(resp_body) if resp_body else None
    except Exception:
        parsed_json = None
        
    return {
        "status": status,
        "body_raw": resp_body,
        "body_json": parsed_json,
        "headers": resp_headers,
        "cookies": {cookie.name: cookie.value for cookie in cj}
    }

print("Starting tests against", BASE_URL)

# Step 1: Login
print("\n--- STEP 1: Login ---")
step1_resp = make_request("POST", f"{BASE_URL}/merchant/login", data={
    "phone_number": "+393319910276",
    "password": "prova"
})
has_cookie = "access_token" in step1_resp["cookies"]
step1_pass = (step1_resp["status"] in [200, 302, 303]) and has_cookie
print(f"Status: {step1_resp['status']}")
print(f"Cookies: {step1_resp['cookies']}")
print(f"Result: {'PASS' if step1_pass else 'FAIL'}")

# Step 2: Add cashback points (5.50)
print("\n--- STEP 2: Add cashback points (5.50) ---")
step2_resp = make_request("POST", f"{BASE_URL}/api/merchant/add-point/{CARD_1}", json_body={"cb_points": 5.50})
print(f"Status: {step2_resp['status']}")
print(f"Body: {step2_resp['body_raw']}")
cb_val = None
if step2_resp["body_json"]:
    cb_val = step2_resp["body_json"].get("cashback_point")
step2_pass = (step2_resp["status"] == 200) and (cb_val == 5.5 or cb_val == 5.50)
print(f"cashback_point: {cb_val}, Result: {'PASS' if step2_pass else 'FAIL'}")

# Step 3: Remove some cashback (-2.00)
print("\n--- STEP 3: Remove cashback (-2.00) ---")
step3_resp = make_request("POST", f"{BASE_URL}/api/merchant/add-point/{CARD_1}", json_body={"cb_points": -2.00})
print(f"Status: {step3_resp['status']}")
print(f"Body: {step3_resp['body_raw']}")
cb_val3 = None
if step3_resp["body_json"]:
    cb_val3 = step3_resp["body_json"].get("cashback_point")
step3_pass = (step3_resp["status"] == 200) and (cb_val3 == 3.5 or cb_val3 == 3.50)
print(f"cashback_point: {cb_val3}, Result: {'PASS' if step3_pass else 'FAIL'}")

# Step 4: Try to go below zero (-10.00)
print("\n--- STEP 4: Try negative cashback below zero (-10.00) ---")
step4_resp = make_request("POST", f"{BASE_URL}/api/merchant/add-point/{CARD_1}", json_body={"cb_points": -10.00})
print(f"Status: {step4_resp['status']}")
print(f"Body: {step4_resp['body_raw']}")
step4_pass = (step4_resp["status"] == 400)
print(f"Result: {'PASS' if step4_pass else 'FAIL'}")

# Step 5: Add tree points below threshold (+5)
print("\n--- STEP 5: Add tree points below threshold (+5) ---")
step5_resp = make_request("POST", f"{BASE_URL}/api/merchant/add-tree-points/{CARD_1}", json_body={"tree_points": 5})
print(f"Status: {step5_resp['status']}")
print(f"Body: {step5_resp['body_raw']}")
planted_now5 = step5_resp["body_json"].get("planted_now") if step5_resp["body_json"] else None
tree_pts5 = step5_resp["body_json"].get("tree_points") if step5_resp["body_json"] else None
step5_pass = (step5_resp["status"] == 200) and (planted_now5 == 0) and (tree_pts5 == 5)
print(f"tree_points: {tree_pts5}, planted_now: {planted_now5}, Result: {'PASS' if step5_pass else 'FAIL'}")

# Step 6: Add tree points to reach threshold (+5)
print("\n--- STEP 6: Add tree points to reach threshold (+5) ---")
step6_resp = make_request("POST", f"{BASE_URL}/api/merchant/add-tree-points/{CARD_1}", json_body={"tree_points": 5})
print(f"Status: {step6_resp['status']}")
print(f"Body: {step6_resp['body_raw']}")
planted_now6 = step6_resp["body_json"].get("planted_now") if step6_resp["body_json"] else None
tree_pts6 = step6_resp["body_json"].get("tree_points") if step6_resp["body_json"] else None
warning6 = step6_resp["body_json"].get("warning") if step6_resp["body_json"] else ""
step6_pass = (step6_resp["status"] == 200) and (planted_now6 == 0) and (tree_pts6 == 10) and ("Ecologi" in str(warning6) or "key" in str(warning6) or "chiave" in str(warning6) or warning6 is not None)
print(f"tree_points: {tree_pts6}, planted_now: {planted_now6}, warning: {warning6}, Result: {'PASS' if step6_pass else 'FAIL'}")

# Step 7: Try negative tree points below zero (-20)
print("\n--- STEP 7: Negative tree points below zero (-20) ---")
step7_resp = make_request("POST", f"{BASE_URL}/api/merchant/add-tree-points/{CARD_1}", json_body={"tree_points": -20})
print(f"Status: {step7_resp['status']}")
print(f"Body: {step7_resp['body_raw']}")
step7_pass = (step7_resp["status"] == 400)
print(f"Result: {'PASS' if step7_pass else 'FAIL'}")

# Step 8: Verify card state
print("\n--- STEP 8: Verify card state ---")
step8_resp = make_request("GET", f"{BASE_URL}/api/card/{CARD_1}")
print(f"Status: {step8_resp['status']}")
print(f"Body: {step8_resp['body_raw']}")
step8_pass = (step8_resp["status"] == 200) and (step8_resp["body_json"] is not None)
print(f"Result: {'PASS' if step8_pass else 'FAIL'}")

# Step 9: Delete card for merchant 2 with merchant 1's cookie
print("\n--- STEP 9: Delete unowned card ---")
step9_resp = make_request("DELETE", f"{BASE_URL}/api/merchant/card/{CARD_2}")
print(f"Status: {step9_resp['status']}")
print(f"Body: {step9_resp['body_raw']}")
step9_pass = (step9_resp["status"] == 404)
print(f"Result: {'PASS' if step9_pass else 'FAIL'}")

# Save full results to JSON
full_output = {
    "step1": {"pass": step1_pass, "resp": step1_resp},
    "step2": {"pass": step2_pass, "resp": step2_resp},
    "step3": {"pass": step3_pass, "resp": step3_resp},
    "step4": {"pass": step4_pass, "resp": step4_resp},
    "step5": {"pass": step5_pass, "resp": step5_resp},
    "step6": {"pass": step6_pass, "resp": step6_resp},
    "step7": {"pass": step7_pass, "resp": step7_resp},
    "step8": {"pass": step8_pass, "resp": step8_resp},
    "step9": {"pass": step9_pass, "resp": step9_resp},
}
with open("test_results.json", "w") as f:
    json.dump(full_output, f, indent=2)
