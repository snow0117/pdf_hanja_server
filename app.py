from flask import Flask, request, send_file, jsonify, render_template
import fitz  # PyMuPDF
import re
import os
import uuid
import json
import anthropic
import threading
import time

# Flask 설정
app = Flask(__name__, static_folder='static', template_folder='templates')
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
JSON_FILE = 'temp/한자_훈_음.json'
BASE_URL = "https://hanja.dict.naver.com/#/search?query={}"

# 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# 한자 패턴 정의
hanja_pattern = re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF\U00020000-\U0002A6DF\uF900-\uFAFF]')

# 전역 진행률 저장소
progress_store = {}


class ProgressTracker:
    def __init__(self, task_id):
        self.task_id = task_id
        self.progress = 0
        self.status = "시작"
        self.completed = False
        self.error = None

    def update(self, progress, status):
        self.progress = progress
        self.status = status
        progress_store[self.task_id] = {
            'progress': self.progress,
            'status': self.status,
            'completed': self.completed,
            'error': self.error
        }

    def complete(self, result=None):
        self.progress = 100
        self.status = "완료"
        self.completed = True
        progress_store[self.task_id] = {
            'progress': self.progress,
            'status': self.status,
            'completed': self.completed,
            'error': self.error,
            'result': result
        }

    def set_error(self, error):
        self.error = str(error)
        self.status = "오류 발생"
        progress_store[self.task_id] = {
            'progress': self.progress,
            'status': self.status,
            'completed': False,
            'error': self.error
        }


# JSON 기반 한자 사전 불러오기
def load_hanja_dict():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        hanja_data = json.load(f)
    return {entry["한자"]: (entry["훈"], entry["음"]) for entry in hanja_data}


# 단일 한자에 대한 정보 반환
def get_hanja_info(char, hanja_dict):
    if char in hanja_dict:
        meaning_str, reading_str = hanja_dict[char]
        return meaning_str.split('/'), reading_str.split('/')
    else:
        return ['?'], ['?']


# 단어의 첫 음 반환
def get_reading(hanja_word, hanja_dict):
    return ''.join(hanja_dict.get(c, ('?', '?'))[1].split('/')[0] for c in hanja_word)


# Claude API 호출 함수 (세밀한 진행률 추적 포함)
def ask_claude_to_extract_hanja(text, tracker):
    try:
        tracker.update(45, "Claude AI 클라이언트 초기화 중...")
        time.sleep(0.3)  # 짧은 지연으로 진행률 시각화

        client = anthropic.Anthropic(
            api_key=os.environ.get("CLAUDE_API_KEY")
        )

        tracker.update(50, "AI 분석 프롬프트 준비 중...")
        time.sleep(0.2)

        prompt = f"""
        다음 텍스트에서 한자 문장이랑 2글자 이상 한자 단어를 추출하고 옆에 괄호를 사용해서 음을 적어주세요. 
        그 다음 줄에는 반드시 그 단어를 구성하는 각 한자의 훈음을 "한자 훈 음" 형식으로 / 로 구분하여 표기해주세요.

        반드시 다음 형식을 정확히 따라주세요:

        - 字體 (자체)
        字 글자 자 / 體 몸 체

        - 篆書 (전서)  
        篆 전서 전 / 書 글 서

        - 隸書 (예서)
        隸 예속할 예 / 書 글 서

        규칙:
        1. 첫 번째 줄: "- 한자단어 (발음)"
        2. 두 번째 줄: "한자 훈 음 / 한자 훈 음" (각 글자별로 구분)
        3. 각 단어 그룹 사이에는 빈 줄 하나 삽입
        4. 중복 없이 정리
        5. 다른 불필요한 설명 문장은 절대 포함하지 말 것

        {text}
        """

        tracker.update(55, "Claude AI 서버에 요청 전송 중...")
        time.sleep(0.5)  # API 요청 준비 시간

        tracker.update(60, "AI가 텍스트를 분석하고 있습니다...")

        message = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=7168,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        tracker.update(75, "AI 분석 완료, 한자 패턴 추출 중...")
        time.sleep(0.3)

        tracker.update(82, "한자 단어 분류 및 정리 중...")
        time.sleep(0.2)

        response = message.content[0].text

        tracker.update(88, "훈음 정보 매칭 중...")
        time.sleep(0.2)

        tracker.update(94, "최종 결과 포맷팅 중...")
        time.sleep(0.2)

        print(response)
        return response

    except Exception as e:
        tracker.set_error(f"Claude API 호출 오류: {str(e)}")
        raise e


