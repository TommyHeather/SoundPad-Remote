import json, os, sys, re, threading
import win32file
from flask import Flask, render_template, request, jsonify
import pystray
from PIL import Image, ImageDraw
from werkzeug.utils import secure_filename

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask(__name__, template_folder=template_folder)
else:
    app = Flask(__name__)

UI_CONFIG = 'ui_config.json'

def sp_command(cmd):
    try:
        handle = win32file.CreateFile(r'\\.\pipe\sp_remote_control',
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None, win32file.OPEN_EXISTING, 0, None)
        win32file.WriteFile(handle, cmd.encode('utf-8'))
        _, data = win32file.ReadFile(handle, 1048576)
        win32file.CloseHandle(handle)
        return data.decode('utf-8')
    except:
        return ""

def get_live_sounds():
    xml_data = sp_command("GetSoundlist()")
    sounds = []
    
    for match in re.finditer(r'<Sound\s+(.+?)>', xml_data):
        attrs = match.group(1)
        
        index_match = re.search(r'index="(\d+)"', attrs)
        title_match = re.search(r'title="([^"]+)"', attrs)
        duration_match = re.search(r'duration="([^"]+)"', attrs)
        
        if index_match and title_match:
            dur_str = ""
            duration_ms = 0
            
            if duration_match:
                raw_dur = duration_match.group(1)
                if raw_dur.isdigit(): 
                    duration_ms = int(raw_dur)
                    minutes, seconds = divmod(duration_ms // 1000, 60)
                    dur_str = f"{minutes}:{seconds:02d}" if duration_ms > 0 else ""
                else: 
                    dur_str = raw_dur
            
            sounds.append({
                "index": index_match.group(1),
                "title": title_match.group(1),
                "duration": dur_str,
                "duration_ms": duration_ms
            })
    return sounds

def load_ui():
    if not os.path.exists(UI_CONFIG):
        return {}
    with open(UI_CONFIG, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.route('/')
def index():
    sounds = get_live_sounds()
    ui_data = load_ui()
    
    categories = {}
    for s in sounds:
        title = s['title']
        custom = ui_data.get(title, {"category": "Без категории", "icon": "🎵"})
        cat = custom["category"]
        
        if cat not in categories:
            categories[cat] = []
            
        categories[cat].append({
            "index": s["index"],
            "title": title,
            "icon": custom["icon"],
            "category": cat,
            "duration": s["duration"],
            "duration_ms": s["duration_ms"]
        })
    return render_template('index.html', categories=categories)

@app.route('/play/<index>')
def play(index):
    sp_command(f"DoPlaySound({index})")
    return "ok"

@app.route('/pause')
def pause():
    sp_command("DoTogglePause()")
    return "ok"

@app.route('/stop')
def stop():
    sp_command("DoStopSound()")
    return "ok"

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    ui_data = load_ui()
    ui_data[data['title']] = {"category": data['category'], "icon": data['icon']}
    with open(UI_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(ui_data, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "ok"})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file", 400
    file = request.files['file']
    if file.filename == '':
        return "No filename", 400
    
    os.makedirs("sounds", exist_ok=True)
    save_path = os.path.abspath(os.path.join("sounds", secure_filename(file.filename)))
    file.save(save_path)
    sp_command(f'DoAddSound("{save_path}")')
    return jsonify({"status": "ok"})

def run_flask():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def create_icon():
    image = Image.new('RGB', (64, 64), color=(0, 255, 136))
    draw = ImageDraw.Draw(image)
    draw.rectangle([(16, 16), (48, 48)], fill=(18, 18, 18))
    return image

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    icon = pystray.Icon("SP Remote", create_icon(), "SoundPad Remote", menu=pystray.Menu(
        pystray.MenuItem('Закрыть пульт', lambda icon, item: (icon.stop(), os._exit(0)))
    ))
    icon.run()
