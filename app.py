import os
import json
import datetime
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import requests

app = Flask(__name__)

# المجلد الرئيسي المخصص لجمع صور التدريب للذكاء الاصطناعي
BASE_DATASET_DIR = "dataset_for_retraining"
LOCATIONS_FILE = "farm_locations.json"

# إنشاء مجلد التدريب تلقائياً عند تشغيل السيرفر
os.makedirs(BASE_DATASET_DIR, exist_ok=True)

# 1. نقطة النهاية (API Endpoint) لاستقبال المزامنة والصور من تطبيق الأندرويد
@app.route('/api/sync', methods=['POST'])
def sync_farm_data():
    lat = request.form.get('latitude')
    lon = request.form.get('longitude')
    disease_name = request.form.get('disease_name', 'unknown_disease')
    fcm_token = request.form.get('fcm_token', '')
    user_ip = request.remote_addr

    # إنشاء مجلد مستقل لكل مرض على حدة لوضع الصور بداخله
    disease_dir = os.path.join(BASE_DATASET_DIR, disease_name)
    os.makedirs(disease_dir, exist_ok=True)

    # حفظ الصورة المرفوعة داخل مجلد المرض المحدد
    image_file = request.files.get('image')
    if image_file:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{lat}_{lon}_{timestamp}.jpg"
        save_path = os.path.join(disease_dir, filename)
        image_file.save(save_path)

    # حفظ الإحداثيات والـ IP للرصد الفضائي الدوري
    save_location(lat, lon, user_ip, fcm_token)

    return jsonify({
        "status": "success", 
        "message": f"تم حفظ الصورة بنجاح داخل مجلد {disease_name} وتسجيل الإحداثيات"
    }), 200

def save_location(lat, lon, ip, token):
    locations = []
    if os.path.exists(LOCATIONS_FILE):
        try:
            with open(LOCATIONS_FILE, 'r') as f:
                locations = json.load(f)
        except Exception:
            locations = []
    
    locations.append({
        "lat": float(lat),
        "lon": float(lon),
        "ip": ip,
        "token": token,
        "updated_at": str(datetime.datetime.now())
    })

    with open(LOCATIONS_FILE, 'w') as f:
        json.dump(locations, f, indent=4)

# 2. وظيفة الفحص الدوري المجدول مع بوابات الأقمار الاصطناعية (Sentinel-2 / Landsat)
def check_satellite_data():
    if not os.path.exists(LOCATIONS_FILE):
        return

    try:
        with open(LOCATIONS_FILE, 'r') as f:
            farms = json.load(f)
    except Exception:
        return

    for farm in farms:
        lat, lon = farm['lat'], farm['lon']
        # استعلام عن اللقطات الصافية الخالية من الغيوم (<10%) عبر STAC API المفتوحة
        stac_url = "https://earth-search.aws.element84.com/v1/search"
        payload = {
            "collections": ["sentinel-2-l2a"],
            "bbox": [lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01],
            "query": {"eo:cloud_cover": {"lt": 10}},
            "limit": 1
        }
        
        try:
            res = requests.post(stac_url, json=payload).json()
            features = res.get('features', [])
            if features:
                latest_scene = features[0]
                date = latest_scene['properties']['datetime']
                cloud_cover = latest_scene['properties']['eo:cloud_cover']
                print(f"المزرعة ({lat}, {lon}): تم العثور على صورة نظيفة بتاريخ {date} بنسبة غيوم {cloud_cover}%")
        except Exception as e:
            print(f"خطأ أثناء استعلام البيانات الفضائية: {e}")

# تشغيل الفحص الدوري تلقائياً كل 24 ساعة
scheduler = BackgroundScheduler()
scheduler.add_job(check_satellite_data, 'interval', hours=24)
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
