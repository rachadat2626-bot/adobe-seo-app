import streamlit as st
import pandas as pd
from PIL import Image
import re
import unicodedata
import cv2
import numpy as np
import base64
from io import BytesIO
import time

# ---------------------------------------------------------
# 0. ปลดล็อกขีดจำกัดขนาดภาพ PIL (รองรับ 50MB+)
# ---------------------------------------------------------
Image.MAX_IMAGE_PIXELS = None

# นำเข้า SDK สำคัญ
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

# ---------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ
# ---------------------------------------------------------
st.set_page_config(page_title="Adobe Stock SEO Cloud Generator", layout="wide")

if "openai_api_key" not in st.session_state:
    st.session_state["openai_api_key"] = ""
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""

st.title("⚡ Adobe Stock SEO Generator (Cloud Version)")
st.caption("🚀 รองรับ 80-100 ไฟล์ | ระบบออนไลน์ไร้ขีดจำกัด | ขับเคลื่อนด้วย Gemini & OpenAI Vision")

# แถบ Sidebar สำหรับกรอกและบันทึก API Keys
with st.sidebar:
    st.header("🔑 ตั้งค่า Cloud Vision AI")
    
    input_openai = st.text_input(
        "OpenAI API Key (GPT-4o-mini):", 
        value=st.session_state["openai_api_key"], 
        type="password", 
        help="รับ Key ได้ที่ platform.openai.com"
    )
    
    input_gemini = st.text_input(
        "Gemini API Key (ฟรีจาก Google):", 
        value=st.session_state["gemini_api_key"], 
        type="password", 
        help="รับ Key ฟรีได้ที่ aistudio.google.com"
    )
    
    if st.button("💾 บันทึก API Keys", use_container_width=True, type="primary"):
        st.session_state["openai_api_key"] = input_openai.strip()
        st.session_state["gemini_api_key"] = input_gemini.strip()
        st.success("✅ บันทึก API Keys เรียบร้อยแล้ว!")

    openai_api_key = st.session_state["openai_api_key"]
    gemini_api_key = st.session_state["gemini_api_key"]

    st.write("---")
    if openai_api_key:
        st.success("🤖 เปิดใช้งาน OpenAI Precision Engine")
    elif gemini_api_key:
        st.success("⚡ เปิดใช้งาน Gemini Vision (พร้อมระบบหน่วงเวลาโควต้าฟรี)")
    else:
        st.warning("⚠️ กรุณาใส่ API Key อย่างน้อย 1 ช่องเพื่อเริ่มใช้งาน")

st.write("---")

# ---------------------------------------------------------
# 2. ฟังก์ชันทำความสะอาดข้อความ
# ---------------------------------------------------------
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
    if w == h:
        return img.resize((target_size, target_size), Image.Resampling.LANCZOS)
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

