# script/extract_pages_with_ocr.py

import fitz
import os
import json
import re
from PIL import Image
import io
import sys

try:
    import pytesseract
    
    # Windows Tesseract path
    if os.name == 'nt':  # Windows
        tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️  pytesseract not installed")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_BASE_DIR = os.path.join(BASE_DIR, "data")
OUT_DIR = os.path.join(BASE_DIR, "data/pages")
os.makedirs(OUT_DIR, exist_ok=True)

def clean(text):
    return re.sub(r"\s+", " ", text).strip()

def extract_text_normal(page):
    """Normal text extraction with error handling"""
    try:
        text = page.get_text()
        if not text.strip():
            text = page.get_text("text")
        if not text.strip():
            blocks = page.get_text("blocks")
            text = " ".join([block[4] for block in blocks if len(block) > 4])
        return clean(text)
    except:
        return ""

def extract_text_ocr(page):
    """OCR-based extraction for image PDFs"""
    if not OCR_AVAILABLE:
        return ""
    
    try:
        # Convert page to image
        mat = fitz.Matrix(2, 2)  # 2x zoom
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # OCR with timeout
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, lang='eng', config=custom_config, timeout=10)
        return clean(text)
    
    except Exception as e:
        return ""

def load_chapter_info(pdf_path, category):
    """Load chapter JSON if available"""
    book_id = os.path.splitext(os.path.basename(pdf_path))[0]
    
    # ✅ FIX: Correct chapter file selection based on category
    if category == "chapter":
        chapter_file = os.path.join(PDF_BASE_DIR, "structures", "chapter.json")
    else:
        chapter_file = os.path.join(PDF_BASE_DIR, "structures", "non_chapter.json")
    
    # ✅ Also try data folder root
    if not os.path.exists(chapter_file):
        if category == "chapter":
            chapter_file = os.path.join(PDF_BASE_DIR, "chapter.json")
        else:
            chapter_file = os.path.join(PDF_BASE_DIR, "non_chapter.json")
    
    if os.path.exists(chapter_file):
        try:
            with open(chapter_file, 'r', encoding='utf-8') as f:
                all_chapters = json.load(f)
            
            # ✅ Debug: Print available book IDs
            if book_id not in all_chapters:
                print(f"   ⚠️  '{book_id}' not found in {os.path.basename(chapter_file)}")
                print(f"       Available IDs: {list(all_chapters.keys())[:3]}...")
                return None
            
            return all_chapters[book_id]
        except Exception as e:
            print(f"   ⚠️  Error loading chapter file: {e}")
            pass
    else:
        print(f"   ⚠️  Chapter file not found: {chapter_file}")
    
    return None

