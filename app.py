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
import ast # เพิ่มเข้ามาเพื่ออ่านค่าจาก Secrets

Image.MAX_IMAGE_PIXELS = None

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

st.set_page_config(page_title="SEO Generator", layout="wide")

# ==========================================
# 1. โค้ดซ่อน UI ของ Streamlit ทั้งหมด
# ==========================================
st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none; }
    footer { visibility: hidden; }
    .viewerBadge_container__1QSob, .viewerBadge_link__1S137 { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. ดึงฐานข้อมูล User จาก Streamlit Secrets
# ==========================================
try:
    # อ่านรายชื่อจากหลังบ้าน Streamlit 
    raw_users = st.secrets.get("APPROVED_USERS", '{"admin": "1234"}')
    
    # แปลงข้อความให้กลายเป็น Dictionary
    if isinstance(raw_users, dict):
        APPROVED_USERS = raw_users
    else:
        APPROVED_USERS = ast.literal_eval(raw_users)
except Exception:
    # ถ้าตั้งค่าหลังบ้านผิดพลาด จะเหลือแค่แอดมินให้เข้าได้เพื่อความปลอดภัย
    APPROVED_USERS = {"admin": "1234"}

# ==========================================
# 3. ระบบเช็กสถานะการ Login
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = ""
if "openai_api_key" not in st.session_state:
    st.session_state["openai_api_key"] = ""
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""

def login_screen():
    st.title("🔒 เข้าสู่ระบบ (SEO Generator)")
    st.caption("ระบบจำกัดสิทธิ์การใช้งาน กรุณาเข้าสู่ระบบก่อนใช้งาน")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("เข้าสู่ระบบ", type="primary")
        
        if submit:
            if username in APPROVED_USERS and APPROVED_USERS[username] == password:
                st.session_state["logged_in"] = True
                st.session_state["current_user"] = username
                st.success("✅ เข้าสู่ระบบสำเร็จ! กำลังพาท่านเข้าสู่ระบบ...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Username หรือ Password ไม่ถูกต้อง (ติดต่อ Admin เพื่อขอสิทธิ์)")

# ==========================================
# 4. หน้าต่างแอปพลิเคชันหลัก (เมื่อ Login ผ่าน)
# ==========================================
def main_app():
    st.title("SEO Generator")
    st.caption(f"🚀 ยินดีต้อนรับคุณ **{st.session_state['current_user']}** | รองรับพรีวิวรูปภาพ & วิดีโอ")
    
    if st.button("🚪 ออกจากระบบ", size="small"):
        st.session_state["logged_in"] = False
        st.rerun()

    with st.sidebar:
        st.header("🔑 ตั้งค่า Cloud Vision AI")
        
        api_choice = st.radio(
            "🎯 เลือก AI Engine ที่ต้องการใช้งาน:",
            ["Gemini API (Google)", "OpenAI API (GPT-4o-mini)"]
        )
        
        st.write("---")
        input_openai = st.text_input("OpenAI API Key (GPT-4o-mini):", value=st.session_state["openai_api_key"], type="password")
        input_gemini = st.text_input("Gemini API Key (ฟรีจาก Google):", value=st.session_state["gemini_api_key"], type="password")
        
        if st.button("💾 บันทึก API Keys", use_container_width=True, type="primary"):
            st.session_state["openai_api_key"] = input_openai.strip()
            st.session_state["gemini_api_key"] = input_gemini.strip()
            st.success("✅ บันทึก API Keys เรียบร้อยแล้ว!")

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

    def make_square_image(img, target_size=512):
        w, h = img.size
        if w == h: return img.resize((target_size, target_size), Image.Resampling.LANCZOS)
        ratio = min(target_size / w, target_size / h)
        new_w, new_h = int(w * ratio), int(h * ratio)
        resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        square_img = Image.new("RGB", (target_size, target_size), (255, 255, 255))
        square_img.paste(resized_img, ((target_size - new_w) // 2, (target_size - new_h) // 2))
        return square_img

    def encode_image_to_base64(pil_img):
        buffered = BytesIO()
        pil_img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def parse_ai_response(text, is_video=False):
        title_match = re.search(r'TITLE:\s*(.*)', text, re.IGNORECASE)
        kw_match = re.search(r'KEYWORDS:\s*(.*)', text, re.IGNORECASE)
        
        raw_title = title_match.group(1).strip() if title_match else text.split('\n')[0].replace('TITLE:', '').strip()
        raw_kw = kw_match.group(1).strip() if kw_match else text.split('\n')[-1].replace('KEYWORDS:', '').strip()
        
        title = clean_title_ascii(raw_title)[:195]
        if len(title) < 180:
            title = (title + " for commercial marketing visual storytelling and creative content design projects asset")[:195]
            
        kw_list = [clean_ascii(k).lower() for k in raw_kw.split(',') if clean_ascii(k)]
        
        fillers = [
            "commercial asset", "stock Media", "high quality", "digital asset", "design element",
            "modern concept", "isolated background", "vivid colors", "artistic detail", "trending concept",
            "marketing resource", "premium aesthetic", "decorative resource", "visual content", "niche market"
        ]
        for f in fillers:
            if len(kw_list) >= 50: break
            if f not in kw_list: kw_list.append(f)
            
        keywords_str = ", ".join(kw_list[:50])
        category = "Videos" if is_video else "Illustrations/Clip Art"
        return title, keywords_str, category

    def process_with_gemini(uploaded_file, api_key):
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = "TITLE: Describe main visual details precisely (no commas, 180-195 chars). KEYWORDS: 50 highly relevant commercial English keywords separated by commas."
        
        is_video = uploaded_file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))
        uploaded_file.seek(0)
        
        if is_video:
            ext = os.path.splitext(uploaded_file.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
                
            g_file = genai.upload_file(path=tmp_path)
            while g_file.state.name == "PROCESSING":
                time.sleep(2)
                g_file = genai.get_file(g_file.name)
                
            response = model.generate_content([prompt, g_file])
            try: genai.delete_file(g_file.name)
            except: pass
            if os.path.exists(tmp_path): os.remove(tmp_path)
        else:
            img = Image.open(uploaded_file).convert("RGB")
            square_img = make_square_image(img, 512)
            response = model.generate_content([prompt, square_img])
            
        return parse_ai_response(response.text, is_video)

    def process_with_openai(uploaded_file, api_key):
        client = OpenAI(api_key=api_key)
        prompt = "TITLE: Describe main visual details precisely (no commas, 180-195 chars). KEYWORDS: 50 highly relevant commercial English keywords separated by commas."
        is_video = uploaded_file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))
        uploaded_file.seek(0)
        
        img = Image.open(uploaded_file).convert("RGB") if not is_video else Image.new("RGB", (512, 512), (200, 200, 200))
        square_img = make_square_image(img, 512)
        base64_img = encode_image_to_base64(square_img)
        
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}],
            max_tokens=300
        )
        return parse_ai_response(res.choices[0].message.content, is_video)

    st.write("รองรับ: **JPG, JPEG, PNG, MP4, MOV** (สูงสุด 100 ไฟล์ต่อรอบ)")
    uploaded_files = st.file_uploader("ลากไฟล์มาวางที่นี่", type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "avi", "webm"], accept_multiple_files=True)

    if uploaded_files:
        st.write(f"📁 **พร้อมประมวลผล:** {len(uploaded_files)} ไฟล์")
        status_placeholders = {}
        
        with st.expander("🖼️ ตัวอย่างไฟล์ที่อัปโหลด (Preview Gallery)", expanded=True):
            cols_per_row = 5
            for i in range(0, len(uploaded_files), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, file in enumerate(uploaded_files[i:i+cols_per_row]):
                    idx = i + j + 1
                    with cols[j]:
                        is_vid = file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))
                        file.seek(0)
                        if not is_vid:
                            try:
                                preview_img = Image.open(file)
                                preview_img.thumbnail((300, 300))
                                st.image(preview_img, caption=f"[{idx}] {file.name[:12]}...", use_container_width=True)
                            except Exception:
                                st.warning(f"[{idx}] 🖼️ {file.name[:12]}...")
                        else:
                            try:
                                st.video(file)
                                st.caption(f"[{idx}] 🎥 {file.name[:12]}...")
                            except Exception:
                                st.info(f"🎥 Video\n\n[{idx}] {file.name[:12]}...")
                        
                        status_placeholders[file.name] = st.empty()
                        status_placeholders[file.name].caption("⏳ รอประมวลผล")

        st.write("---")

        if st.button("🚀 เริ่มสร้าง CSV ทันที", use_container_width=True, type="primary"):
            if "Gemini" in api_choice and not gemini_api_key:
                st.error("❌ คุณเลือกใช้ Gemini API กรุณากรอก Gemini API Key ในแถบด้านซ้ายก่อน")
            elif "OpenAI" in api_choice and not openai_api_key:
                st.error("❌ คุณเลือกใช้ OpenAI API กรุณากรอก OpenAI API Key ในแถบด้านซ้ายก่อน")
            else:
                results = []
                bar = st.progress(0)
                for idx, file in enumerate(uploaded_files):
                    status_placeholders[file.name].info("🔄 ประมวลผล...")
                    try:
                        if "Gemini" in api_choice:
                            if idx > 0: time.sleep(4.5)
                            t, k, c = process_with_gemini(file, gemini_api_key)
                        else:
                            if idx > 0: time.sleep(0.5)
                            t, k, c = process_with_openai(file, openai_api_key)
                            
                        status_placeholders[file.name].success("✅ สำเร็จ")
                        results.append({"Filename": file.name, "Title": t, "Keywords": k, "Category": c, "Release Info": "", "Editorial": "No"})
                    except Exception as e:
                        status_placeholders[file.name].error(f"❌ Error: {e}")
                    bar.progress((idx + 1) / len(uploaded_files))
                    
                if results:
                    st.success("🎉 เสร็จสมบูรณ์! พร้อมดาวน์โหลดไฟล์ CSV")
                    df = pd.DataFrame(results)
                    st.dataframe(df[["Filename", "Title", "Keywords", "Category", "Release Info", "Editorial"]])
                    st.download_button("📥 ดาวน์โหลด CSV สำหรับ Adobe Stock", data=df.to_csv(index=False, encoding="utf-8-sig"), file_name="adobe_stock_seo.csv", mime="text/csv", type="primary")

# ==========================================
# 5. ตัวควบคุมหน้าจอ (แสดงผลตามสถานะ Login)
# ==========================================
if not st.session_state["logged_in"]:
    login_screen()
else:
    main_app()