# ---------------------------------------------------------
# 3. ฟังก์ชันจัดการไฟล์อัปโหลด
# ---------------------------------------------------------
def process_uploaded_file(uploaded_file):
    filename_lower = uploaded_file.name.lower()
    uploaded_file.seek(0)
    
    if filename_lower.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        
        # สำหรับวิดีโอบน Streamlit Cloud ไม่บันทึกไฟล์ชั่วคราวเพื่อประหยัดพื้นที่
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(file_bytes)
            temp_video_path = tmp.name
            
        cap = cv2.VideoCapture(temp_video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        middle_frame = int(total_frames / 2) if total_frames > 0 else 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
        ret, frame = cap.read()
        cap.release()
        
        import os
        if os.path.exists(temp_video_path): os.remove(temp_video_path)
        
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            file_type = "Video"
        else:
            return None, None, None
    else:
        img = Image.open(uploaded_file)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode != 'RGBA': img = img.convert('RGBA')
            mask = img.split()[3] if len(img.split()) == 4 else None
            background.paste(img, mask=mask)
            img = background
        else:
            img = img.convert("RGB")
        file_type = "Image"
        uploaded_file.seek(0)

    img_preview = img.copy()
    img_preview.thumbnail((400, 400))
    img_ai = make_square_image(img, 512)
    return img_preview, img_ai, file_type

# ---------------------------------------------------------
# 4. ฟังก์ชันสร้าง Metadata
# ---------------------------------------------------------
def generate_metadata_with_gemini(image_pil, api_key, filename, file_type):
    genai.configure(api_key=api_key)
    
    models_to_try = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name or 'gemini' in m.name:
                    models_to_try.append(m.name)
    except Exception:
        pass

    models_to_try.extend(["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest", "models/gemini-1.5-flash"])
    
    fn_clean = re.sub(r'[^A-Za-z0-9 ]+', ' ', filename.split('.')[0])
    numbers = [w for w in fn_clean.split() if w.isdigit()]
    num_context = f" (File name contains numbers: {', '.join(numbers)})" if numbers else ""
    
    prompt = f"""You are an elite Adobe Stock SEO specialist. Carefully analyze all visual elements, main subjects, colors, setting, and environment in this photo/video frame{num_context}.

Requirements:
1. TITLE: Single highly specific, accurate commercial stock description in English. MUST be between 180 and 195 characters long. NO commas or special characters. Describe EXACT visual details, main colors, atmosphere, and commercial use.
2. KEYWORDS: Provide EXACTLY 50 highly relevant commercial English keywords separated by comma and space. Include exact objects seen, colors, location, target market, and stock commercial boosters.

Output format STRICTLY:
TITLE: <title text>
KEYWORDS: <comma separated keywords>"""

    response = None
    last_err = None
    for m_name in list(dict.fromkeys(models_to_try)):
        try:
            model = genai.GenerativeModel(m_name)
            response = model.generate_content([prompt, image_pil])
            if response and response.text:
                break
        except Exception as e:
            last_err = e
            continue

    if not response or not response.text:
        raise Exception(f"Gemini API Error: {last_err}")

    text = response.text.strip()
    return parse_ai_response(text, file_type)

def generate_metadata_with_openai(image_pil, api_key, filename, file_type):
    client = OpenAI(api_key=api_key)
    base64_img = encode_image_to_base64(image_pil)
    
    fn_clean = re.sub(r'[^A-Za-z0-9 ]+', ' ', filename.split('.')[0])
    numbers = [w for w in fn_clean.split() if w.isdigit()]
    num_context = f" (File name contains numbers: {', '.join(numbers)})" if numbers else ""
    
    prompt = f"""You are an elite Adobe Stock SEO specialist. Carefully analyze all visual elements in this photo/video frame{num_context}.

Requirements:
1. TITLE: Single descriptive English sentence, MUST be between 180 and 195 characters long. NO commas or special characters. Describe exact visual objects, main colors, setting, and commercial use.
2. KEYWORDS: Exactly 50 highly relevant commercial English keywords separated by comma and space.

Output format STRICTLY:
TITLE: <title text>
KEYWORDS: <comma separated keywords>"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            }
        ],
        max_tokens=300
    )
    
    text = response.choices[0].message.content.strip()
    return parse_ai_response(text, file_type)

def parse_ai_response(text, file_type):
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
    category = "Videos" if file_type == "Video" else "Illustrations/Clip Art"
    
    return title, keywords_str, category

# ---------------------------------------------------------
# 5. UI อัปโหลด และ Gallery แสดงผล
# ---------------------------------------------------------
st.write("รองรับ: **JPG, JPEG, PNG, MP4, MOV** (สูงสุด 100 ไฟล์ต่อรอบ)")

uploaded_files = st.file_uploader(
    "ลากไฟล์มาวางที่นี่", 
    type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "avi", "webm"], 
    accept_multiple_files=True
)

if uploaded_files:
    if len(uploaded_files) > 100:
        st.warning(f"⚠️ เลือกไว้ {len(uploaded_files)} ไฟล์ (แนะนำสูงสุด 100 ไฟล์ต่อรอบ เพื่อเสถียรภาพสูงสุด)")
    
    st.write(f"📁 **พร้อมประมวลผล:** {len(uploaded_files)} ไฟล์")

    status_placeholders = {}
    
    with st.expander("🖼️ ตัวอย่างไฟล์ที่อัปโหลด", expanded=True):
        cols_per_row = 5
        for i in range(0, len(uploaded_files), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, file in enumerate(uploaded_files[i:i+cols_per_row]):
                global_idx = i + j + 1
                with cols[j]:
                    img_preview, _, f_type = process_uploaded_file(file)
                    if img_preview is not None:
                        badge = "🎥 Video" if f_type == "Video" else "🖼️ Image"
                        st.image(img_preview, caption=f"[{global_idx}] {badge}: {file.name}", use_container_width=True)
                        status_placeholders[file.name] = st.empty()
                        status_placeholders[file.name].caption("⏳ รอประมวลผล")
                    else:
                        st.warning(f"[{global_idx}] ⚠️ {file.name}")

    st.write("---")

    if st.button("🚀 เริ่มสร้าง CSV ทันที", use_container_width=True, type="primary"):
        if not openai_api_key and not gemini_api_key:
            st.error("❌ กรุณากรอก API Key ในแถบด้านซ้ายและกดบันทึกก่อนเริ่มทำงาน")
        else:
            results = []
            progress_bar = st.progress(0)
            
            for idx, file in enumerate(uploaded_files):
                status_placeholders[file.name].info("🔄 กำลังประมวลผล...")
                
                _, img_ai, file_type = process_uploaded_file(file)
                
                if img_ai is None:
                    status_placeholders[file.name].error("❌ อ่านไฟล์ล้มเหลว")
                    continue
                    
                try:
                    if openai_api_key and HAS_OPENAI:
                        if idx > 0: time.sleep(0.5)
                        title, keywords, category = generate_metadata_with_openai(img_ai, openai_api_key, file.name, file_type)
                    elif gemini_api_key and HAS_GEMINI:
                        if idx > 0:
                            status_placeholders[file.name].warning("⏳ หน่วงเวลาป้องกัน API Limit...")
                            time.sleep(4.5)
                            status_placeholders[file.name].info("🔄 กำลังประมวลผลด้วย Gemini...")
                        title, keywords, category = generate_metadata_with_gemini(img_ai, gemini_api_key, file.name, file_type)
                    
                    status_placeholders[file.name].success("✅ สำเร็จ")
                    
                    results.append({
                        "Filename": file.name,
                        "Title": title,
                        "Keywords": keywords,
                        "Category": category,
                        "Release Info": "",
                        "Editorial": "No"
                    })
                except Exception as e:
                    status_placeholders[file.name].error(f"❌ Error: {e}")
                
                progress_bar.progress((idx + 1) / len(uploaded_files))
                
            if results:
                st.success(f"🎉 ประมวลผลสำเร็จเรียบร้อย {len(results)} ไฟล์! พร้อมดาวน์โหลด CSV")
                df_full = pd.DataFrame(results)
                st.subheader("📋 ตารางตรวจสอบผลลัพธ์ (Metadata Inspection)")
                st.dataframe(df_full[["Filename", "Title", "Keywords", "Category", "Release Info", "Editorial"]])
                
                csv_data = df_full.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ CSV สำหรับ Adobe Stock",
                    data=csv_data,
                    file_name="adobe_stock_metadata_SEO_optimized.csv",
                    mime="text/csv",
                    type="primary"
                )