def extract_pdf(pdf_path, category):
    book_id = os.path.splitext(os.path.basename(pdf_path))[0]
    
    # ✅ Suppress MuPDF errors
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except:
        pass
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        print(f"\n📖 {book_id}")
        print(f"   Category: {category}")
        print(f"   Pages: {total_pages}")
        
    except Exception as e:
        print(f"❌ Cannot open: {book_id}")
        return
    
    # Load chapters
    chapter_info = load_chapter_info(pdf_path, category)
    chapter_lookup = {}
    
    # ✅ FIX: has_chapters based ONLY on category (folder name)
    has_chapters = (category == "chapter")
    
    if chapter_info:
        chapters_list = chapter_info.get('chapters', [])
        print(f"   Chapters: {len(chapters_list)} found")
        for chapter in chapters_list:
            start = chapter.get('start_page', 0)
            end = chapter.get('end_page', start)
            for page_num in range(start, end + 1):
                chapter_lookup[page_num] = {
                    'chapter_number': chapter.get('chapter_number'),
                    'chapter_title': chapter.get('title', '')
                }
    elif category == "chapter":
        print(f"   ⚠️  No chapter info available (will extract without chapter metadata)")
    
    pages = []
    empty_pages = 0
    ocr_pages = 0
    error_pages = 0
    is_image_pdf = False
    
    # Check if image-based PDF
    sample_has_text = False
    for sample_idx in range(min(3, total_pages)):
        try:
            sample_text = extract_text_normal(doc[sample_idx])
            if sample_text:
                sample_has_text = True
                break
        except:
            continue
    
    if not sample_has_text:
        is_image_pdf = True
        if not OCR_AVAILABLE:
            print(f"   ❌ Image PDF but OCR not available")
            doc.close()
            return
        print(f"   Type: 🖼️  Image PDF (using OCR)")
    else:
        print(f"   Type: 📄 Text PDF")
    
    # Extract pages
    print(f"   Extracting...", end="", flush=True)
    
    for i, page in enumerate(doc):
        page_num = i + 1
        
        try:
            # Try normal extraction
            text = extract_text_normal(page)
            
            # If no text and image PDF, use OCR
            if not text and is_image_pdf and OCR_AVAILABLE:
                text = extract_text_ocr(page)
                if text:
                    ocr_pages += 1
            
            # Progress indicator
            if page_num % 10 == 0:
                print(f"\r   Extracting... {page_num}/{total_pages}", end="", flush=True)
            
            if not text:
                empty_pages += 1
                continue
            
            page_data = {
                "page_no": page_num,
                "text": text,
                "source": book_id,
                "category": category
            }
            
            # Add chapter info if available
            if page_num in chapter_lookup:
                page_data["chapter_number"] = chapter_lookup[page_num]['chapter_number']
                page_data["chapter_title"] = chapter_lookup[page_num]['chapter_title']
            
            pages.append(page_data)
            
        except KeyboardInterrupt:
            print("\n   ⚠️  Interrupted by user")
            doc.close()
            return
        except Exception as e:
            error_pages += 1
    
    print()  # New line
    doc.close()
    
    # Save
    out_file = f"{category}_{book_id}_pages.json"
    out_path = os.path.join(OUT_DIR, out_file)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "book_id": book_id,
            "category": category,
            "total_pages": total_pages,
            "extracted_pages": len(pages),
            "empty_pages": empty_pages,
            "error_pages": error_pages,
            "ocr_pages": ocr_pages,
            "is_image_pdf": is_image_pdf,
            "has_chapters": has_chapters,  # ✅ Fixed logic
            "pages": pages
        }, f, indent=2, ensure_ascii=False)
    
    # Report
    if len(pages) == 0:
        print(f"   ⚠️  No text extracted!")
        if error_pages > 0:
            print(f"      ({error_pages} pages had errors)")
    else:
        print(f"   ✅ Extracted: {len(pages)} pages")
        if ocr_pages > 0:
            print(f"      (OCR: {ocr_pages} pages)")
        if empty_pages > 0:
            print(f"      (Skipped: {empty_pages} empty)")
        if error_pages > 0:
            print(f"      (Errors: {error_pages} pages)")

if __name__ == "__main__":
    print("="*60)
    print("📚 MEDIBOOK PAGE EXTRACTOR (with OCR)")
    print("="*60)
    
    # ✅ Suppress MuPDF errors globally
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except:
        pass
    
    if not OCR_AVAILABLE:
        print("\n⚠️  OCR NOT AVAILABLE")
        print("   pip install pytesseract pillow")
        print("\nContinuing with text PDFs only...\n")
    else:
        print("✅ OCR Available\n")
    
    for category in ["chapter", "non_chapter"]:
        folder = os.path.join(PDF_BASE_DIR, category)
        
        if not os.path.exists(folder):
            continue
        
        print(f"📁 {category.upper()}")
        
        pdfs = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
        
        for pdf in pdfs:
            try:
                extract_pdf(os.path.join(folder, pdf), category)
            except KeyboardInterrupt:
                print("\n\n⚠️  Process interrupted by user")
                print("✅ Partial extraction saved\n")
                sys.exit(0)
            except Exception as e:
                print(f"\n❌ Fatal error processing {pdf}: {e}\n")
                continue
    
    print("\n" + "="*60)
    print("✅ DONE!")
    print("="*60)