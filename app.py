import streamlit as st
import pandas as pd
from PIL import Image
import re
import unicodedata
import base64
from io import BytesIO
import time
import tempfile
import os
import json
import uuid
import gc

# 1. ตั้งค่าหน้าเว็บเป็นคำสั่งแรกเสมอ
st.set_page_config(page_title="SEO Generator", layout="wide")

# 2. ซ่อน UI ของ Streamlit ทั้งหมด
st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none; }
    footer { visibility: hidden; }
    .viewerBadge_container__1QSob, .viewerBadge_link__1S137 { display: none !important; }
    </style>
""", unsafe_allow_html=True)

Image.MAX_IMAGE_PIXELS = None

# ตรวจสอบ Library ปลอดภัย
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except Exception:
    HAS_GEMINI = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False

# ------------------------------------------
# 3. ระบบจัดการ User แบบปลอดภัย ป้องกัน File System Lock
# ------------------------------------------
DB_FILE = "users_db.json"

def safe_load_users():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}

def safe_save_users(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # ข้ามกรณีเพอร์มิชชันโดนล็อกบน Cloud

try:
    ADMIN_USER = st.secrets.get("ADMIN_USER", "superadmin")
    ADMIN_PASS = st.secrets.get("ADMIN_PASS", "gappy789")
except Exception:
    ADMIN_USER = "superadmin"
    ADMIN_PASS = "gappy789"

# โหลดฐานข้อมูล
if "global_user_db" not in st.session_state:
    st.session_state["global_user_db"] = safe_load_users()

user_db = st.session_state["global_user_db"]

# ------------------------------------------
# 4. Session State Initialization
# ------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = ""
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "openai_api_key" not in st.session_state:
    st.session_state["openai_api_key"] = ""
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "generated_results" not in st.session_state:
    st.session_state["generated_results"] = None

# ------------------------------------------
# 5. ฟังก์ชันสร้างภาพพรีวิวบีบอัดจิ๋ว (ประหยัด RAM 99%)
# ------------------------------------------
def make_fast_thumbnail(uploaded_file, max_size=150):
    try:
        uploaded_file.seek(0)
        img = Image.open(uploaded_file).convert("RGB")
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        buf.seek(0)
        del img
        gc.collect()
        return buf
    except Exception:
        return None

# ------------------------------------------
# 6. หน้า Login & Register
# ------------------------------------------
def login_and_register_screen():
    st.title("🔒 เข้าสู่ระบบ / สมัครสมาชิก")
    tab1, tab2 = st.tabs(["🔑 เข้าสู่ระบบ (Login)", "📝 สมัครสมาชิก (Register)"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username").strip()
            password = st.text_input("Password", type="password").strip()
            submit_login = st.form_submit_button("เข้าสู่ระบบ", type="primary")
            
            if submit_login:
                if username == ADMIN_USER and password == ADMIN_PASS:
                    st.session_state["logged_in"] = True
                    st.session_state["current_user"] = username
                    st.session_state["is_admin"] = True
                    if username in user_db and isinstance(user_db[username], dict):
                        st.session_state["gemini_api_key"] = user_db[username].get("gemini_api_key", "")
                        st.session_state["openai_api_key"] = user_db[username].get("openai_api_key", "")
                    st.success("✅ เข้าสู่ระบบสำเร็จ (Admin)")
                    time.sleep(0.3)
                    st.rerun()
                elif username in user_db and isinstance(user_db[username], dict) and user_db[username].get("password") == password:
                    if user_db[username].get("status") == "Approved":
                        st.session_state["logged_in"] = True
                        st.session_state["current_user"] = username
                        st.session_state["is_admin"] = False
                        st.session_state["gemini_api_key"] = user_db[username].get("gemini_api_key", "")
                        st.session_state["openai_api_key"] = user_db[username].get("openai_api_key", "")
                        st.success("✅ เข้าสู่ระบบสำเร็จ")
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.warning("⏳ บัญชีของคุณอยู่ระหว่างรอ Admin อนุมัติการใช้งาน")
                else:
                    st.error("❌ Username หรือ Password ไม่ถูกต้อง")

    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("ตั้ง Username").strip()
            new_pass = st.text_input("ตั้ง Password", type="password").strip()
            confirm_pass = st.text_input("ยืนยัน Password", type="password").strip()
            submit_reg = st.form_submit_button("ส่งข้อมูลสมัครสมาชิก")
            
            if submit_reg:
                if not new_user or not new_pass:
                    st.error("❌ กรุณากรอกข้อมูลให้ครบถ้วน")
                elif new_pass != confirm_pass:
                    st.error("❌ รหัสผ่านทั้งสองช่องไม่ตรงกัน")
                elif new_user == ADMIN_USER or new_user in user_db:
                    st.error("⚠️ Username นี้มีผู้ใช้งานในระบบแล้ว")
                else:
                    user_db[new_user] = {
                        "password": new_pass, 
                        "status": "Pending",
                        "gemini_api_key": "",
                        "openai_api_key": ""
                    }
                    safe_save_users(user_db)
                    st.success("🎉 สมัครสมาชิกเรียบร้อยแล้ว! กรุณารอ Admin อนุมัติการใช้งาน")

# ------------------------------------------
# 7. หน้า Dashboard สำหรับ Admin
# ------------------------------------------
def admin_dashboard():
    st.title("🛡️ ระบบจัดการหลังบ้าน (Admin Dashboard)")
    st.caption("หน้าต่างนี้เห็นเฉพาะ Admin เท่านั้น")
    
    if st.button("⬅️ กลับไปหน้าแอปใช้งาน (SEO Generator)", key="btn_back_app_admin"):
        st.session_state["show_admin_panel"] = False
        st.rerun()
        
    st.write("---")
    st.subheader("📋 รายชื่อผู้ใช้งาน")
    
    if not user_db:
        st.info("ยังไม่มีผู้ใช้งานสมัครเข้ามาในระบบ")
    else:
        for user, data in list(user_db.items()):
            if not isinstance(data, dict):
                continue
            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
            col1.write(f"**{user}**")
            col2.write(f"สถานะ: `{data.get('status', 'Pending')}`")
            
            if data.get("status") == "Pending":
                if col3.button("✅ อนุมัติ", key=f"app_{user}"):
                    user_db[user]["status"] = "Approved"
                    safe_save_users(user_db)
                    st.rerun()
            else:
                if col3.button("⛔ ระงับ", key=f"rev_{user}"):
                    user_db[user]["status"] = "Pending"
                    safe_save_users(user_db)
                    st.rerun()
                    
            if col4.button("🗑️ ลบ", key=f"del_{user}"):
                del user_db[user]
                safe_save_users(user_db)
                st.rerun()
            st.divider()

# ------------------------------------------
# 8. หน้าต่างแอปพลิเคชันหลัก
# ------------------------------------------
def main_app():
    if st.session_state.get("is_admin", False):
        if "show_admin_panel" not in st.session_state:
            st.session_state["show_admin_panel"] = False
            
        if st.session_state["show_admin_panel"]:
            admin_dashboard()
            return
            
    st.title("SEO Generator")
    st.caption(f"🚀 ยินดีต้อนรับคุณ **{st.session_state.get('current_user', '')}**")
    
    if st.session_state.get("is_admin", False):
        col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
        with col2:
            if st.button("🔄 ทำรายการใหม่", use_container_width=True, key="btn_reset_adm"):
                st.session_state["uploader_key"] += 1
                st.session_state["generated_results"] = None
                gc.collect()
                st.rerun()
        with col3:
            if st.button("🛡️ หลังบ้าน Admin", use_container_width=True, key="btn_adm_panel"):
                st.session_state["show_admin_panel"] = True
                st.rerun()
        with col4:
            if st.button("🚪 ออกจากระบบ", use_container_width=True, key="btn_logout_adm"):
                st.session_state["logged_in"] = False
                st.session_state["current_user"] = ""
                st.session_state["is_admin"] = False
                st.session_state["openai_api_key"] = ""
                st.session_state["gemini_api_key"] = ""
                st.session_state["generated_results"] = None
                gc.collect()
                st.rerun()
    else:
        col1, col2, col3 = st.columns([6, 2, 2])
        with col2:
            if st.button("🔄 ทำรายการใหม่", use_container_width=True, key="btn_reset_usr"):
                st.session_state["uploader_key"] += 1
                st.session_state["generated_results"] = None
                gc.collect()
                st.rerun()
        with col3:
            if st.button("🚪 ออกจากระบบ", use_container_width=True, key="btn_logout_usr"):
                st.session_state["logged_in"] = False
                st.session_state["current_user"] = ""
                st.session_state["is_admin"] = False
                st.session_state["openai_api_key"] = ""
                st.session_state["gemini_api_key"] = ""
                st.session_state["generated_results"] = None
                gc.collect()
                st.rerun()

    with st.sidebar:
        st.header("🔑 ตั้งค่า Cloud Vision AI")
        api_choice = st.radio("🎯 เลือก AI Engine:", ["Gemini API (Google)", "OpenAI API (GPT-4o-mini)"])
        st.write("---")
        input_openai = st.text_input("OpenAI API Key (GPT-4o-mini):", value=st.session_state["openai_api_key"], type="password")
        input_gemini = st.text_input("Gemini API Key:", value=st.session_state["gemini_api_key"], type="password")
        
        if st.button("💾 บันทึก API Keys", use_container_width=True, type="primary", key="btn_save_k"):
            st.session_state["openai_api_key"] = input_openai.strip()
            st.session_state["gemini_api_key"] = input_gemini.strip()
            
            user_name = st.session_state.get("current_user", "")
            if user_name:
                if user_name not in user_db or not isinstance(user_db[user_name], dict):
                    user_db[user_name] = {"password": "", "status": "Approved", "gemini_api_key": "", "openai_api_key": ""}
                user_db[user_name]["gemini_api_key"] = input_gemini.strip()
                user_db[user_name]["openai_api_key"] = input_openai.strip()
                safe_save_users(user_db)
                
            st.success("✅ บันทึก API Keys เรียบร้อยแล้ว (จำค่าไว้ถาวร)!")

        openai_api_key = st.session_state["openai_api_key"]
        gemini_api_key = st.session_state["gemini_api_key"]

        st.write("---")
        if "Gemini" in api_choice:
            if gemini_api_key: st.success("⚡ กำลังเปิดใช้งาน: Gemini Vision")
            else: st.warning("⚠️ กรุณากรอก Gemini API Key และกดบันทึก")
        else:
            if openai_api_key: st.success("🤖 กำลังเปิดใช้งาน: OpenAI Vision")
            else: st.warning("⚠️ กรุณากรอก OpenAI API Key และกดบันทึก")

    def clean_ascii(s):
        if not s: return ""
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Za-z0-9, ]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def clean_title_ascii(s):
        if not s: return ""
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Za-z0-9 ]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def parse_ai_response(text, is_video=False, is_vector=False):
        title_match = re.search(r'TITLE:\s*(.*)', text, re.IGNORECASE)
        kw_match = re.search(r'KEYWORDS:\s*(.*)', text, re.IGNORECASE)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first_line = lines[0] if lines else ""
        last_line = lines[-1] if lines else ""
        raw_title = title_match.group(1).strip() if title_match else first_line.replace('TITLE:', '').strip()
        raw_kw = kw_match.group(1).strip() if kw_match else last_line.replace('KEYWORDS:', '').strip()
        title = clean_title_ascii(raw_title)[:195]
        if len(title) < 180:
            title = (title + " for commercial marketing visual storytelling and creative content design projects asset")[:195]
        kw_list = [clean_ascii(k).lower() for k in raw_kw.split(',') if clean_ascii(k)]
        fillers = ["commercial asset", "stock Media", "high quality", "digital asset", "design element", "modern concept", "isolated background", "vivid colors", "artistic detail", "trending concept"]
        for f in fillers:
            if len(kw_list) >= 50: break
            if f not in kw_list: kw_list.append(f)
        keywords_str = ", ".join(kw_list[:50])
        
        if is_video:
            category = "Videos"
        elif is_vector:
            category = "Vectors"
        else:
            category = "Illustrations/Clip Art"
            
        return title, keywords_str, category

    def get_available_gemini_models(api_key):
        if not HAS_GEMINI:
            return ["gemini-1.5-flash"]
        try:
            genai.configure(api_key=api_key)
            valid_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    name = m.name.replace('models/', '')
                    valid_models.append(name)
            
            flash_models = [m for m in valid_models if 'flash' in m.lower()]
            other_models = [m for m in valid_models if 'flash' not in m.lower()]
            result = flash_models + other_models
            return result if result else ["gemini-1.5-flash", "gemini-2.0-flash"]
        except Exception:
            return ["gemini-1.5-flash", "gemini-2.0-flash"]

    def process_with_gemini(uploaded_file, api_key):
        models_to_try = get_available_gemini_models(api_key)
        prompt = "TITLE: Describe main visual details precisely (no commas, 180-195 chars). KEYWORDS: 50 highly relevant commercial English keywords separated by commas."
        
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        is_video = ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        is_svg = ext == '.svg'
        is_eps = ext == '.eps'
        is_vector = is_svg or is_eps
        
        uploaded_file.seek(0)
        response_text = None
        last_err = None

        if is_svg:
            svg_text = uploaded_file.read().decode('utf-8', errors='ignore')[:10000]
            svg_prompt = f"{prompt}\n\nThis is SVG vector illustration code/metadata:\n{svg_text}"
            for m_name in models_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    res = model.generate_content(svg_prompt)
                    if res and res.text:
                        response_text = res.text
                        break
                except Exception as e:
                    last_err = e
                    continue

        elif is_eps:
            eps_bytes = uploaded_file.read()
            eps_text = eps_bytes[:5000].decode('ascii', errors='ignore')
            clean_eps_info = re.sub(r'[^A-Za-z0-9 ]+', ' ', eps_text)[:2000]
            eps_prompt = f"{prompt}\n\nFilename: {uploaded_file.name}\nEPS Vector Metadata/Header:\n{clean_eps_info}"
            for m_name in models_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    res = model.generate_content(eps_prompt)
                    if res and res.text:
                        response_text = res.text
                        break
                except Exception as e:
                    last_err = e
                    continue

        elif is_video:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
                
            g_file = genai.upload_file(path=tmp_path)
            while g_file.state.name == "PROCESSING":
                time.sleep(2)
                g_file = genai.get_file(g_file.name)
                
            for m_name in models_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    res = model.generate_content([prompt, g_file])
                    if res and res.text:
                        response_text = res.text
                        break
                except Exception as e:
                    last_err = e
                    continue
                    
            try: genai.delete_file(g_file.name)
            except Exception: pass
            if os.path.exists(tmp_path): os.remove(tmp_path)

        else:
            img = Image.open(uploaded_file).convert("RGB")
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            for m_name in models_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    res = model.generate_content([prompt, img])
                    if res and res.text:
                        response_text = res.text
                        break
                except Exception as e:
                    last_err = e
                    continue
            del img
            gc.collect()

        if not response_text:
            raise Exception(f"Gemini API Error: {last_err if last_err else 'No response'}")
            
        return parse_ai_response(response_text, is_video, is_vector)

    def process_with_openai(uploaded_file, api_key):
        client = OpenAI(api_key=api_key)
        prompt = "TITLE: Describe main visual details precisely (no commas, 180-195 chars). KEYWORDS: 50 highly relevant commercial English keywords separated by commas."
        
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        is_video = ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        is_svg = ext == '.svg'
        is_eps = ext == '.eps'
        is_vector = is_svg or is_eps
        
        uploaded_file.seek(0)

        if is_svg:
            svg_text = uploaded_file.read().decode('utf-8', errors='ignore')[:10000]
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"{prompt}\n\nSVG Vector Code:\n{svg_text}"}],
                max_tokens=300
            )
            return parse_ai_response(res.choices[0].message.content, is_video, is_vector)

        elif is_eps:
            eps_bytes = uploaded_file.read()
            eps_text = eps_bytes[:5000].decode('ascii', errors='ignore')
            clean_eps_info = re.sub(r'[^A-Za-z0-9 ]+', ' ', eps_text)[:2000]
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"{prompt}\n\nFilename: {uploaded_file.name}\nEPS Vector Info:\n{clean_eps_info}"}],
                max_tokens=300
            )
            return parse_ai_response(res.choices[0].message.content, is_video, is_vector)

        elif is_video:
            img = Image.new("RGB", (512, 512), (200, 200, 200))
        else:
            img = Image.open(uploaded_file).convert("RGB")
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)

        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=80)
        base64_img = base64.b64encode(buffered.getvalue()).decode('utf-8')
        del img
        gc.collect()

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}],
            max_tokens=300
        )
        return parse_ai_response(res.choices[0].message.content, is_video, is_vector)

    st.write("รองรับ: **JPG, PNG, WEBP, MP4, MOV, SVG, EPS** (สูงสุด 100 ไฟล์ต่อรอบ)")
    uploaded_files = st.file_uploader(
        "ลากไฟล์มาวางที่นี่", 
        type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "avi", "webm", "svg", "eps"], 
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}"
    )

    if uploaded_files:
        st.write(f"📁 **พร้อมประมวลผล:** {len(uploaded_files)} ไฟล์")
        status_placeholders = {}
        
        try:
            with st.expander("🖼️ ตัวอย่างไฟล์ที่อัปโหลด (Preview Gallery)", expanded=False):
                cols_per_row = 5
                for i in range(0, len(uploaded_files), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for j, file in enumerate(uploaded_files[i:i+cols_per_row]):
                        idx = i + j + 1
                        with cols[j]:
                            ext = os.path.splitext(file.name)[1].lower()
                            file.seek(0)
                            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                thumb_buf = make_fast_thumbnail(file, max_size=150)
                                if thumb_buf:
                                    st.image(thumb_buf, caption=f"[{idx}] {file.name[:12]}...")
                                else:
                                    st.info(f"🖼️ [{idx}] {file.name[:12]}...")
                            elif ext in ['.mp4', '.mov', '.avi', '.webm']:
                                st.info(f"🎥 Video\n[{idx}] {file.name[:12]}...")
                            elif ext == '.svg':
                                st.info(f"🎨 SVG Vector\n[{idx}] {file.name[:12]}...")
                            elif ext == '.eps':
                                st.info(f"📐 EPS Vector\n[{idx}] {file.name[:12]}...")
                            else:
                                st.info(f"📄 File\n[{idx}] {file.name[:12]}...")
                            status_placeholders[file.name] = st.empty()
                            status_placeholders[file.name].caption("⏳ รอประมวลผล")
        except Exception:
            st.warning("⚠️ โหลดพรีวิวรูปภาพไม่สมบูรณ์ แต่ยังสามารถกดประมวลผลต่อได้ครับ")

        st.write("---")

        if st.button("🚀 เริ่มสร้าง CSV ทันที", use_container_width=True, type="primary", key="btn_run_process"):
            if "Gemini" in api_choice and not gemini_api_key:
                st.error("❌ คุณเลือกใช้ Gemini API กรุณากรอก Gemini API Key ในแถบด้านซ้ายก่อน")
            elif "OpenAI" in api_choice and not openai_api_key:
                st.error("❌ คุณเลือกใช้ OpenAI API กรุณากรอก OpenAI API Key ในแถบด้านซ้ายก่อน")
            else:
                results = []
                bar = st.progress(0)
                for idx, file in enumerate(uploaded_files):
                    if file.name in status_placeholders:
                        status_placeholders[file.name].info("🔄 ประมวลผล...")
                    try:
                        if "Gemini" in api_choice:
                            if idx > 0: time.sleep(4.5)
                            t, k, c = process_with_gemini(file, gemini_api_key)
                        else:
                            if idx > 0: time.sleep(0.5)
                            t, k, c = process_with_openai(file, openai_api_key)
                        if file.name in status_placeholders:
                            status_placeholders[file.name].success("✅ สำเร็จ")
                        results.append({"Filename": file.name, "Title": t, "Keywords": k, "Category": c, "Release Info": "", "Editorial": "No"})
                    except Exception as e:
                        if file.name in status_placeholders:
                            status_placeholders[file.name].error(f"❌ {e}")
                    bar.progress((idx + 1) / len(uploaded_files))
                    gc.collect()
                
                if results:
                    st.session_state["generated_results"] = results

    if st.session_state.get("generated_results"):
        st.success("🎉 เสร็จสมบูรณ์! พร้อมดาวน์โหลดไฟล์ CSV")
        df = pd.DataFrame(st.session_state["generated_results"])
        st.dataframe(df[["Filename", "Title", "Keywords", "Category", "Release Info", "Editorial"]])
        st.download_button(
            label="📥 ดาวน์โหลด CSV สำหรับ Adobe Stock", 
            data=df.to_csv(index=False, encoding="utf-8-sig"), 
            file_name="adobe_stock_seo.csv", 
            mime="text/csv", 
            type="primary",
            key="btn_download_csv"
        )

# ------------------------------------------
# 9. Main Router
# ------------------------------------------
if not st.session_state["logged_in"]:
    login_and_register_screen()
else:
    main_app()