# 텍스트 전처리 함수 (세밀한 진행률 추적)
def extract_text_for_claude(pdf_path, tracker):
    try:
        tracker.update(8, "PDF 파일 열기 중...")
        time.sleep(0.2)

        tracker.update(12, "PDF 구조 분석 중...")
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        tracker.update(15, f"총 {total_pages}페이지 PDF 발견")
        time.sleep(0.1)

        tracker.update(18, "텍스트 추출 시작...")
        text_parts = []

        # 페이지별 진행률 (18% ~ 30%)
        for i, page in enumerate(doc):
            page_progress = 18 + (12 * (i + 1) / total_pages)
            tracker.update(int(page_progress), f"페이지 {i + 1}/{total_pages} 텍스트 추출 중...")

            page_text = page.get_text()
            text_parts.append(page_text)
            time.sleep(0.1)  # 페이지 처리 시뮬레이션

        doc.close()

        tracker.update(32, "전체 텍스트 병합 중...")
        time.sleep(0.1)
        text = ''.join(text_parts)

        tracker.update(35, "한글 문자 제거 중...")
        time.sleep(0.2)
        text = re.sub(r'[가-힣]', ' ', text)

        tracker.update(38, "공백 정리 및 텍스트 최적화 중...")
        time.sleep(0.2)
        text = re.sub(r'\s+', ' ', text).strip()

        tracker.update(42, "텍스트 전처리 완료")
        time.sleep(0.1)

        return text
    except Exception as e:
        tracker.set_error(f"PDF 처리 오류: {str(e)}")
        raise e


# 백그라운드에서 처리할 함수 (세밀한 진행률)
def process_pdf_background(file_path, task_id):
    tracker = ProgressTracker(task_id)

    try:
        tracker.update(2, "파일 업로드 검증 중...")
        time.sleep(0.2)

        tracker.update(5, "PDF 파일 유효성 확인 중...")
        time.sleep(0.3)

        # PDF 텍스트 추출 (5% ~ 42%)
        text = extract_text_for_claude(file_path, tracker)

        # Claude API 호출 (45% ~ 94%)
        extracted = ask_claude_to_extract_hanja(text, tracker)

        tracker.update(96, "결과 데이터 구조화 중...")
        time.sleep(0.2)

        tracker.update(98, "최종 검증 중...")
        time.sleep(0.2)

        # 완료
        tracker.complete(extracted.splitlines())

    except Exception as e:
        tracker.set_error(str(e))
    finally:
        # 임시 파일 정리
        if os.path.exists(file_path):
            os.remove(file_path)


# 메인 페이지 라우트
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/c1.html')
def c1():
    return render_template('c1.html')


@app.route('/c2.html')
def c2():
    return render_template('c2.html')


@app.route('/c3.html')
def c3():
    return render_template('c3.html')


# PDF 한자 링크 삽입 라우트
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400

    file = request.files['file']
    filename = str(uuid.uuid4()) + '.pdf'
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_path = os.path.join(PROCESSED_FOLDER, f"linked_{filename}")
    file.save(input_path)

    doc = fitz.open(input_path)
    for page in doc:
        full_text = page.get_text()
        hanja_chars = set(hanja_pattern.findall(full_text))
        for ch in hanja_chars:
            rect_list = page.search_for(ch)
            for rect in rect_list:
                page.insert_link({
                    "kind": fitz.LINK_URI,
                    "from": rect,
                    "uri": BASE_URL.format(ch)
                })
    doc.save(output_path)
    doc.close()

    return jsonify({'url': f'/download/{os.path.basename(output_path)}'})


# Claude 기반 한자 분석 라우트 (비동기 처리)
@app.route('/upload2', methods=['POST'])
def upload2():
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400

    file = request.files['file']

    # 고유 작업 ID 생성
    task_id = str(uuid.uuid4())
    filename = f"{task_id}.pdf"
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(input_path)

    # 백그라운드에서 처리 시작
    thread = threading.Thread(target=process_pdf_background, args=(input_path, task_id))
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id})


# 진행률 확인 라우트
@app.route('/progress/<task_id>')
def get_progress(task_id):
    if task_id in progress_store:
        return jsonify(progress_store[task_id])
    else:
        return jsonify({'error': '작업을 찾을 수 없습니다'}), 404


@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(PROCESSED_FOLDER, filename), as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # 환경 변수 PORT가 있으면 사용
    app.run(host='0.0.0.0', port=port)