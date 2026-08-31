import streamlit as st
import pandas as pd
from PIL import Image
import re
import unicodedata
import numpy as np
import base64
from io import BytesIO
import time
import tempfile
import os
import av # เปลี่ยนจาก cv2 มาใช้ av แทนเพื่อแก้ปัญหาติดตั้งบน Streamlit

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

st.set_page_config(page_title="Adobe Stock SEO Cloud Generator", layout="wide")

if "openai_api_key" not in st.session_state:
    st.session_state["openai_api_key"] = ""
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""

st.title("⚡ Adobe Stock SEO Generator (Cloud Version)")
st.caption("🚀 รองรับ 80-100 ไฟล์ (รูป & วิดีโอ) | ระบบออนไลน์ไร้ขีดจำกัด | แก้ปัญหา Error ติดตั้ง 100%")

with st.sidebar:
    st.header("🔑 ตั้งค่า Cloud Vision AI")
    input_openai = st.text_input("OpenAI API Key (GPT-4o-mini):", value=st.session_state["openai_api_key"], type="password")
    input_gemini = st.text_input("Gemini API Key (ฟรีจาก Google):", value=st.session_state["gemini_api_key"], type="password")
    
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
        st.success("⚡ เปิดใช้งาน Gemini Vision (พร้อมระบบหน่วงเวลา)")
    else:
        st.warning("⚠️ กรุณาใส่ API Key อย่างน้อย 1 ช่อง")

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

# ฟังก์ชันอ่านไฟล์ที่แก้มาใช้ PyAV 
def process_uploaded_file(uploaded_file):
    filename_lower = uploaded_file.name.lower()
    uploaded_file.seek(0)
    
    if filename_lower.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        file_bytes = uploaded_file.read()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(file_bytes)
            temp_video_path = tmp.name
            
        try:
            container = av.open(temp_video_path)
            stream = container.streams.video[0]
            total_frames = stream.frames if stream.frames > 0 else 100 
            middle_frame_idx = total_frames // 2
            
            frame_img = None
            for i, frame in enumerate(container.decode(stream)):
                if i >= middle_frame_idx or i > 100:
                    frame_img = frame.to_image()
                    break
            container.close()
            
            if os.path.exists(temp_video_path): os.remove(temp_video_path)
            
            if frame_img:
                img = frame_img.convert("RGB")
                file_type = "Video"
            else:
                return None, None, None
        except Exception:
            if os.path.exists(temp_video_path): os.remove(temp_video_path)
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

def generate_metadata_with_gemini(image_pil, api_key, filename, file_type):
    genai.configure(api_key=api_key)
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    prompt = "TITLE: Describe main visual details precisely (no commas, 180-195 chars). KEYWORDS: 50 highly relevant keywords separated by commas."
    for m_name in models:
        try:
            model = genai.GenerativeModel(m_name)
            response = model.generate_content([prompt, image_pil])
            if response and response.text: break
        except: continue
    return parse_ai_response(response.text, file_type)

def generate_metadata_with_openai(image_pil, api_key, filename, file_type):
    client = OpenAI(api_key=api_key)
    base64_img = encode_image_to_base64(image_pil)
    prompt = "TITLE: Describe main visual details precisely (no commas, 180-195 chars). KEYWORDS: 50 highly relevant keywords separated by commas."
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}],
        max_tokens=300
    )
    return parse_ai_response(res.choices[0].message.content, file_type)

def parse_ai_response(text, file_type):
    title = clean_title_ascii(re.search(r'TITLE:\s*(.*)', text, re.IGNORECASE).group(1) if re.search(r'TITLE:\s*(.*)', text, re.IGNORECASE) else text.split('\n')[0])[:195]
    if len(title) < 180: title = (title + " for commercial marketing visual storytelling and creative content design projects asset")[:195]
    kw = re.search(r'KEYWORDS:\s*(.*)', text, re.IGNORECASE).group(1) if re.search(r'KEYWORDS:\s*(.*)', text, re.IGNORECASE) else text.split('\n')[-1]
    kw_list = [clean_ascii(k).lower() for k in kw.split(',')]
    return title, ", ".join(kw_list[:50]), "Videos" if file_type == "Video" else "Illustrations/Clip Art"

st.write("รองรับ: **JPG, JPEG, PNG, MP4, MOV** (สูงสุด 100 ไฟล์ต่อรอบ)")
uploaded_files = st.file_uploader("ลากไฟล์มาวางที่นี่", type=["jpg", "jpeg", "png", "webp", "mp4", "mov"], accept_multiple_files=True)

if uploaded_files:
    status_placeholders = {}
    with st.expander("🖼️ ตัวอย่างไฟล์ที่อัปโหลด", expanded=True):
        cols = st.columns(5)
        for j, file in enumerate(uploaded_files):
            with cols[j % 5]:
                img_prev, _, f_type = process_uploaded_file(file)
                if img_prev:
                    st.image(img_prev, caption=f"[{j+1}] {file.name}", use_container_width=True)
                    status_placeholders[file.name] = st.empty()
                    status_placeholders[file.name].caption("⏳ รอประมวลผล")

    if st.button("🚀 เริ่มสร้าง CSV ทันที", use_container_width=True, type="primary"):
        if not openai_api_key and not gemini_api_key: st.error("❌ กรุณากรอก API Key ก่อน")
        else:
            results = []
            bar = st.progress(0)
            for idx, file in enumerate(uploaded_files):
                status_placeholders[file.name].info("🔄 ประมวลผล...")
                _, img_ai, f_type = process_uploaded_file(file)
                
                try:
                    if openai_api_key:
                        if idx > 0: time.sleep(0.5)
                        t, k, c = generate_metadata_with_openai(img_ai, openai_api_key, file.name, f_type)
                    else:
                        if idx > 0: time.sleep(4.5)
                        t, k, c = generate_metadata_with_gemini(img_ai, gemini_api_key, file.name, f_type)
                    status_placeholders[file.name].success("✅ สำเร็จ")
                    results.append({"Filename": file.name, "Title": t, "Keywords": k, "Category": c, "Release Info": "", "Editorial": "No"})
                except Exception as e: status_placeholders[file.name].error(f"❌ Error")
                bar.progress((idx + 1) / len(uploaded_files))
                
            if results:
                st.success("🎉 เสร็จสิ้น! ดาวน์โหลด CSV ได้เลย")
                df = pd.DataFrame(results)
                st.download_button("📥 โหลด CSV", data=df.to_csv(index=False, encoding="utf-8-sig"), file_name="adobe_seo.csv", mime="text/csv", type="primary")
